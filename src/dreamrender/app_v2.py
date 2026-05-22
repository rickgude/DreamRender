from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .queue import (
    CODE_SIGNATURE,
    Share,
    clear_worker_stop_request,
    get_job_detail,
    queue_snapshot,
    repair_queue,
    request_worker_restart,
    request_worker_stop_after_batch,
    request_worker_stop_now,
    requeue_failed,
    set_job_priorities,
    set_job_status,
    worker_stop_requested,
)


CONFIG_PATH = Path.home() / "DreamRenderApp.json"
DEFAULT_SHARE = Path(__file__).resolve().parents[2] / "DreamRenderShare"
DEFAULT_C4D = Path(r"C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe")
STATIC_DIR = Path(__file__).with_name("app_v2_static")
C4D_VERSION = "2026"


def load_config() -> dict[str, object]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict[str, object]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def default_config() -> dict[str, object]:
    config = load_config()
    return {
        "share": str(config.get("share", DEFAULT_SHARE)),
        "c4d": str(config.get("c4d", DEFAULT_C4D)),
        "worker_id": str(config.get("worker_id", socket.gethostname())),
        "chunk_size": int(config.get("chunk_size", 5) or 5),
        "monitor_port": int(config.get("monitor_port", 8766) or 8766),
        "keep_worker_running": bool(config.get("keep_worker_running", True)),
    }


def response_json(handler: BaseHTTPRequestHandler, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, creationflags=creation_flags())
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags())
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidate = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
    return str(candidate) if candidate.exists() else None


def query_gpus() -> tuple[list[dict[str, object]], str | None]:
    nvidia_smi = find_nvidia_smi()
    if not nvidia_smi:
        return [], "NVIDIA GPU data is not available."
    command = [
        nvidia_smi,
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, creationflags=creation_flags())
    except Exception as exc:
        return [], f"Could not read GPU data: {exc}"
    if result.returncode != 0:
        return [], result.stderr.strip() or "Could not read GPU data."
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        try:
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "util": int(parts[2]),
                    "memory_used": int(parts[3]),
                    "memory_total": int(parts[4]),
                }
            )
        except ValueError:
            continue
    return gpus, None if gpus else "No GPU data returned."


class AppV2State:
    def __init__(self) -> None:
        self.config = default_config()
        self.worker_process: subprocess.Popen[str] | None = None
        self.monitor_process: subprocess.Popen[str] | None = None
        self.worker_log: deque[str] = deque(maxlen=1200)
        self.status = "Ready"
        self.lock = threading.RLock()

    def python_command(self) -> list[str]:
        return [sys.executable, "-m", "dreamrender"]

    def persist(self) -> None:
        save_config(self.config)

    def share(self) -> Share:
        return Share(Path(str(self.config["share"])))

    def monitor_url(self) -> str:
        return f"http://127.0.0.1:{int(self.config['monitor_port'])}/"

    def worker_running(self) -> bool:
        return self.worker_process is not None and self.worker_process.poll() is None

    def monitor_running(self) -> bool:
        return self.monitor_process is not None and self.monitor_process.poll() is None

    def start(self) -> None:
        with self.lock:
            self.share().init()
            self.start_monitor()
            self.start_worker()
            self.status = "DreamRender running"

    def stop(self) -> None:
        with self.lock:
            if self.worker_process and self.worker_process.poll() is None:
                stop_pid_tree(self.worker_process.pid)
            if self.monitor_process and self.monitor_process.poll() is None:
                stop_pid_tree(self.monitor_process.pid)
            self.worker_process = None
            self.monitor_process = None
            self.status = "DreamRender stopped"

    def start_worker(self) -> None:
        if self.worker_running():
            return
        c4d = Path(str(self.config["c4d"]))
        if not c4d.exists():
            self.status = "Cinema 4D Commandline.exe is missing"
            return
        command = self.python_command() + [
            "worker",
            "--share",
            str(self.config["share"]),
            "--c4d",
            str(self.config["c4d"]),
            "--worker-id",
            str(self.config["worker_id"]),
            "--chunk-size",
            str(self.config["chunk_size"]),
        ]
        self.worker_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags(),
        )
        threading.Thread(target=self.read_worker_log, args=(self.worker_process,), daemon=True).start()

    def start_monitor(self) -> None:
        if self.monitor_running():
            return
        command = self.python_command() + [
            "monitor",
            "--share",
            str(self.config["share"]),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.config["monitor_port"]),
        ]
        self.monitor_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags())

    def read_worker_log(self, process: subprocess.Popen[str]) -> None:
        if not process.stdout:
            return
        for line in process.stdout:
            self.worker_log.append(line.rstrip())

    def update_config(self, payload: dict[str, object]) -> None:
        for key in ("share", "c4d", "worker_id"):
            if key in payload:
                self.config[key] = str(payload[key])
        for key in ("chunk_size", "monitor_port"):
            if key in payload:
                self.config[key] = max(1, int(payload[key] or 1))
        if "keep_worker_running" in payload:
            self.config["keep_worker_running"] = bool(payload["keep_worker_running"])
        self.persist()

    def install_plugin(self) -> tuple[bool, str]:
        source_script = Path(__file__).resolve().parents[2] / "cinema4d" / "DreamRenderSubmit.py"
        source_plugin = Path(__file__).resolve().parents[2] / "cinema4d" / "plugin" / "DreamRender.pyp"
        if not source_script.exists() or not source_plugin.exists():
            return False, "Cinema 4D plugin source files are missing."
        targets = self.c4d_plugin_targets()
        if not targets:
            return False, f"No Cinema 4D {C4D_VERSION} preferences folder found. Open Cinema 4D once, close it, then try again."
        installed = []
        for target in targets:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_script, target / "DreamRenderSubmit.py")
            shutil.copy2(source_plugin, target / "DreamRender.pyp")
            installed.append(str(target))
        return True, "Installed plugin to:\n" + "\n".join(installed)

    def c4d_plugin_targets(self) -> list[Path]:
        if os.name != "nt":
            return []
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return [prefs / "plugins" / "DreamRender" for prefs in sorted((appdata / "Maxon").glob(f"Maxon Cinema 4D {C4D_VERSION}_*"), reverse=True)]

    def open_output_folder(self, job_id: str) -> None:
        job = get_job_detail(self.share(), job_id)
        output_text = str(job.get("output") or "")
        if not output_text:
            raise FileNotFoundError("Job has no output path.")
        output = Path(output_text)
        folder = output.parent if output.suffix else output
        while not folder.exists() and folder != folder.parent:
            folder = folder.parent
        if not folder.exists():
            raise FileNotFoundError(folder)
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            webbrowser.open(folder.as_uri())

    def health(self) -> list[dict[str, object]]:
        share = Path(str(self.config["share"]))
        c4d = Path(str(self.config["c4d"]))
        items = [
            {"label": "Queue", "ok": share.exists(), "detail": str(share)},
            {"label": "Cinema 4D", "ok": c4d.exists(), "detail": str(c4d)},
            {"label": "Plugin", "ok": any((target / "DreamRender.pyp").exists() for target in self.c4d_plugin_targets()), "detail": f"Cinema 4D {C4D_VERSION} submitter"},
        ]
        try:
            share.mkdir(parents=True, exist_ok=True)
            probe = share / f"write-test-{int(time.time() * 1000)}.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            items.append({"label": "Queue Access", "ok": True, "detail": "Writable"})
        except Exception as exc:
            items.append({"label": "Queue Access", "ok": False, "detail": str(exc)})
        return items

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            if self.worker_process and self.worker_process.poll() is not None:
                self.status = f"Worker exited with code {self.worker_process.returncode}"
                self.worker_process = None
            if self.monitor_process and self.monitor_process.poll() is not None:
                self.monitor_process = None
            share_snapshot: dict[str, object] = {"jobs": [], "workers": []}
            try:
                share_snapshot = queue_snapshot(self.share())
            except Exception as exc:
                share_snapshot = {"jobs": [], "workers": [], "error": str(exc)}
            gpus, gpu_message = query_gpus()
            return {
                "config": self.config,
                "status": self.status,
                "code_signature": CODE_SIGNATURE,
                "worker_running": self.worker_running(),
                "monitor_running": self.monitor_running(),
                "monitor_url": self.monitor_url(),
                "health": self.health(),
                "queue": share_snapshot,
                "gpus": gpus,
                "gpu_message": gpu_message,
                "worker_log": list(self.worker_log)[-400:],
            }


class AppV2Handler(BaseHTTPRequestHandler):
    state: AppV2State

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            response_json(self, self.state.snapshot())
            return
        if parsed.path == "/api/monitor-url":
            response_json(self, {"url": self.state.monitor_url()})
            return
        self.send_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        payload = {}
        if length:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if parsed.path == "/api/config":
            self.state.update_config(payload)
            response_json(self, {"ok": True})
            return
        if parsed.path == "/api/action":
            self.handle_action(payload)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_action(self, payload: dict[str, object]) -> None:
        action = str(payload.get("action", ""))
        if action == "start":
            self.state.start()
            response_json(self, {"ok": True})
        elif action == "stop":
            self.state.stop()
            response_json(self, {"ok": True})
        elif action == "open_dashboard":
            response_json(self, {"ok": True, "url": self.state.monitor_url()})
        elif action == "open_queue":
            queue = Path(str(self.state.config["share"]))
            queue.mkdir(parents=True, exist_ok=True)
            os.startfile(str(queue)) if os.name == "nt" else webbrowser.open(queue.as_uri())
            response_json(self, {"ok": True})
        elif action == "repair":
            result = repair_queue(self.state.share(), min_output_age_seconds=0)
            response_json(self, {"ok": True, "repair": result})
        elif action == "repair_job":
            job_id = str(payload.get("job_id", ""))
            result = repair_queue(self.state.share(), job_id or None, min_output_age_seconds=0)
            response_json(self, {"ok": True, "repair": result})
        elif action in {"worker_restart", "worker_toggle_stop", "worker_stop_now"}:
            worker_id = str(payload.get("worker_id", ""))
            if not worker_id:
                response_json(self, {"ok": False, "message": "Missing worker id."}, HTTPStatus.BAD_REQUEST)
                return
            if action == "worker_restart":
                request_worker_restart(self.state.share(), worker_id)
            elif action == "worker_stop_now":
                request_worker_stop_now(self.state.share(), worker_id)
            else:
                if worker_stop_requested(self.state.share(), worker_id):
                    clear_worker_stop_request(self.state.share(), worker_id)
                else:
                    request_worker_stop_after_batch(self.state.share(), worker_id)
            response_json(self, {"ok": True})
        elif action in {"pause", "resume", "drain", "cancel", "delete", "requeue", "open_output"}:
            job_id = str(payload.get("job_id", ""))
            if not job_id:
                response_json(self, {"ok": False, "message": "Missing job id."}, HTTPStatus.BAD_REQUEST)
                return
            if action == "pause":
                set_job_status(self.state.share(), job_id, "paused")
            elif action == "resume":
                set_job_status(self.state.share(), job_id, "queued")
            elif action == "drain":
                set_job_status(self.state.share(), job_id, "draining")
            elif action == "cancel":
                set_job_status(self.state.share(), job_id, "cancelled")
            elif action == "delete":
                set_job_status(self.state.share(), job_id, "archived")
            elif action == "requeue":
                requeue_failed(self.state.share(), job_id)
            elif action == "open_output":
                self.state.open_output_folder(job_id)
            response_json(self, {"ok": True})
        elif action == "reorder":
            job_ids = payload.get("job_ids", [])
            if not isinstance(job_ids, list) or not job_ids:
                response_json(self, {"ok": False, "message": "Missing job order."}, HTTPStatus.BAD_REQUEST)
                return
            set_job_priorities(self.state.share(), [str(job_id) for job_id in job_ids])
            response_json(self, {"ok": True})
        elif action == "install_plugin":
            ok, message = self.state.install_plugin()
            response_json(self, {"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
        else:
            self.send_error(HTTPStatus.BAD_REQUEST, "Unknown action")

    def send_static(self, request_path: str) -> None:
        parsed = urlparse(request_path)
        clean_path = parsed.path
        path = STATIC_DIR / ("index.html" if clean_path in {"", "/"} else clean_path.lstrip("/"))
        try:
            resolved = path.resolve()
            if STATIC_DIR.resolve() not in resolved.parents and resolved != STATIC_DIR.resolve():
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not resolved.exists() or not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = "text/html; charset=utf-8"
            if resolved.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif resolved.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            body = resolved.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


def run_app_v2(host: str = "127.0.0.1", port: int = 8777, open_browser: bool = True) -> None:
    state = AppV2State()
    handler = type("DreamRenderAppV2Handler", (AppV2Handler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"DreamRender App v2 running at {url}", flush=True)
    try:
        server.serve_forever()
    finally:
        state.stop()


def main() -> None:
    run_app_v2()
