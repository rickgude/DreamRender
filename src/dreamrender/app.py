from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Frame, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from .queue import Share, doctor_share, queue_snapshot


CONFIG_PATH = Path.home() / "DreamRenderApp.json"
DEFAULT_SHARE = Path(__file__).resolve().parents[2] / "DreamRenderShare"
DEFAULT_C4D = Path(r"C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe")


def load_config() -> dict[str, object]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict[str, object]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


class DreamRenderApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("DreamRender")
        self.root.geometry("780x520")
        self.root.minsize(720, 480)

        config = load_config()
        self.share = StringVar(value=str(config.get("share", DEFAULT_SHARE)))
        self.c4d = StringVar(value=str(config.get("c4d", DEFAULT_C4D)))
        self.worker_id = StringVar(value=str(config.get("worker_id", socket.gethostname())))
        self.chunk_size = StringVar(value=str(config.get("chunk_size", 5)))
        self.monitor_port = StringVar(value=str(config.get("monitor_port", 8766)))
        self.keep_worker_running = BooleanVar(value=bool(config.get("keep_worker_running", True)))
        self.status = StringVar(value="Ready")
        self.worker_state = StringVar(value="Worker: stopped")
        self.monitor_state = StringVar(value="Monitor: stopped")
        self.start_button_text = StringVar(value="Start DreamRender")

        self.worker_process: subprocess.Popen[str] | None = None
        self.adopted_worker_pid: int | None = None
        self.monitor_process: subprocess.Popen[str] | None = None
        self.worker_should_run = False
        self.worker_restart_after = 0.0

        self.build_ui()
        self.adopt_existing_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.refresh_status)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=BOTH, expand=True)

        title = ttk.Label(outer, text="DreamRender Control", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")
        ttk.Label(outer, text="Start this machine as a render node, open the dashboard, and keep the queue healthy.").pack(anchor="w", pady=(2, 16))

        form = ttk.Frame(outer)
        form.pack(fill=X)
        self.path_row(form, "Queue", self.share, self.pick_share)
        self.path_row(form, "Cinema 4D", self.c4d, self.pick_c4d)
        self.worker_row(form)
        self.entry_row(form, "Chunk size", self.chunk_size)
        self.entry_row(form, "Monitor port", self.monitor_port)
        ttk.Checkbutton(form, text="Keep worker running", variable=self.keep_worker_running, command=self.persist).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=X, pady=14)
        ttk.Button(buttons, textvariable=self.start_button_text, command=self.start_all).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Start Worker", command=self.start_worker).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Stop Worker", command=self.stop_worker).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Start Monitor", command=self.start_monitor).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Open Dashboard", command=self.open_dashboard).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Doctor", command=self.run_doctor).pack(side=RIGHT)

        tools = ttk.Frame(outer)
        tools.pack(fill=X, pady=(0, 10))
        ttk.Button(tools, text="Initialize Queue", command=self.init_queue).pack(side=LEFT, padx=(0, 8))
        ttk.Button(tools, text="Open Queue Folder", command=self.open_queue_folder).pack(side=LEFT, padx=(0, 8))
        ttk.Button(tools, text="Create Desktop Shortcut", command=self.create_desktop_shortcut).pack(side=LEFT, padx=(0, 8))
        ttk.Button(tools, text="Stop All", command=self.stop_all).pack(side=RIGHT)

        ttk.Separator(outer).pack(fill=X, pady=10)
        states = ttk.Frame(outer)
        states.pack(fill=X, pady=(0, 8))
        ttk.Label(states, textvariable=self.worker_state, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 18))
        ttk.Label(states, textvariable=self.monitor_state, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        ttk.Label(outer, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        self.summary = ttk.Label(outer, text="", justify=LEFT)
        self.summary.pack(anchor="w", fill=X)

        self.log = ttk.Treeview(outer, columns=("message",), show="headings", height=10)
        self.log.heading("message", text="Worker log")
        self.log.column("message", anchor="w")
        self.log.pack(fill=BOTH, expand=True, pady=(12, 0))

    def path_row(self, parent: Frame, label: str, variable: StringVar, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=4)
        ttk.Label(row, text=label, width=12).pack(side=LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse", command=command).pack(side=RIGHT)

    def entry_row(self, parent: Frame, label: str, variable: StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=4)
        ttk.Label(row, text=label, width=12).pack(side=LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=LEFT, fill=X, expand=True)

    def worker_row(self, parent: Frame) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=4)
        ttk.Label(row, text="Worker", width=12).pack(side=LEFT)
        ttk.Entry(row, textvariable=self.worker_id).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(row, text="Use Computer Name", command=self.use_computer_name).pack(side=RIGHT)

    def use_computer_name(self) -> None:
        self.worker_id.set(socket.gethostname())
        self.persist()
        self.status.set(f"Worker name set to {self.worker_id.get()}")

    def pick_share(self) -> None:
        value = filedialog.askdirectory(title="Choose DreamRender queue folder")
        if value:
            self.share.set(value)
            self.persist()

    def pick_c4d(self) -> None:
        value = filedialog.askopenfilename(title="Choose Cinema 4D Commandline.exe", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if value:
            self.c4d.set(value)
            self.persist()

    def persist(self) -> None:
        save_config(
            {
                "share": self.share.get(),
                "c4d": self.c4d.get(),
                "worker_id": self.worker_id.get(),
                "chunk_size": self.chunk_size.get(),
                "monitor_port": self.monitor_port.get(),
                "keep_worker_running": self.keep_worker_running.get(),
            }
        )

    def python_command(self) -> list[str]:
        return [sys.executable, "-m", "dreamrender"]

    def start_all(self) -> None:
        self.init_queue(silent=True)
        self.start_monitor(open_browser=False)
        self.start_worker()
        self.open_dashboard()

    def start_worker(self, auto_restart: bool = False) -> None:
        if self.worker_is_running():
            if not auto_restart:
                messagebox.showinfo("DreamRender", "Worker is already running.")
            return
        self.persist()
        share = Path(self.share.get())
        c4d = Path(self.c4d.get())
        if not share.exists():
            if auto_restart:
                self.status.set("Worker restart paused: queue folder is missing")
                return
            if messagebox.askyesno("DreamRender", "Queue folder does not exist. Create it now?"):
                self.init_queue(silent=True)
            else:
                return
        if not c4d.exists():
            if auto_restart:
                self.status.set("Worker restart paused: Cinema 4D path is missing")
            else:
                messagebox.showerror("DreamRender", f"Cinema 4D Commandline.exe was not found:\n{c4d}")
            return
        command = self.python_command() + [
            "worker",
            "--share",
            self.share.get(),
            "--c4d",
            self.c4d.get(),
            "--worker-id",
            self.worker_id.get(),
            "--chunk-size",
            self.chunk_size.get(),
        ]
        self.worker_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.worker_should_run = True
        self.adopted_worker_pid = None
        self.status.set("Worker restarted" if auto_restart else "Worker started")
        self.worker_state.set(f"Worker: running as {self.worker_id.get()}")
        self.start_button_text.set("DreamRender Running")
        threading.Thread(target=self.read_worker_log, args=(self.worker_process,), daemon=True).start()

    def read_worker_log(self, process: subprocess.Popen[str]) -> None:
        if not process.stdout:
            return
        for line in process.stdout:
            self.root.after(0, self.add_log, line.strip())

    def add_log(self, line: str) -> None:
        if not line:
            return
        self.log.insert("", END, values=(line,))
        children = self.log.get_children()
        if len(children) > 200:
            self.log.delete(children[0])
        self.log.see(children[-1])

    def stop_worker(self) -> None:
        self.worker_should_run = False
        if self.worker_process and self.worker_process.poll() is None:
            self.stop_process_tree(self.worker_process)
            self.status.set("Worker stopped")
        elif self.adopted_worker_pid is not None:
            self.stop_pid_tree(self.adopted_worker_pid)
            self.status.set("Worker stopped")
        self.worker_process = None
        self.adopted_worker_pid = None
        self.worker_state.set("Worker: stopped")
        self.start_button_text.set("Start DreamRender")

    def start_monitor(self, open_browser: bool = True) -> None:
        if self.monitor_process and self.monitor_process.poll() is None:
            if open_browser:
                self.open_dashboard()
            return
        self.persist()
        try:
            if self.monitor_is_reachable():
                self.monitor_state.set(f"Monitor: running on port {self.monitor_port.get()}")
                if open_browser:
                    self.open_dashboard()
                return
            command = self.python_command() + ["monitor", "--share", self.share.get(), "--host", "127.0.0.1", "--port", self.monitor_port.get()]
            self.monitor_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            time.sleep(0.5)
            self.monitor_state.set(f"Monitor: running on port {self.monitor_port.get()}")
            if open_browser:
                self.open_dashboard()
        except Exception as exc:
            messagebox.showerror("DreamRender", f"Could not start monitor:\n{exc}")

    def open_dashboard(self) -> None:
        webbrowser.open(f"http://127.0.0.1:{self.monitor_port.get()}")

    def run_doctor(self) -> None:
        results = doctor_share(Share(Path(self.share.get())))
        message = "\n".join(f"{'OK' if ok else 'FAIL'}  {label}: {detail}" for label, ok, detail in results)
        messagebox.showinfo("DreamRender Doctor", message)

    def init_queue(self, silent: bool = False) -> None:
        share = Share(Path(self.share.get()))
        try:
            share.init()
            self.status.set(f"Queue ready: {share.root}")
            if not silent:
                messagebox.showinfo("DreamRender", f"Queue is ready:\n{share.root}")
        except Exception as exc:
            if silent:
                self.status.set(f"Could not initialize queue: {exc}")
            else:
                messagebox.showerror("DreamRender", f"Could not initialize queue:\n{exc}")

    def open_queue_folder(self) -> None:
        path = Path(self.share.get())
        if not path.exists():
            messagebox.showwarning("DreamRender", "Queue folder does not exist yet.")
            return
        os.startfile(path) if os.name == "nt" else webbrowser.open(path.as_uri())

    def create_desktop_shortcut(self) -> None:
        if os.name != "nt":
            messagebox.showinfo("DreamRender", "Desktop shortcut creation is currently Windows-only.")
            return
        launcher = Path(__file__).resolve().parents[2] / "scripts" / "start-dreamrender-app.bat"
        desktop = Path.home() / "Desktop" / "DreamRender.lnk"
        script = (
            "$shell = New-Object -ComObject WScript.Shell; "
            f"$shortcut = $shell.CreateShortcut('{desktop}'); "
            f"$shortcut.TargetPath = '{launcher}'; "
            f"$shortcut.WorkingDirectory = '{launcher.parent}'; "
            "$shortcut.IconLocation = 'shell32.dll,13'; "
            "$shortcut.Save()"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True, text=True)
            messagebox.showinfo("DreamRender", f"Desktop shortcut created:\n{desktop}")
        except Exception as exc:
            messagebox.showerror("DreamRender", f"Could not create shortcut:\n{exc}")

    def monitor_is_reachable(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(self.monitor_port.get())), timeout=0.25):
                return True
        except OSError:
            return False
        except ValueError:
            return False

    def stop_process_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        self.stop_pid_tree(process.pid)

    def stop_pid_tree(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass

    def worker_is_running(self) -> bool:
        if self.worker_process and self.worker_process.poll() is None:
            return True
        if self.adopted_worker_pid is not None and self.process_exists(self.adopted_worker_pid):
            return True
        self.adopted_worker_pid = None
        return False

    def process_exists(self, pid: int) -> bool:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def find_existing_worker_pid(self) -> int | None:
        if os.name != "nt":
            return None
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -like '*dreamrender worker*' } | "
            "Select-Object -Property ProcessId,CommandLine | ConvertTo-Json -Depth 3",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode != 0 or not result.stdout.strip():
                return None
            payload = json.loads(result.stdout)
        except Exception:
            return None
        rows = payload if isinstance(payload, list) else [payload]
        share = self.share.get()
        worker_id = self.worker_id.get()
        for row in rows:
            command_line = str(row.get("CommandLine", ""))
            normalized_command = " ".join(command_line.lower().split())
            if "-m dreamrender worker" not in normalized_command:
                continue
            if "--worker-id" not in command_line or worker_id not in command_line:
                continue
            if "--share" not in command_line or share not in command_line:
                continue
            try:
                return int(row["ProcessId"])
            except Exception:
                continue
        return None

    def adopt_existing_worker(self) -> None:
        pid = self.find_existing_worker_pid()
        if pid is None:
            return
        self.worker_process = None
        self.adopted_worker_pid = pid
        self.worker_should_run = True
        self.worker_state.set(f"Worker: running as {self.worker_id.get()} (adopted)")
        self.start_button_text.set("DreamRender Running")
        self.status.set(f"Adopted existing worker process {pid}")
        self.add_log(f"Adopted existing worker process {pid}")

    def stop_all(self) -> None:
        self.worker_should_run = False
        self.stop_worker()
        if self.monitor_process and self.monitor_process.poll() is None:
            self.stop_process_tree(self.monitor_process)
        self.monitor_process = None
        self.monitor_state.set("Monitor: stopped")
        self.status.set("DreamRender stopped")

    def refresh_status(self) -> None:
        try:
            if self.worker_process and self.worker_process.poll() is not None:
                exit_code = self.worker_process.returncode
                self.worker_process = None
                self.worker_state.set("Worker: stopped")
                self.start_button_text.set("Start DreamRender")
                self.status.set(f"Worker exited with code {exit_code}")
                self.add_log(f"Worker exited with code {exit_code}")
                self.worker_restart_after = time.time() + 3
            elif self.adopted_worker_pid is not None and not self.process_exists(self.adopted_worker_pid):
                self.add_log(f"Adopted worker process {self.adopted_worker_pid} exited")
                self.adopted_worker_pid = None
                self.worker_state.set("Worker: stopped")
                self.start_button_text.set("Start DreamRender")
                self.worker_restart_after = time.time() + 3
            elif self.adopted_worker_pid is None and self.worker_process is None:
                self.adopt_existing_worker()
            if (
                self.worker_should_run
                and self.keep_worker_running.get()
                and not self.worker_is_running()
                and time.time() >= self.worker_restart_after
            ):
                self.start_worker(auto_restart=True)
            if self.monitor_process and self.monitor_process.poll() is not None:
                self.monitor_process = None
                self.monitor_state.set("Monitor: stopped")
            elif self.monitor_is_reachable():
                self.monitor_state.set(f"Monitor: running on port {self.monitor_port.get()}")
            snapshot = queue_snapshot(Share(Path(self.share.get())))
            jobs = snapshot["jobs"]
            workers = snapshot["workers"]
            active = sum(1 for worker in workers if worker.get("state") == "online")
            if jobs:
                job = jobs[0]
                stats = job.get("stats", {})
                self.summary.config(
                    text=(
                        f"Workers online: {active}    "
                        f"Current job: {job['name']}    "
                        f"Progress: {job['progress']:.1f}%    "
                        f"Average: {stats.get('avg', '--')}    "
                        f"ETA: {stats.get('eta', '--')}"
                    )
                )
            else:
                self.summary.config(text=f"Workers online: {active}    No queued jobs.")
        except Exception as exc:
            self.summary.config(text=f"Queue status unavailable: {exc}")
        self.root.after(2500, self.refresh_status)

    def close(self) -> None:
        self.persist()
        self.worker_should_run = False
        if self.worker_process and self.worker_process.poll() is None:
            self.stop_process_tree(self.worker_process)
        elif self.adopted_worker_pid is not None and self.process_exists(self.adopted_worker_pid):
            self.stop_pid_tree(self.adopted_worker_pid)
        if self.monitor_process and self.monitor_process.poll() is None:
            self.stop_process_tree(self.monitor_process)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    DreamRenderApp().run()
