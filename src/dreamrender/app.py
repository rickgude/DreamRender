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
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Frame, StringVar, Text, Tk, filedialog, messagebox
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
        self.root.geometry("1100x880")
        self.root.minsize(980, 820)
        self.root.configure(bg="#edf3ef")

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

        self.configure_style()
        self.build_ui()
        self.adopt_existing_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.refresh_status)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=22, style="App.TFrame")
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill=X, pady=(0, 16))
        title_area = ttk.Frame(header, style="App.TFrame")
        title_area.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(title_area, text="DreamRender", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_area,
            text="Small-studio render farm control for Cinema 4D, Redshift, and Octane.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Button(header, text="Open Dashboard", command=self.open_dashboard, style="Ghost.TButton").pack(side=RIGHT, padx=(8, 0))
        ttk.Button(header, textvariable=self.start_button_text, command=self.toggle_dreamrender, style="Accent.TButton").pack(side=RIGHT)

        states = ttk.Frame(outer, style="App.TFrame")
        states.pack(fill=X, pady=(0, 14))
        self.status_card(states, "Worker", self.worker_state).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self.status_card(states, "Monitor", self.monitor_state).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self.status_card(states, "Status", self.status).pack(side=LEFT, fill=X, expand=True)

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill=BOTH, expand=True)

        left = ttk.Frame(content, style="App.TFrame")
        left.pack(side=LEFT, fill=BOTH, expand=False, padx=(0, 14))
        right = ttk.Frame(content, style="App.TFrame")
        right.pack(side=LEFT, fill=BOTH, expand=True)

        setup = self.card(left, "Setup")
        setup.pack(fill=X, pady=(0, 14))
        self.path_row(setup, "Queue", self.share, self.pick_share)
        self.path_row(setup, "Cinema 4D", self.c4d, self.pick_c4d)
        self.worker_row(setup)
        self.entry_row(setup, "Chunk size", self.chunk_size)
        self.entry_row(setup, "Monitor port", self.monitor_port)
        ttk.Checkbutton(setup, text="Keep worker running", variable=self.keep_worker_running, command=self.persist, style="App.TCheckbutton").pack(anchor="w", pady=(8, 0))

        actions = self.card(left, "Controls")
        actions.pack(fill=X)
        controls_grid = ttk.Frame(actions, style="Card.TFrame")
        controls_grid.pack(fill=X)
        controls = (
            ("Start Monitor", self.start_monitor, "App.TButton"),
            ("Open Queue Folder", self.open_queue_folder, "App.TButton"),
            ("Desktop Shortcut", self.create_desktop_shortcut, "App.TButton"),
            ("Run Diagnostics", self.run_doctor, "App.TButton"),
            ("Stop All", self.stop_all, "Danger.TButton"),
        )
        for index, (label, command, style_name) in enumerate(controls):
            row = index // 2
            column = index % 2
            ttk.Button(controls_grid, text=label, command=command, style=style_name).grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 8) if column == 0 else (0, 0),
                pady=(0, 8) if row < 1 else (0, 0),
            )
        controls_grid.columnconfigure(0, weight=1)
        controls_grid.columnconfigure(1, weight=1)

        queue_card = self.card(right, "Queue")
        queue_card.pack(fill=X, pady=(0, 14))
        self.summary = ttk.Label(queue_card, text="", justify=LEFT, style="Body.TLabel")
        self.summary.pack(anchor="w", fill=X)

        log_card = self.card(right, "Worker Log", actions=(("Copy Log", self.copy_log),))
        log_card.pack(fill=BOTH, expand=True)
        log_frame = ttk.Frame(log_card, style="Card.TFrame")
        log_frame.pack(fill=BOTH, expand=True)
        self.log = Text(
            log_frame,
            height=14,
            wrap="none",
            relief="flat",
            borderwidth=0,
            background="#f6faf7",
            foreground="#0f1111",
            insertbackground="#0f1111",
            selectbackground="#cfe8dc",
            selectforeground="#0f1111",
            font=("Consolas", 9),
        )
        log_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_x = ttk.Scrollbar(log_card, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=log_y.set, xscrollcommand=log_x.set, state="disabled")
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        log_y.pack(side=RIGHT, fill="y")
        log_x.pack(fill=X, pady=(6, 0))

    def configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        bg = "#edf3ef"
        card = "#fbfdfb"
        text = "#0f1111"
        muted = "#66736f"
        line = "#dce5df"
        accent = "#0f1111"
        style.configure("App.TFrame", background=bg)
        style.configure("Card.TFrame", background=card, relief="flat")
        style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI", 24, "bold"))
        style.configure("Subtle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=card, foreground=text, font=("Segoe UI", 12, "bold"))
        style.configure("Body.TLabel", background=card, foreground=text, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=card, foreground=muted, font=("Segoe UI", 9))
        style.configure("StatusValue.TLabel", background=card, foreground=text, font=("Segoe UI", 11, "bold"))
        style.configure("App.TEntry", fieldbackground="#f4f7f5", foreground=text, bordercolor=line, lightcolor=line, darkcolor=line, padding=6)
        style.configure("App.TCheckbutton", background=card, foreground=text, font=("Segoe UI", 10))
        style.configure("App.TButton", padding=(12, 8), font=("Segoe UI", 10, "bold"), background="#f4f7f5", foreground=text, bordercolor=line)
        style.configure("Ghost.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"), background="#f7faf8", foreground=text, bordercolor=line)
        style.configure("Accent.TButton", padding=(16, 10), font=("Segoe UI", 10, "bold"), background=accent, foreground="#ffffff", bordercolor=accent)
        style.map("Accent.TButton", background=[("active", "#2a2d2d")], foreground=[("active", "#ffffff")])
        style.configure("Danger.TButton", padding=(12, 8), font=("Segoe UI", 10, "bold"), background="#ffe7df", foreground="#9a2c18", bordercolor="#ffc7b8")

    def card(self, parent: Frame, title: str, actions=None) -> ttk.Frame:
        wrapper = ttk.Frame(parent, padding=16, style="Card.TFrame")
        header = ttk.Frame(wrapper, style="Card.TFrame")
        header.pack(fill=X, pady=(0, 12))
        ttk.Label(header, text=title, style="CardTitle.TLabel").pack(side=LEFT)
        for label, command in actions or ():
            ttk.Button(header, text=label, command=command, style="App.TButton").pack(side=RIGHT)
        return wrapper

    def status_card(self, parent: Frame, title: str, variable: StringVar) -> ttk.Frame:
        wrapper = ttk.Frame(parent, padding=14, style="Card.TFrame")
        ttk.Label(wrapper, text=title.upper(), style="Muted.TLabel").pack(anchor="w")
        ttk.Label(wrapper, textvariable=variable, style="StatusValue.TLabel").pack(anchor="w", pady=(4, 0))
        return wrapper

    def path_row(self, parent: Frame, label: str, variable: StringVar, command) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text=label, style="Muted.TLabel").pack(anchor="w")
        field = ttk.Frame(row, style="Card.TFrame")
        field.pack(fill=X, pady=(3, 0))
        ttk.Entry(field, textvariable=variable, style="App.TEntry").pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(field, text="Browse", command=command, style="App.TButton").pack(side=RIGHT)

    def entry_row(self, parent: Frame, label: str, variable: StringVar) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text=label, style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(row, textvariable=variable, style="App.TEntry").pack(fill=X, pady=(3, 0))

    def worker_row(self, parent: Frame) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text="Worker", style="Muted.TLabel").pack(anchor="w")
        field = ttk.Frame(row, style="Card.TFrame")
        field.pack(fill=X, pady=(3, 0))
        ttk.Entry(field, textvariable=self.worker_id, style="App.TEntry").pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(field, text="Use Computer Name", command=self.use_computer_name, style="App.TButton").pack(side=RIGHT)

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

    def toggle_dreamrender(self) -> None:
        if self.worker_is_running():
            self.stop_all()
        else:
            self.start_all()

    def start_all(self) -> None:
        self.init_queue(silent=True)
        self.start_monitor(open_browser=False)
        self.start_worker()

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
        self.update_start_button()
        threading.Thread(target=self.read_worker_log, args=(self.worker_process,), daemon=True).start()

    def read_worker_log(self, process: subprocess.Popen[str]) -> None:
        if not process.stdout:
            return
        for line in process.stdout:
            self.root.after(0, self.add_log, line.strip())

    def add_log(self, line: str) -> None:
        if not line:
            return
        self.log.configure(state="normal")
        self.log.insert(END, line + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 1000:
            self.log.delete("1.0", "%d.0" % (lines - 1000))
        self.log.see(END)
        self.log.configure(state="disabled")

    def copy_log(self) -> None:
        text = self.log.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Worker log copied to clipboard")

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
        self.update_start_button()

    def start_monitor(self, open_browser: bool = True) -> None:
        if self.monitor_process and self.monitor_process.poll() is None:
            if open_browser:
                self.open_dashboard()
            return
        self.persist()
        try:
            if self.monitor_is_reachable():
                self.monitor_state.set(f"Monitor: running on port {self.monitor_port.get()}")
                self.update_start_button()
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
            self.update_start_button()
            if open_browser:
                self.open_dashboard()
        except Exception as exc:
            messagebox.showerror("DreamRender", f"Could not start monitor:\n{exc}")

    def open_dashboard(self) -> None:
        webbrowser.open(f"http://127.0.0.1:{self.monitor_port.get()}")

    def run_doctor(self) -> None:
        results = doctor_share(Share(Path(self.share.get())))
        message = "\n".join(f"{'OK' if ok else 'FAIL'}  {label}: {detail}" for label, ok, detail in results)
        messagebox.showinfo("DreamRender Diagnostics", message)

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
        launcher = Path(__file__).resolve().parents[2] / "scripts" / "START_DreamRender_App.bat"
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

    def update_start_button(self) -> None:
        if self.worker_is_running():
            self.start_button_text.set("Stop DreamRender")
        else:
            self.start_button_text.set("Start DreamRender")

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
        self.update_start_button()
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
        self.update_start_button()

    def refresh_status(self) -> None:
        try:
            if self.worker_process and self.worker_process.poll() is not None:
                exit_code = self.worker_process.returncode
                self.worker_process = None
                self.worker_state.set("Worker: stopped")
                self.update_start_button()
                self.status.set(f"Worker exited with code {exit_code}")
                self.add_log(f"Worker exited with code {exit_code}")
                self.worker_restart_after = time.time() + 3
            elif self.adopted_worker_pid is not None and not self.process_exists(self.adopted_worker_pid):
                self.add_log(f"Adopted worker process {self.adopted_worker_pid} exited")
                self.adopted_worker_pid = None
                self.worker_state.set("Worker: stopped")
                self.update_start_button()
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
            self.update_start_button()
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
