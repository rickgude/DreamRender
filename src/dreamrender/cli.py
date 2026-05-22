from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

from .queue import (
    DEFAULT_COMMAND_TEMPLATE,
    Share,
    ShareAccessError,
    claim_next_frames,
    clear_worker_restart_request,
    clear_worker_stop_request,
    doctor_share,
    heartbeat_worker,
    list_jobs,
    parse_frames,
    render_frames,
    repair_queue,
    requeue_failed,
    set_job_status,
    submit_job,
    summarize_job,
    worker_stop_requested,
    worker_stop_now_requested,
    worker_restart_requested,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dreamrender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_share = subparsers.add_parser("init-share", help="Create a DreamRender shared queue folder.")
    init_share.add_argument("--share", required=True, type=Path)

    submit = subparsers.add_parser("submit", help="Submit a Cinema 4D scene as a render job.")
    submit.add_argument("--share", required=True, type=Path)
    submit.add_argument("--scene", required=True, type=Path)
    submit.add_argument("--frames", required=True, help="Frame spec, for example 1-120 or 1,4,8-12.")
    submit.add_argument("--output", required=True, type=Path)
    submit.add_argument("--name")
    submit.add_argument("--copy-scene", action="store_true", help="Copy the .c4d file into the queue instead of preserving its original path.")

    worker = subparsers.add_parser("worker", help="Run a worker that claims and renders frames.")
    worker.add_argument("--share", required=True, type=Path)
    worker.add_argument("--c4d", required=True, type=Path)
    worker.add_argument("--worker-id", default=socket.gethostname())
    worker.add_argument("--poll-seconds", type=int, default=5)
    worker.add_argument("--heartbeat-seconds", type=int, default=10)
    worker.add_argument("--stale-seconds", type=int, default=600)
    worker.add_argument("--chunk-size", type=int, default=5, help="Number of contiguous frames to render per C4D launch.")
    worker.add_argument("--once", action="store_true", help="Render at most one frame and exit.")
    worker.add_argument("--command-template", default=DEFAULT_COMMAND_TEMPLATE)

    status = subparsers.add_parser("status", help="Show job and worker status.")
    status.add_argument("--share", required=True, type=Path)

    requeue = subparsers.add_parser("requeue-failed", help="Move failed frames back to queued.")
    requeue.add_argument("--share", required=True, type=Path)
    requeue.add_argument("--job-id")

    repair = subparsers.add_parser("repair", help="Repair stale/rendered frame states in the queue.")
    repair.add_argument("--share", required=True, type=Path)
    repair.add_argument("--job-id")

    monitor = subparsers.add_parser("monitor", help="Run the DreamRender dashboard.")
    monitor.add_argument("--share", required=True, type=Path)
    monitor.add_argument("--host", default="127.0.0.1")
    monitor.add_argument("--port", type=int, default=8765)

    job_status = subparsers.add_parser("set-job-status", help="Pause, resume, or cancel a job.")
    job_status.add_argument("--share", required=True, type=Path)
    job_status.add_argument("--job-id", required=True)
    job_status.add_argument("--status", required=True, choices=["queued", "paused", "cancelled", "draining"])

    doctor = subparsers.add_parser("doctor", help="Check whether this machine can use the DreamRender share.")
    doctor.add_argument("--share", required=True, type=Path)

    classic_app = subparsers.add_parser("classic-app", help="Launch the legacy Tkinter control panel.")

    app_v2 = subparsers.add_parser("app-v2", help="Launch the DreamRender App UI.")
    app_v2.add_argument("--host", default="127.0.0.1")
    app_v2.add_argument("--port", type=int, default=8777)
    app_v2.add_argument("--no-browser", action="store_true")

    return parser


def cmd_init_share(args: argparse.Namespace) -> int:
    share = Share(args.share)
    share.init()
    print(f"Initialized DreamRender share: {share.root}", flush=True)
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    share = Share(args.share)
    frames = parse_frames(args.frames)
    job_id = submit_job(
        share=share,
        scene=args.scene,
        frames=frames,
        output=args.output,
        name=args.name,
        copy_scene=args.copy_scene,
    )
    print(f"Submitted job {job_id} with {len(frames)} frame(s).", flush=True)
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    share = Share(args.share)
    worker_id = args.worker_id
    if not args.c4d.exists():
        print(f"Cinema 4D commandline executable not found: {args.c4d}", file=sys.stderr, flush=True)
        return 2

    try:
        print(f"DreamRender worker '{worker_id}' watching {share.root}", flush=True)
        while True:
            if worker_stop_requested(share, worker_id):
                restarting = worker_restart_requested(share, worker_id)
                stopping_now = worker_stop_now_requested(share, worker_id)
                label = "Restart requested." if restarting else "Stop requested." if stopping_now else "Quit-after-batch requested."
                print(label + " Worker is stopping before claiming new frames.", flush=True)
                clear_worker_restart_request(share, worker_id)
                clear_worker_stop_request(share, worker_id)
                return 75 if restarting else 76
            heartbeat_worker(share, worker_id)
            claim = claim_next_frames(share, worker_id, args.stale_seconds, args.chunk_size)
            if claim is None:
                if args.once:
                    print("No queued frames found.", flush=True)
                    return 0
                time.sleep(args.poll_seconds)
                continue

            job_dir, job, frame_paths = claim
            start_frame = int(frame_paths[0].stem)
            end_frame = int(frame_paths[-1].stem)
            frame_label = str(start_frame) if start_frame == end_frame else f"{start_frame}-{end_frame}"
            print(f"Rendering job {job['id']} frame(s) {frame_label}", flush=True)
            render_frames(
                share=share,
                c4d=args.c4d,
                command_template=args.command_template,
                worker_id=worker_id,
                job_dir=job_dir,
                job=job,
                frame_paths=frame_paths,
                heartbeat_interval=args.heartbeat_seconds,
            )
            if worker_stop_requested(share, worker_id):
                restarting = worker_restart_requested(share, worker_id)
                stopping_now = worker_stop_now_requested(share, worker_id)
                label = "Restart requested." if restarting else "Stop requested." if stopping_now else "Quit-after-batch requested."
                print(label + " Worker stopped after finishing the current batch.", flush=True)
                clear_worker_restart_request(share, worker_id)
                clear_worker_stop_request(share, worker_id)
                return 75 if restarting else 76
            if args.once:
                return 0
    except ShareAccessError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        print("Run: dreamrender doctor --share <same-share-path>", file=sys.stderr, flush=True)
        return 3


def cmd_status(args: argparse.Namespace) -> int:
    share = Share(args.share)
    jobs = list_jobs(share)
    if not jobs:
        print("No jobs found.", flush=True)
    for job_dir in jobs:
        summary = summarize_job(job_dir)
        counts = ", ".join(f"{key}: {value}" for key, value in sorted(summary["counts"].items()))
        print(f"{summary['id']}  {summary['name']}  {summary['progress']:.1f}%  {counts}", flush=True)

    workers = sorted(share.workers_dir.glob("*.json")) if share.workers_dir.exists() else []
    if workers:
        print("\nWorkers:", flush=True)
        for worker in workers:
            print(f"- {worker.stem}", flush=True)
    return 0


def cmd_requeue_failed(args: argparse.Namespace) -> int:
    changed = requeue_failed(Share(args.share), args.job_id)
    print(f"Requeued {changed} failed frame(s).", flush=True)
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    result = repair_queue(Share(args.share), args.job_id, min_output_age_seconds=0)
    print(
        f"Repaired {result['changed']} frame(s): "
        f"{result['outputs']} output-backed, {result['stale_failed']} stale failed.",
        flush=True,
    )
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    from .monitor import run_monitor

    run_monitor(Share(args.share), args.host, args.port)
    return 0


def cmd_set_job_status(args: argparse.Namespace) -> int:
    set_job_status(Share(args.share), args.job_id, args.status)
    print(f"Set job {args.job_id} to {args.status}.", flush=True)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    failed = False
    for label, ok, detail in doctor_share(Share(args.share)):
        mark = "OK" if ok else "FAIL"
        print(f"{mark:4} {label}  {detail}", flush=True)
        failed = failed or not ok
    return 1 if failed else 0


def cmd_app(args: argparse.Namespace) -> int:
    from .app import main as app_main

    app_main()
    return 0


def cmd_app_v2(args: argparse.Namespace) -> int:
    from .app_v2 import run_app_v2

    run_app_v2(args.host, args.port, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if argv and argv[0] == "app":
        argv[0] = "classic-app"
    args = parser.parse_args(argv)
    handlers = {
        "init-share": cmd_init_share,
        "submit": cmd_submit,
        "worker": cmd_worker,
        "status": cmd_status,
        "requeue-failed": cmd_requeue_failed,
        "repair": cmd_repair,
        "monitor": cmd_monitor,
        "set-job-status": cmd_set_job_status,
        "doctor": cmd_doctor,
        "classic-app": cmd_app,
        "app-v2": cmd_app_v2,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
