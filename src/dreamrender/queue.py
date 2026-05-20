from __future__ import annotations

import json
from json import JSONDecodeError
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
from queue import Empty, Queue
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_COMMAND_TEMPLATE = '"{c4d}" -render "{scene}" {take_arg} -frame {start_frame} {end_frame}'
BROWSER_PREVIEW_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
CONVERTIBLE_PREVIEW_EXTENSIONS = {".exr", ".tif", ".tiff"}
IMAGE_EXTENSIONS = BROWSER_PREVIEW_EXTENSIONS | CONVERTIBLE_PREVIEW_EXTENSIONS


class ShareAccessError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_utc(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def seconds_between(start: str | None, end: str | None) -> float | None:
    start_ts = parse_utc(start)
    end_ts = parse_utc(end)
    if start_ts is None or end_ts is None or end_ts < start_ts:
        return None
    return end_ts - start_ts


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def read_json(path: Path) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                return json.load(handle)
        except (OSError, JSONDecodeError) as exc:
            last_error = exc
            if attempt == 4:
                break
            time.sleep(0.05 * (attempt + 1))
    raise last_error or FileNotFoundError(path)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    for attempt in range(8):
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, path)
            return
        except OSError as exc:
            last_error = exc
            if attempt == 7:
                break
            time.sleep(0.08 * (attempt + 1))
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    raise ShareAccessError(f"Cannot write to DreamRender share path: {path.parent}") from last_error


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()


class FileLock:
    def __init__(self, path: Path, stale_after_seconds: int = 300) -> None:
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.handle: int | None = None

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(self.handle, f"{socket.gethostname()} {utc_now()}".encode("utf-8"))
            return True
        except FileExistsError:
            if self._is_stale():
                try:
                    self.path.unlink()
                    self.handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    os.write(self.handle, f"{socket.gethostname()} {utc_now()}".encode("utf-8"))
                    return True
                except OSError:
                    return False
            return False

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.handle is not None:
            os.close(self.handle)
            self.handle = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        return age > self.stale_after_seconds


@dataclass(frozen=True)
class Share:
    root: Path

    @property
    def jobs_dir(self) -> Path:
        return self.root / "jobs"

    @property
    def workers_dir(self) -> Path:
        return self.root / "workers"

    def init(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.workers_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self.root / "dreamrender.json",
            {
                "created_at": utc_now(),
                "format": 1,
                "name": "DreamRender Share",
            },
        )


def doctor_share(share: Share) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("share exists", share.root.exists(), str(share.root)))
    checks.append(("jobs folder exists", share.jobs_dir.exists(), str(share.jobs_dir)))
    checks.append(("workers folder exists", share.workers_dir.exists(), str(share.workers_dir)))

    for folder in [share.root, share.jobs_dir, share.workers_dir]:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / f"write-test-{uuid.uuid4().hex}.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append((f"write access: {folder.name or folder}", True, str(folder)))
        except Exception as exc:
            checks.append((f"write access: {folder.name or folder}", False, f"{folder} ({exc})"))
    return checks


def parse_frames(spec: str) -> list[int]:
    frames: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid descending frame range: {part}")
            frames.update(range(start, end + 1))
        else:
            frames.add(int(part))
    if not frames:
        raise ValueError("No frames were specified.")
    return sorted(frames)


def submit_job(
    share: Share,
    scene: Path,
    frames: list[int],
    output: Path,
    name: str | None = None,
    copy_scene: bool = False,
    metadata: dict[str, Any] | None = None,
) -> str:
    if not scene.exists():
        raise FileNotFoundError(scene)

    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = share.jobs_dir / job_id
    frames_dir = job_dir / "frames"
    logs_dir = job_dir / "logs"
    frames_dir.mkdir(parents=True)
    logs_dir.mkdir()

    if copy_scene:
        job_scene = job_dir / scene.name
        shutil.copy2(scene, job_scene)
    else:
        job_scene = scene

    job = {
        "id": job_id,
        "name": name or scene.stem,
        "created_at": utc_now(),
        "scene": str(job_scene),
        "source_scene": str(scene),
        "output": str(output),
        "path_mode": "copied_scene" if copy_scene else "shared_paths",
        "frames": frames,
        "status": "queued",
        "metadata": metadata or {},
    }
    write_json_atomic(job_dir / "job.json", job)

    for frame in frames:
        write_json_atomic(
            frames_dir / f"{frame:04d}.json",
            {
                "frame": frame,
                "status": "queued",
                "attempts": 0,
                "worker_id": None,
                "updated_at": utc_now(),
            },
        )
    return job_id


def list_jobs(share: Share) -> list[Path]:
    if not share.jobs_dir.exists():
        return []
    def sort_key(path: Path) -> tuple[int, str, str]:
        try:
            job = read_json(path / "job.json")
        except (FileNotFoundError, json.JSONDecodeError):
            return (999_999, "", path.name)
        return (int(job.get("priority", 5000)), str(job.get("created_at", "")), path.name)

    return sorted((path for path in share.jobs_dir.iterdir() if (path / "job.json").exists()), key=sort_key)


def list_visible_jobs(share: Share, include_archived: bool = False) -> list[Path]:
    jobs = []
    for job_dir in list_jobs(share):
        job = read_json(job_dir / "job.json")
        if not include_archived and job.get("status") == "archived":
            continue
        jobs.append(job_dir)
    return jobs


def frame_is_claimable(frame: dict[str, Any], stale_after_seconds: int) -> bool:
    if frame.get("status") in {"queued", "failed"}:
        return True
    if frame.get("status") != "rendering":
        return False
    timestamp = parse_utc(frame.get("heartbeat_at") or frame.get("updated_at"))
    if timestamp is None:
        return True
    return time.time() - timestamp > stale_after_seconds


def claim_next_frames(
    share: Share,
    worker_id: str,
    stale_after_seconds: int,
    chunk_size: int = 1,
) -> tuple[Path, dict[str, Any], list[Path]] | None:
    default_chunk_size = max(1, chunk_size)
    for job_dir in list_jobs(share):
        with FileLock(job_dir / "claim.lock") as job_locked:
            if not job_locked:
                continue
            job = read_json(job_dir / "job.json")
            if job.get("status") in {"paused", "done", "cancelled", "draining", "archived"}:
                continue
            job_chunk_size = int(job.get("metadata", {}).get("chunk_size") or default_chunk_size)
            job_chunk_size = max(1, job_chunk_size)

            frame_paths = sorted((job_dir / "frames").glob("*.json"))
            for start_index, first_frame_path in enumerate(frame_paths):
                frame = read_json(first_frame_path)
                if not frame_is_claimable(frame, stale_after_seconds):
                    continue

                claimed_paths = [first_frame_path]
                expected_frame = int(frame["frame"]) + 1
                for candidate_path in frame_paths[start_index + 1 :]:
                    if len(claimed_paths) >= job_chunk_size:
                        break
                    candidate = read_json(candidate_path)
                    if int(candidate["frame"]) != expected_frame:
                        break
                    if not frame_is_claimable(candidate, stale_after_seconds):
                        break
                    claimed_paths.append(candidate_path)
                    expected_frame += 1

                chunk_id = uuid.uuid4().hex[:8]
                chunk_end = int(read_json(claimed_paths[-1])["frame"])
                for path in claimed_paths:
                    claimed = read_json(path)
                    claimed["status"] = "rendering"
                    claimed["worker_id"] = worker_id
                    claimed["chunk_id"] = chunk_id
                    claimed["chunk_start"] = int(frame["frame"])
                    claimed["chunk_end"] = chunk_end
                    claimed["attempts"] = int(claimed.get("attempts", 0)) + 1
                    claimed["started_at"] = utc_now()
                    claimed["heartbeat_at"] = utc_now()
                    claimed["updated_at"] = utc_now()
                    write_json_atomic(path, claimed)
                return job_dir, job, claimed_paths
    return None


def claim_next_frame(share: Share, worker_id: str, stale_after_seconds: int) -> tuple[Path, dict[str, Any], Path] | None:
    claim = claim_next_frames(share, worker_id, stale_after_seconds, 1)
    if claim is None:
        return None
    job_dir, job, frame_paths = claim
    return job_dir, job, frame_paths[0]


def heartbeat_worker(share: Share, worker_id: str, active: dict[str, Any] | None = None) -> None:
    write_json_atomic(
        share.workers_dir / f"{worker_id}.json",
        {
            "worker_id": worker_id,
            "host": socket.gethostname(),
            "heartbeat_at": utc_now(),
            "active": active,
        },
    )


def read_job_status(job_dir: Path) -> str:
    try:
        return str(read_json(job_dir / "job.json").get("status", "queued"))
    except FileNotFoundError:
        return "cancelled"
    except Exception:
        return "queued"


def heartbeat_frames(frame_paths: list[Path], worker_id: str) -> None:
    for frame_path in frame_paths:
        with FileLock(frame_path.with_suffix(".lock")) as locked:
            if not locked:
                continue
            frame = read_json(frame_path)
            if frame.get("status") == "rendering" and frame.get("worker_id") == worker_id:
                frame["heartbeat_at"] = utc_now()
                frame["updated_at"] = utc_now()
                write_json_atomic(frame_path, frame)


def heartbeat_frame(frame_path: Path, worker_id: str) -> None:
    heartbeat_frames([frame_path], worker_id)


def build_command(
    template: str,
    c4d: Path,
    job: dict[str, Any],
    job_dir: Path,
    start_frame: int,
    end_frame: int,
    worker_id: str,
) -> str:
    take_name = str(job.get("metadata", {}).get("take_name") or "")
    take_arg = f'-take "{take_name}"' if take_name else ""
    return template.format(
        c4d=str(c4d),
        scene=job["scene"],
        take=take_name,
        take_arg=take_arg,
        frame=start_frame,
        start_frame=start_frame,
        end_frame=end_frame,
        output=job["output"],
        job_id=job["id"],
        job_dir=str(job_dir),
        worker_id=worker_id,
    )


def render_frame(
    share: Share,
    c4d: Path,
    command_template: str,
    worker_id: str,
    job_dir: Path,
    job: dict[str, Any],
    frame_path: Path,
    heartbeat_interval: int,
) -> int:
    return render_frames(share, c4d, command_template, worker_id, job_dir, job, [frame_path], heartbeat_interval)


def render_frames(
    share: Share,
    c4d: Path,
    command_template: str,
    worker_id: str,
    job_dir: Path,
    job: dict[str, Any],
    frame_paths: list[Path],
    heartbeat_interval: int,
) -> int:
    frames = [read_json(path) for path in frame_paths]
    start_frame = int(frames[0]["frame"])
    end_frame = int(frames[-1]["frame"])
    scene_path = Path(job["scene"])
    if not scene_path.exists():
        log_path = job_dir / "logs" / f"{start_frame:04d}-{end_frame:04d}-{worker_id}.log"
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{utc_now()}] Scene path is not available on this worker: {scene_path}\n")
        complete_frames(frame_paths, worker_id, 2, log_path)
        return 2

    command = build_command(command_template, c4d, job, job_dir, start_frame, end_frame, worker_id)
    log_path = job_dir / "logs" / f"{start_frame:04d}-{end_frame:04d}-{worker_id}.log"

    process = subprocess.Popen(
        command,
        cwd=str(job_dir),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output_lines: Queue[str] = Queue()

    def read_output() -> None:
        if process.stdout is None:
            return
        for output_line in process.stdout:
            output_lines.put(output_line)

    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()

    last_heartbeat = 0.0
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"[{utc_now()}] Running: {command}\n")
        cancelled = False
        while process.poll() is None:
            try:
                line = output_lines.get(timeout=1)
                log.write(line)
                log.flush()
            except Empty:
                pass
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                active = {"job_id": job["id"], "start_frame": start_frame, "end_frame": end_frame}
                try:
                    heartbeat_worker(share, worker_id, active)
                except ShareAccessError as exc:
                    log.write(f"[{utc_now()}] Could not write worker heartbeat: {exc}\n")
                    log.flush()
                try:
                    heartbeat_frames(frame_paths, worker_id)
                except ShareAccessError as exc:
                    log.write(f"[{utc_now()}] Could not write frame heartbeat: {exc}\n")
                    log.flush()
                last_heartbeat = now
                if read_job_status(job_dir) == "cancelled":
                    cancelled = True
                    log.write(f"[{utc_now()}] Job was cancelled. Stopping Cinema 4D process tree.\n")
                    log.flush()
                    terminate_process_tree(process)
                    break

        output_thread.join(timeout=2)
        while True:
            try:
                log.write(output_lines.get_nowait())
            except Empty:
                break
        return_code = -9 if cancelled else process.wait()
        log.write(f"[{utc_now()}] Exit code: {return_code}\n")

    complete_frames(frame_paths, worker_id, return_code, log_path)
    return return_code


def complete_frame(frame_path: Path, worker_id: str, return_code: int, log_path: Path) -> None:
    complete_frames([frame_path], worker_id, return_code, log_path)


def complete_frames(frame_paths: list[Path], worker_id: str, return_code: int, log_path: Path) -> None:
    job_dirs = set()
    for frame_path in frame_paths:
        job_dirs.add(frame_path.parents[1])
        complete_one_frame(frame_path, worker_id, return_code, log_path)
    for job_dir in job_dirs:
        update_job_status_from_frames(job_dir)


def complete_one_frame(frame_path: Path, worker_id: str, return_code: int, log_path: Path) -> None:
    with FileLock(frame_path.with_suffix(".lock")) as locked:
        if not locked:
            return
        frame = read_json(frame_path)
        if frame.get("worker_id") != worker_id:
            return
        if return_code == 0:
            frame["status"] = "done"
        elif return_code == -9:
            frame["status"] = "cancelled"
        else:
            frame["status"] = "failed"
        frame["return_code"] = return_code
        frame["log"] = str(log_path)
        frame["finished_at"] = utc_now()
        frame["updated_at"] = utc_now()
        write_json_atomic(frame_path, frame)


def update_job_status_from_frames(job_dir: Path) -> None:
    job_path = job_dir / "job.json"
    job = read_json(job_path)
    frame_statuses = [read_json(path).get("status") for path in (job_dir / "frames").glob("*.json")]
    archive_when_done = job.get("metadata", {}).get("archive_when_done")
    if job.get("status") == "cancelled":
        if archive_when_done and "rendering" not in frame_statuses:
            job["status"] = "archived"
            job["finished_at"] = utc_now()
            job["updated_at"] = utc_now()
            write_json_atomic(job_path, job)
        return
    if job.get("status") == "paused":
        return
    if frame_statuses and all(status == "done" for status in frame_statuses):
        job["status"] = "archived" if job.get("metadata", {}).get("archive_when_done") else "done"
        job["finished_at"] = utc_now()
        job["updated_at"] = utc_now()
        write_json_atomic(job_path, job)
        return
    if archive_when_done:
        job["status"] = "draining"
        job["updated_at"] = utc_now()
        write_json_atomic(job_path, job)


def summarize_job(job_dir: Path) -> dict[str, Any]:
    job = read_json(job_dir / "job.json")
    counts: dict[str, int] = {}
    frames = [read_json(frame_path) for frame_path in (job_dir / "frames").glob("*.json")]
    for frame in frames:
        status = frame.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    total = sum(counts.values())
    done = counts.get("done", 0)
    stats = calculate_job_stats(job, frames)
    output_paths = expand_c4d_output_path(job)
    display_output = str(output_paths[1] if len(output_paths) > 1 else output_paths[0]) if output_paths else job.get("output")
    return {
        "id": job["id"],
        "name": job["name"],
        "status": job.get("status", "queued"),
        "created_at": job.get("created_at"),
        "scene": job.get("scene"),
        "output": job.get("output"),
        "display_output": display_output,
        "path_mode": job.get("path_mode"),
        "priority": int(job.get("priority", 5000)),
        "metadata": job.get("metadata", {}),
        "counts": counts,
        "progress": (done / total * 100.0) if total else 0.0,
        "stats": stats,
    }


def calculate_job_stats(job: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
    durations = []
    worker_stats: dict[str, dict[str, Any]] = {}
    slowest: dict[str, Any] | None = None
    fastest: dict[str, Any] | None = None

    for frame in frames:
        duration = seconds_between(frame.get("started_at"), frame.get("finished_at"))
        worker_id = frame.get("worker_id")
        if duration is not None:
            durations.append(duration)
            if worker_id:
                stats = worker_stats.setdefault(worker_id, {"frames": 0, "seconds": 0.0, "failed": 0})
                stats["frames"] += 1
                stats["seconds"] += duration
            entry = {"frame": frame.get("frame"), "seconds": duration, "worker_id": worker_id}
            if slowest is None or duration > slowest["seconds"]:
                slowest = entry
            if fastest is None or duration < fastest["seconds"]:
                fastest = entry
        elif worker_id:
            worker_stats.setdefault(worker_id, {"frames": 0, "seconds": 0.0, "failed": 0})

        if frame.get("status") == "failed" and worker_id:
            worker_stats.setdefault(worker_id, {"frames": 0, "seconds": 0.0, "failed": 0})["failed"] += 1

    for worker_id, stats in worker_stats.items():
        frames_done = stats["frames"]
        seconds = stats["seconds"]
        stats["avg_seconds"] = seconds / frames_done if frames_done else None
        stats["time"] = format_seconds(seconds)
        stats["avg"] = format_seconds(stats["avg_seconds"])

    queued = sum(1 for frame in frames if frame.get("status") in {"queued", "failed"})
    avg_seconds = (sum(durations) / len(durations)) if durations else None
    eta_seconds = avg_seconds * queued if avg_seconds is not None else None
    started_values = [parse_utc(frame.get("started_at")) for frame in frames]
    started_values = [value for value in started_values if value is not None]
    first_started = min(started_values) if started_values else None
    finished_values = [parse_utc(frame.get("finished_at")) for frame in frames]
    finished_values = [value for value in finished_values if value is not None]
    all_terminal = frames and all(frame.get("status") in {"done", "failed", "cancelled"} for frame in frames)
    elapsed_end = max(finished_values) if all_terminal and finished_values else time.time()
    elapsed = elapsed_end - first_started if first_started is not None else None

    return {
        "avg_seconds": avg_seconds,
        "avg": format_seconds(avg_seconds),
        "eta_seconds": eta_seconds,
        "eta": format_seconds(eta_seconds),
        "elapsed_seconds": elapsed,
        "elapsed": format_seconds(elapsed),
        "slowest": slowest,
        "fastest": fastest,
        "workers": worker_stats,
    }


def list_frames(job_dir: Path) -> list[dict[str, Any]]:
    frames = []
    for frame_path in sorted((job_dir / "frames").glob("*.json")):
        frame = read_json(frame_path)
        frame["id"] = frame_path.stem
        frames.append(frame)
    return frames


def get_job_detail(share: Share, job_id: str) -> dict[str, Any]:
    job_dir = share.jobs_dir / job_id
    summary = summarize_job(job_dir)
    summary["frames"] = list_frames(job_dir)
    return summary


def find_frame(job_dir: Path, frame_number: int) -> tuple[Path, dict[str, Any]]:
    frame_path = job_dir / "frames" / f"{frame_number:04d}.json"
    return frame_path, read_json(frame_path)


def read_frame_log(share: Share, job_id: str, frame_number: int, max_chars: int = 60000) -> dict[str, Any]:
    job_dir = share.jobs_dir / job_id
    _, frame = find_frame(job_dir, frame_number)
    log_path_text = frame.get("log")
    if not log_path_text:
        return {"frame": frame, "log": "No log has been written for this frame yet.", "path": None}
    log_path = Path(log_path_text)
    if not log_path.exists():
        return {"frame": frame, "log": f"Log file does not exist: {log_path}", "path": str(log_path)}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[-max_chars:]
    return {"frame": frame, "log": text, "path": str(log_path)}


def expand_c4d_output_path(job: dict[str, Any]) -> list[Path]:
    output_text = str(job.get("output", ""))
    metadata = job.get("metadata", {})
    scene = Path(str(job.get("source_scene") or job.get("scene") or ""))
    project_folder = Path(str(metadata.get("project_folder") or scene.parent))
    document_name = str(metadata.get("document_name") or scene.name)
    project_name = Path(document_name).stem or scene.stem
    take_name = str(metadata.get("take_name") or "")
    replacements = {
        "$prj": project_name,
        "$project": project_name,
        "$take": take_name,
    }

    candidates = [output_text]
    lowered = output_text.lower()
    expanded = output_text
    for token, value in replacements.items():
        expanded = expanded.replace(token, value).replace(token.upper(), value)
    if expanded not in candidates:
        candidates.append(expanded)

    paths: list[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute() and not str(path).startswith("\\\\"):
            path = project_folder / path
        paths.append(path)

    if "$" in lowered and project_folder.exists():
        paths.append(project_folder / "render")
    return paths


def find_frame_preview(share: Share, job_id: str, frame_number: int) -> dict[str, Any]:
    job_dir = share.jobs_dir / job_id
    job = read_json(share.jobs_dir / job_id / "job.json")
    candidates: list[Path] = []
    frame_tokens = {
        str(frame_number),
        f"{frame_number:04d}",
        f"{frame_number:05d}",
        f"{frame_number:06d}",
    }
    search_dirs = []
    for output in expand_c4d_output_path(job):
        if output.suffix:
            search_dirs.append(output.parent)
        else:
            search_dirs.append(output)
            search_dirs.append(output.parent)

    for folder in dict.fromkeys(search_dirs):
        if not folder.exists() or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            name = path.stem.lower()
            if any(token in name for token in frame_tokens):
                candidates.append(path)

    if not candidates:
        return {"frame": frame_number, "path": None, "renderable": False, "message": "No output image found for this frame yet."}
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    source = candidates[0]
    extension = source.suffix.lower()
    if extension in BROWSER_PREVIEW_EXTENSIONS:
        return {
            "frame": frame_number,
            "path": str(source),
            "source_path": str(source),
            "source_extension": extension,
            "renderable": True,
            "converted": False,
        }

    thumbnail = ensure_frame_thumbnail(job_dir, frame_number, source)
    if thumbnail is not None:
        return {
            "frame": frame_number,
            "path": str(thumbnail),
            "source_path": str(source),
            "source_extension": extension,
            "renderable": True,
            "converted": True,
            "message": f"Generated browser preview from {extension.upper().lstrip('.')}.",
        }

    return {
        "frame": frame_number,
        "path": None,
        "source_path": str(source),
        "source_extension": extension,
        "renderable": False,
        "message": (
            f"Found {extension.upper().lstrip('.')} output, but browsers cannot display it directly. "
            "Install ImageMagick, OpenImageIO, or ffmpeg on this machine to enable automatic PNG previews."
        ),
    }


def ensure_frame_thumbnail(job_dir: Path, frame_number: int, source: Path) -> Path | None:
    if source.suffix.lower() not in CONVERTIBLE_PREVIEW_EXTENSIONS or not source.exists():
        return None
    stat = source.stat()
    thumb_dir = job_dir / "thumbs"
    thumb_path = thumb_dir / f"{frame_number:04d}-{int(stat.st_mtime)}-{stat.st_size}.png"
    if thumb_path.exists():
        return thumb_path

    thumb_dir.mkdir(parents=True, exist_ok=True)
    converters = thumbnail_commands(source, thumb_path)
    for command in converters:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and thumb_path.exists() and thumb_path.stat().st_size > 0:
            cleanup_old_thumbnails(thumb_dir, frame_number, keep=thumb_path)
            return thumb_path
        if thumb_path.exists():
            thumb_path.unlink(missing_ok=True)
    return None


def thumbnail_commands(source: Path, thumb_path: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    magick = shutil.which("magick")
    if magick:
        commands.append([magick, str(source), "-auto-level", "-thumbnail", "1280x720>", f"png:{thumb_path}"])
    oiiotool = shutil.which("oiiotool")
    if oiiotool:
        commands.append([oiiotool, str(source), "--resize", "1280x720", "-o", str(thumb_path)])
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        commands.append([ffmpeg, "-y", "-i", str(source), "-frames:v", "1", str(thumb_path)])
    return commands


def cleanup_old_thumbnails(thumb_dir: Path, frame_number: int, keep: Path) -> None:
    for path in thumb_dir.glob(f"{frame_number:04d}-*.png"):
        if path != keep:
            path.unlink(missing_ok=True)


def list_workers(share: Share, stale_after_seconds: int = 60) -> list[dict[str, Any]]:
    workers = []
    if not share.workers_dir.exists():
        return workers
    job_statuses = {}
    active_rendering_ranges: dict[tuple[str, str], dict[str, Any]] = {}
    for job_dir in list_jobs(share):
        try:
            job = read_json(job_dir / "job.json")
        except FileNotFoundError:
            continue
        except Exception:
            continue
        job_id = str(job.get("id") or job_dir.name)
        job_statuses[job_id] = job.get("status", "unknown")
        for frame_path in (job_dir / "frames").glob("*.json"):
            try:
                frame = read_json(frame_path)
            except Exception:
                continue
            if frame.get("status") != "rendering" or not frame.get("worker_id"):
                continue
            frame_worker_id = str(frame["worker_id"])
            frame_number = int(frame.get("frame", frame_path.stem))
            frame_heartbeat = parse_utc(frame.get("heartbeat_at") or frame.get("updated_at")) or 0
            key = (frame_worker_id, job_id)
            current = active_rendering_ranges.get(key)
            if current is None:
                active_rendering_ranges[key] = {
                    "job_id": job_id,
                    "start_frame": frame_number,
                    "end_frame": frame_number,
                    "heartbeat_ts": frame_heartbeat,
                }
            else:
                current["start_frame"] = min(current["start_frame"], frame_number)
                current["end_frame"] = max(current["end_frame"], frame_number)
                current["heartbeat_ts"] = max(current["heartbeat_ts"], frame_heartbeat)
    active_rendering: dict[str, dict[str, Any]] = {}
    for (worker_id, _job_id), active in active_rendering_ranges.items():
        current = active_rendering.get(worker_id)
        if current is None or active["heartbeat_ts"] >= current.get("heartbeat_ts", 0):
            active_rendering[worker_id] = active
    seen_workers = set()
    for worker_path in sorted(share.workers_dir.glob("*.json")):
        try:
            worker = read_json(worker_path)
        except Exception:
            continue
        worker_id = str(worker.get("worker_id") or worker_path.stem)
        seen_workers.add(worker_id)
        heartbeat = parse_utc(worker.get("heartbeat_at"))
        age = None if heartbeat is None else max(0, time.time() - heartbeat)
        worker["state"] = "offline"
        worker["last_seen_seconds"] = age
        if heartbeat is not None and age is not None and age <= stale_after_seconds:
            worker["state"] = "online"
        active = worker.get("active")
        active_job_id = active.get("job_id") if isinstance(active, dict) else None
        rendering_active = active_rendering.get(worker_id)
        if worker["state"] != "online" and rendering_active:
            worker["state"] = "heartbeat_lost"
            worker["active"] = {
                "job_id": rendering_active["job_id"],
                "start_frame": rendering_active["start_frame"],
                "end_frame": rendering_active["end_frame"],
            }
            active = worker["active"]
            active_job_id = rendering_active["job_id"]
        active_job_status = job_statuses.get(active_job_id)
        worker["active_job_status"] = active_job_status
        worker["stale_active"] = bool(worker.get("active") and worker["state"] == "offline")
        if worker["state"] == "offline":
            worker["active"] = None
        workers.append(worker)
    for worker_id, rendering_active in sorted(active_rendering.items()):
        if worker_id in seen_workers:
            continue
        workers.append(
            {
                "worker_id": worker_id,
                "host": worker_id,
                "heartbeat_at": None,
                "state": "heartbeat_lost",
                "last_seen_seconds": None,
                "active": {
                    "job_id": rendering_active["job_id"],
                    "start_frame": rendering_active["start_frame"],
                    "end_frame": rendering_active["end_frame"],
                },
                "active_job_status": job_statuses.get(rendering_active["job_id"]),
                "stale_active": False,
            }
        )
    return workers


def queue_snapshot(share: Share, include_archived: bool = False) -> dict[str, Any]:
    workers = list_workers(share)
    active_job_ids = {
        worker["active"]["job_id"]
        for worker in workers
        if isinstance(worker.get("active"), dict) and worker["active"].get("job_id")
    }
    seen_job_ids = set()
    jobs = []
    for job_dir in list_visible_jobs(share, include_archived):
        seen_job_ids.add(job_dir.name)
        summary = summarize_job(job_dir)
        archive_pending = summary.get("metadata", {}).get("archive_when_done")
        is_active = summary["id"] in active_job_ids
        if archive_pending and not is_active and not include_archived:
            continue
        summary["frames"] = list_frames(job_dir)
        jobs.append(summary)
    if not include_archived:
        for job_id in sorted(active_job_ids - seen_job_ids, reverse=True):
            job_dir = share.jobs_dir / job_id
            if not job_dir.exists():
                continue
            summary = summarize_job(job_dir)
            if summary.get("status") != "archived":
                continue
            summary["frames"] = list_frames(job_dir)
            summary["visible_because_active"] = True
            jobs.insert(0, summary)
    return {
        "generated_at": utc_now(),
        "share": str(share.root),
        "jobs": jobs,
        "workers": workers,
    }


def set_job_status(share: Share, job_id: str, status: str) -> None:
    if status not in {"queued", "paused", "cancelled", "draining", "archived"}:
        raise ValueError(f"Unsupported job status: {status}")
    job_path = share.jobs_dir / job_id / "job.json"
    job = read_json(job_path)
    if status == "archived":
        frame_statuses = [
            read_json(path).get("status")
            for path in (share.jobs_dir / job_id / "frames").glob("*.json")
        ]
        if job.get("status") == "cancelled" and "rendering" in frame_statuses:
            metadata = dict(job.get("metadata", {}))
            metadata["archive_when_done"] = True
            job["metadata"] = metadata
            job["updated_at"] = utc_now()
            write_json_atomic(job_path, job)
            return
        if "rendering" in frame_statuses:
            metadata = dict(job.get("metadata", {}))
            metadata["archive_when_done"] = True
            job["metadata"] = metadata
            job["status"] = "draining"
            job["updated_at"] = utc_now()
            write_json_atomic(job_path, job)
            return
    job["status"] = status
    job["updated_at"] = utc_now()
    write_json_atomic(job_path, job)


def set_job_priorities(share: Share, job_ids: list[str]) -> None:
    for index, job_id in enumerate(job_ids):
        job_path = share.jobs_dir / job_id / "job.json"
        if not job_path.exists():
            continue
        with FileLock(job_path.with_suffix(".lock")) as locked:
            if not locked:
                continue
            job = read_json(job_path)
            job["priority"] = index
            job["updated_at"] = utc_now()
            write_json_atomic(job_path, job)


def requeue_frames(share: Share, job_id: str, frames: list[int]) -> int:
    changed = 0
    job_dir = share.jobs_dir / job_id
    for frame_number in frames:
        frame_path = job_dir / "frames" / f"{frame_number:04d}.json"
        with FileLock(frame_path.with_suffix(".lock")) as locked:
            if not locked:
                continue
            frame = read_json(frame_path)
            if frame.get("status") == "rendering":
                continue
            frame["status"] = "queued"
            frame["worker_id"] = None
            frame["chunk_id"] = None
            frame["chunk_start"] = None
            frame["chunk_end"] = None
            frame["return_code"] = None
            frame["updated_at"] = utc_now()
            write_json_atomic(frame_path, frame)
            changed += 1
    if changed:
        job_path = job_dir / "job.json"
        job = read_json(job_path)
        if job.get("status") in {"done", "cancelled"}:
            job["status"] = "queued"
            job["updated_at"] = utc_now()
            write_json_atomic(job_path, job)
    return changed


def requeue_failed(share: Share, job_id: str | None = None) -> int:
    changed = 0
    for job_dir in list_jobs(share):
        if job_id and job_dir.name != job_id:
            continue
        job_changed = 0
        for frame_path in (job_dir / "frames").glob("*.json"):
            with FileLock(frame_path.with_suffix(".lock")) as locked:
                if not locked:
                    continue
                frame = read_json(frame_path)
                if frame.get("status") == "failed":
                    frame["status"] = "queued"
                    frame["worker_id"] = None
                    frame["updated_at"] = utc_now()
                    write_json_atomic(frame_path, frame)
                    changed += 1
                    job_changed += 1
        if job_changed:
            job_path = job_dir / "job.json"
            job = read_json(job_path)
            if job.get("status") == "done":
                job["status"] = "queued"
                job["updated_at"] = utc_now()
                write_json_atomic(job_path, job)
    return changed
