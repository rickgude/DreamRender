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
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Canvas, Frame, PhotoImage, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk

from .queue import (
    Share,
    clear_worker_stop_request,
    doctor_share,
    queue_snapshot,
    request_worker_stop_after_batch,
    worker_stop_requested,
)


CONFIG_PATH = Path.home() / "DreamRenderApp.json"
DEFAULT_SHARE = Path(__file__).resolve().parents[2] / "DreamRenderShare"
DEFAULT_C4D = Path(r"C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe")
WINDOW_BG = "#e9e9e7"
APP_BG = "#f4f8f7"
CARD_BG = "#fbfcfa"
PANEL_BG = "#eef5f2"
TEXT = "#0f1111"
MUTED = "#737a7c"
ORANGE = "#ff8b3d"
CORAL = "#ff5538"
OUTLINE = "#dbe5e1"
START_COLOR = "#0e0e0d"
STOP_COLOR = "#65cd8b"
STOP_ALL_COLOR = "#ed7884"
DEFAULT_BUTTON = "#f8faf8"
IMAGE_CACHE: dict[tuple[int, int, int, str, str, str], PhotoImage] = {}
GPU_GREEN = "#65cd8b"
GPU_PURPLE = "#8b63f6"
GPU_ORANGE = "#ff7359"
GPU_YELLOW = "#ffd63f"
GPU_COLORS = (GPU_GREEN, GPU_PURPLE, GPU_ORANGE, GPU_YELLOW)


def load_config() -> dict[str, object]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict[str, object]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


class RoundedCard(Frame):
    def __init__(self, parent: Frame, radius: int = 26, padding: int = 18, fill: str = CARD_BG) -> None:
        super().__init__(parent, background=APP_BG, borderwidth=0, highlightthickness=0)
        self.radius = radius
        self.padding = padding
        self.fill = fill
        self.image: PhotoImage | None = None
        self.canvas = Canvas(self, background=APP_BG, borderwidth=0, highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.content = ttk.Frame(self.canvas, padding=padding, style="Card.TFrame")
        self.window_id = self.canvas.create_window(padding, padding, anchor="nw", window=self.content)
        self.content.bind("<Configure>", self.sync_size)
        self.bind("<Configure>", self.redraw)

    def sync_size(self, _event=None) -> None:
        width = max(1, self.content.winfo_reqwidth() + self.padding * 2)
        height = max(1, self.content.winfo_reqheight() + self.padding * 2)
        self.canvas.configure(width=width, height=height)
        self.redraw()

    def redraw(self, _event=None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.canvas.delete("card")
        self.image = rounded_rect_image(width, height, self.radius, self.fill, OUTLINE, APP_BG)
        self.canvas.create_image(0, 0, anchor="nw", image=self.image, tags="card")
        self.canvas.coords(self.window_id, self.padding, self.padding)
        self.canvas.itemconfigure(
            self.window_id,
            width=max(1, width - self.padding * 2),
            height=max(1, height - self.padding * 2),
        )
        self.canvas.tag_lower("card")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def blend(foreground: tuple[int, int, int], background: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    alpha = max(0.0, min(1.0, alpha))
    return tuple(int(round(foreground[index] * alpha + background[index] * (1.0 - alpha))) for index in range(3))


def rounded_rect_image(width: int, height: int, radius: int, fill: str, outline: str, background: str) -> PhotoImage:
    width = max(2, int(width))
    height = max(2, int(height))
    radius = max(1, min(int(radius), width // 2, height // 2))
    key = (width, height, radius, fill, outline, background)
    cached = IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    if len(IMAGE_CACHE) > 128:
        IMAGE_CACHE.clear()

    scale = 3
    border = 1.0
    fill_rgb = hex_to_rgb(fill)
    outline_rgb = hex_to_rgb(outline)
    background_rgb = hex_to_rgb(background)

    fill_bytes = bytes(fill_rgb)
    outline_bytes = bytes(outline_rgb)
    data = bytearray(fill_bytes * (width * height))

    def set_pixel(x: int, y: int, color: tuple[int, int, int] | bytes) -> None:
        offset = (y * width + x) * 3
        data[offset : offset + 3] = color

    for x in range(radius, width - radius):
        set_pixel(x, 0, outline_bytes)
        set_pixel(x, height - 1, outline_bytes)
    for y in range(radius, height - radius):
        set_pixel(0, y, outline_bytes)
        set_pixel(width - 1, y, outline_bytes)

    corners = (
        (radius - 0.5, radius - 0.5, 0, 0),
        (width - radius - 0.5, radius - 0.5, width - radius, 0),
        (radius - 0.5, height - radius - 0.5, 0, height - radius),
        (width - radius - 0.5, height - radius - 0.5, width - radius, height - radius),
    )
    outer_radius = radius - 0.45
    inner_radius = max(0.0, outer_radius - border)
    total = scale * scale
    for center_x, center_y, start_x, start_y in corners:
        for y in range(start_y, min(start_y + radius, height)):
            for x in range(start_x, min(start_x + radius, width)):
                outline_samples = 0
                fill_samples = 0
                for sy in range(scale):
                    py = y + (sy + 0.5) / scale
                    for sx in range(scale):
                        px = x + (sx + 0.5) / scale
                        distance = ((px - center_x) ** 2 + (py - center_y) ** 2) ** 0.5
                        if distance <= outer_radius:
                            outline_samples += 1
                        if distance <= inner_radius:
                            fill_samples += 1
                outline_alpha = outline_samples / total
                fill_alpha = fill_samples / total
                color = blend(outline_rgb, background_rgb, outline_alpha)
                if fill_alpha:
                    color = blend(fill_rgb, color, fill_alpha)
                set_pixel(x, y, color)

    if width > radius * 2 and height > 2:
        for x in range(radius, width - radius):
            set_pixel(x, 1, fill_bytes)
            set_pixel(x, height - 2, fill_bytes)
    if height > radius * 2 and width > 2:
        for y in range(radius, height - radius):
            set_pixel(1, y, fill_bytes)
            set_pixel(width - 2, y, fill_bytes)

    ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(data)
    image = PhotoImage(data=ppm, format="PPM")
    IMAGE_CACHE[key] = image
    return image


class PillButton(Frame):
    def __init__(
        self,
        parent: Frame,
        text: str | None = None,
        command=None,
        textvariable: StringVar | None = None,
        fill: str = DEFAULT_BUTTON,
        active_fill: str | None = None,
        foreground: str = TEXT,
        canvas_bg: str = CARD_BG,
    ) -> None:
        super().__init__(parent, background=canvas_bg, borderwidth=0, highlightthickness=0)
        self.command = command
        self.text = text or ""
        self.textvariable = textvariable
        self.fill = fill
        self.active_fill = active_fill or fill
        self.current_fill = fill
        self.foreground = foreground
        self.width = self.preferred_width()
        self.image: PhotoImage | None = None
        self.canvas = Canvas(self, height=40, background=canvas_bg, borderwidth=0, highlightthickness=0)
        self.canvas.configure(width=self.width)
        self.canvas.pack(fill=BOTH, expand=True)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.canvas.bind("<Button-1>", self.invoke)
        self.canvas.bind("<Enter>", self.on_enter)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<Configure>", self.redraw)
        if self.textvariable is not None:
            self.textvariable.trace_add("write", lambda *_: self.on_text_changed())
        self.configure(width=self.width, height=40)

    def label(self) -> str:
        return self.textvariable.get() if self.textvariable is not None else self.text

    def preferred_width(self) -> int:
        return max(96, len(self.label()) * 8 + 34)

    def on_text_changed(self) -> None:
        self.width = self.preferred_width()
        self.configure(width=self.width)
        self.canvas.configure(width=self.width)
        self.redraw()

    def on_enter(self, _event=None) -> None:
        self.current_fill = self.active_fill
        self.redraw()

    def on_leave(self, _event=None) -> None:
        self.current_fill = self.fill
        self.redraw()

    def set_colors(self, fill: str, foreground: str, active_fill: str | None = None) -> None:
        self.fill = fill
        self.active_fill = active_fill or fill
        self.current_fill = fill
        self.foreground = foreground
        self.redraw()

    def invoke(self, _event=None) -> None:
        if self.command:
            self.command()

    def redraw(self, _event=None) -> None:
        width = max(self.width, self.winfo_width())
        height = max(38, self.winfo_height())
        self.canvas.delete("button")
        self.image = rounded_rect_image(width, height, height // 2, self.current_fill, OUTLINE, str(self.canvas.cget("background")))
        self.canvas.create_image(0, 0, anchor="nw", image=self.image, tags="button")
        self.canvas.create_text(
            width // 2,
            height // 2,
            text=self.label(),
            fill=self.foreground,
            font=("Segoe UI", 10, "bold"),
            tags="button",
        )


class GpuActivityGraph(Canvas):
    def __init__(self, parent: Frame) -> None:
        super().__init__(parent, height=170, background=CARD_BG, borderwidth=0, highlightthickness=0)
        self.samples: dict[int, deque[int]] = {}
        self.gpus: list[dict[str, object]] = []
        self.message = "Waiting for GPU data..."
        self.bind("<Configure>", lambda _event=None: self.redraw())

    def update_gpus(self, gpus: list[dict[str, object]], message: str | None = None) -> None:
        self.gpus = gpus
        self.message = message or ""
        for gpu in gpus:
            index = int(gpu["index"])
            history = self.samples.setdefault(index, deque(maxlen=90))
            history.append(int(gpu["util"]))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(280, self.winfo_width())
        if not self.gpus:
            self.create_text(
                0,
                22,
                anchor="w",
                text=self.message or "No GPU data available.",
                fill=MUTED,
                font=("Segoe UI", 10),
            )
            return

        row_height = 78
        gap = 14
        needed_height = len(self.gpus) * row_height + max(0, len(self.gpus) - 1) * gap
        self.configure(height=needed_height)
        for row, gpu in enumerate(self.gpus):
            top = row * (row_height + gap)
            self.draw_gpu(row, gpu, 0, top, width, row_height)

    def draw_gpu(self, row: int, gpu: dict[str, object], x: int, y: int, width: int, height: int) -> None:
        color = GPU_COLORS[row % len(GPU_COLORS)]
        util = int(gpu["util"])
        mem_used = int(gpu["memory_used"])
        mem_total = max(1, int(gpu["memory_total"]))
        label = f"GPU {gpu['index']}  {gpu['name']}"
        stats = f"{util}% load  ·  {mem_used}/{mem_total} MB VRAM"
        self.create_text(x, y, anchor="nw", text=label, fill=TEXT, font=("Segoe UI", 10, "bold"))
        self.create_text(width - 4, y, anchor="ne", text=stats, fill=MUTED, font=("Segoe UI", 9))

        graph_top = y + 26
        graph_height = height - 28
        graph_width = max(80, width - 2)
        self.create_rectangle(
            x,
            graph_top,
            x + graph_width,
            graph_top + graph_height,
            fill=PANEL_BG,
            outline="",
        )
        for tick in (25, 50, 75):
            tick_y = graph_top + graph_height - (graph_height * tick / 100)
            self.create_line(x, tick_y, x + graph_width, tick_y, fill="#dde7e3")

        history = list(self.samples.get(int(gpu["index"]), []))
        if not history:
            return
        if len(history) == 1:
            history.append(history[0])
        step = graph_width / max(1, len(history) - 1)
        points: list[float] = []
        for index, value in enumerate(history):
            px = x + index * step
            py = graph_top + graph_height - (graph_height * max(0, min(100, value)) / 100)
            points.extend([px, py])
        area = [x, graph_top + graph_height, *points, x + (len(history) - 1) * step, graph_top + graph_height]
        self.create_polygon(area, fill=color, outline="", stipple="gray50")
        self.create_line(points, fill=color, width=3, smooth=True)
        self.create_oval(points[-2] - 4, points[-1] - 4, points[-2] + 4, points[-1] + 4, fill=color, outline="")


class DreamRenderApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("DreamRender")
        self.root.geometry("1100x1000")
        self.root.minsize(980, 820)
        self.root.configure(bg=WINDOW_BG)

        config = load_config()
        self.share = StringVar(value=str(config.get("share", DEFAULT_SHARE)))
        self.c4d = StringVar(value=str(config.get("c4d", DEFAULT_C4D)))
        self.worker_id = StringVar(value=str(config.get("worker_id", socket.gethostname())))
        self.chunk_size = StringVar(value=str(config.get("chunk_size", 5)))
        self.monitor_port = StringVar(value=str(config.get("monitor_port", 8766)))
        self.keep_worker_running = BooleanVar(value=bool(config.get("keep_worker_running", True)))
        self.quit_after_batch = BooleanVar(value=False)
        self.status = StringVar(value="Ready")
        self.worker_state = StringVar(value="Worker: stopped")
        self.monitor_state = StringVar(value="Monitor: stopped")
        self.start_button_text = StringVar(value="Start DreamRender")

        self.worker_process: subprocess.Popen[str] | None = None
        self.adopted_worker_pid: int | None = None
        self.monitor_process: subprocess.Popen[str] | None = None
        self.worker_should_run = False
        self.worker_restart_after = 0.0
        self.gpu_poll_running = False
        self.nvidia_smi = self.find_nvidia_smi()

        self.configure_style()
        self.build_ui()
        self.adopt_existing_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.refresh_status)
        self.root.after(500, self.refresh_gpu_activity)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=22, style="App.TFrame")
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill=X, pady=(0, 16))
        title_area = ttk.Frame(header, style="App.TFrame")
        title_area.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(title_area, text="DREAMRENDER", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_area,
            text="Small-studio render farm control for Cinema 4D, Redshift, and Octane.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        self.pill_button(header, text="Open Dashboard", command=self.open_dashboard, canvas_bg=APP_BG).pack(side=RIGHT, padx=(8, 0))
        self.start_button = self.pill_button(
            header,
            textvariable=self.start_button_text,
            command=self.toggle_dreamrender,
            fill=START_COLOR,
            active_fill="#2a2d2d",
            foreground="#ffffff",
            canvas_bg=APP_BG,
        )
        self.start_button.pack(side=RIGHT)

        states = ttk.Frame(outer, style="App.TFrame")
        states.pack(fill=X, pady=(0, 14))
        self.status_card(states, "Worker", self.worker_state).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self.status_card(states, "Monitor", self.monitor_state).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self.status_card(states, "Status", self.status).pack(side=LEFT, fill=X, expand=True)

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill=BOTH, expand=True)
        content.columnconfigure(0, minsize=430, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = ttk.Frame(content, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")

        setup = self.card(left, "Setup")
        setup.pack(fill=X, pady=(0, 14))
        self.path_row(setup, "Queue", self.share, self.pick_share)
        self.path_row(setup, "Cinema 4D", self.c4d, self.pick_c4d)
        self.worker_row(setup)
        self.entry_row(setup, "Chunk size", self.chunk_size)
        self.entry_row(setup, "Monitor port", self.monitor_port)
        ttk.Checkbutton(self.card_content(setup), text="Keep worker running", variable=self.keep_worker_running, command=self.persist, style="App.TCheckbutton").pack(anchor="w", pady=(8, 0))

        actions = self.card(left, "Controls")
        actions.pack(fill=X)
        actions_body = self.card_content(actions)
        ttk.Checkbutton(actions_body, text="Quit After Batch", variable=self.quit_after_batch, command=self.toggle_quit_after_batch, style="App.TCheckbutton").pack(anchor="w", pady=(0, 12))
        controls_grid = ttk.Frame(actions_body, style="Card.TFrame")
        controls_grid.pack(fill=X)
        controls = (
            ("Open Queue Folder", self.open_queue_folder, "App.TButton"),
            ("Desktop Shortcut", self.create_desktop_shortcut, "App.TButton"),
            ("Run Diagnostics", self.run_doctor, "App.TButton"),
            ("Stop All", self.stop_all, "Danger.TButton"),
        )
        for index, (label, command, style_name) in enumerate(controls):
            row = index // 2
            column = index % 2
            fill = STOP_ALL_COLOR if style_name == "Danger.TButton" else DEFAULT_BUTTON
            foreground = "#ffffff" if style_name == "Danger.TButton" else TEXT
            active_fill = "#f08d97" if style_name == "Danger.TButton" else PANEL_BG
            self.pill_button(
                controls_grid,
                text=label,
                command=command,
                fill=fill,
                active_fill=active_fill,
                foreground=foreground,
            ).grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 8) if column == 0 else (0, 0),
                pady=(0, 8) if row < 1 else (0, 0),
            )
        controls_grid.columnconfigure(0, weight=0)
        controls_grid.columnconfigure(1, weight=0)

        queue_card = self.card(right, "Queue")
        queue_card.pack(fill=X, pady=(0, 14))
        self.summary = ttk.Label(self.card_content(queue_card), text="", justify=LEFT, style="Body.TLabel")
        self.summary.pack(anchor="w", fill=X)

        gpu_card = self.card(right, "GPU Activity")
        gpu_card.pack(fill=X, pady=(0, 14))
        self.gpu_graph = GpuActivityGraph(self.card_content(gpu_card))
        self.gpu_graph.pack(fill=X, expand=True)

        log_card = self.card(right, "Worker Log", actions=(("Copy Log", self.copy_log),))
        log_card.pack(fill=BOTH, expand=True)
        log_body = self.card_content(log_card)
        log_frame = ttk.Frame(log_body, style="Card.TFrame")
        log_frame.pack(fill=BOTH, expand=True)
        self.log = Text(
            log_frame,
            height=14,
            wrap="none",
            relief="flat",
            borderwidth=0,
            background="#111111",
            foreground="#f6f2e8",
            insertbackground="#f6f2e8",
            selectbackground="#8b63f6",
            selectforeground="#ffffff",
            font=("Consolas", 9),
        )
        log_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_x = ttk.Scrollbar(log_body, orient="horizontal", command=self.log.xview)
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
        bg = APP_BG
        card = CARD_BG
        panel_2 = PANEL_BG
        text = TEXT
        muted = MUTED
        accent = TEXT
        orange = ORANGE
        coral = CORAL
        style.configure("App.TFrame", background=bg)
        style.configure("Card.TFrame", background=card, relief="flat", borderwidth=0)
        style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI", 25, "bold"))
        style.configure("Subtle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=card, foreground=muted, font=("Segoe UI", 9, "bold"))
        style.configure("Body.TLabel", background=card, foreground=text, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=card, foreground=muted, font=("Segoe UI", 9))
        style.configure("StatusValue.TLabel", background=card, foreground=text, font=("Segoe UI", 12, "bold"))
        style.configure(
            "App.TEntry",
            fieldbackground="#f7faf8",
            foreground=text,
            borderwidth=0,
            relief="flat",
            bordercolor="#f7faf8",
            lightcolor="#f7faf8",
            darkcolor="#f7faf8",
            insertcolor=text,
            padding=8,
        )
        style.configure("App.TCheckbutton", background=card, foreground=text, font=("Segoe UI", 10))
        style.map("App.TCheckbutton", background=[("active", card)], foreground=[("active", text)])
        style.configure("App.TButton", padding=(13, 9), font=("Segoe UI", 10, "bold"), background="#f8faf8", foreground=text, borderwidth=0, relief="flat", bordercolor="#f8faf8")
        style.map("App.TButton", background=[("active", panel_2)], bordercolor=[("active", panel_2)])
        style.configure("Ghost.TButton", padding=(15, 10), font=("Segoe UI", 10, "bold"), background="#fbfcfa", foreground=text, borderwidth=0, relief="flat", bordercolor="#fbfcfa")
        style.map("Ghost.TButton", background=[("active", panel_2)], bordercolor=[("active", panel_2)])
        style.configure("Accent.TButton", padding=(18, 11), font=("Segoe UI", 10, "bold"), background=accent, foreground="#ffffff", borderwidth=0, relief="flat", bordercolor=accent)
        style.map("Accent.TButton", background=[("active", "#2a2d2d")], foreground=[("active", "#ffffff")])
        style.configure("Danger.TButton", padding=(13, 9), font=("Segoe UI", 10, "bold"), background=coral, foreground="#ffffff", borderwidth=0, relief="flat", bordercolor=coral)
        style.map("Danger.TButton", background=[("active", orange)], foreground=[("active", "#ffffff")])

    def pill_button(
        self,
        parent: Frame,
        text: str | None = None,
        command=None,
        textvariable: StringVar | None = None,
        fill: str = DEFAULT_BUTTON,
        active_fill: str | None = None,
        foreground: str = TEXT,
        canvas_bg: str = CARD_BG,
    ) -> PillButton:
        return PillButton(
            parent,
            text=text,
            command=command,
            textvariable=textvariable,
            fill=fill,
            active_fill=active_fill,
            foreground=foreground,
            canvas_bg=canvas_bg,
        )

    def card(self, parent: Frame, title: str, actions=None) -> RoundedCard:
        wrapper = RoundedCard(parent, radius=28, padding=18, fill=CARD_BG)
        body = wrapper.content
        header = ttk.Frame(body, style="Card.TFrame")
        header.pack(fill=X, pady=(0, 12))
        ttk.Label(header, text=title.upper(), style="CardTitle.TLabel").pack(side=LEFT)
        for label, command in actions or ():
            self.pill_button(header, text=label, command=command).pack(side=RIGHT)
        return wrapper

    def card_content(self, parent: Frame) -> Frame:
        return getattr(parent, "content", parent)

    def status_card(self, parent: Frame, title: str, variable: StringVar) -> RoundedCard:
        wrapper = RoundedCard(parent, radius=22, padding=14, fill=CARD_BG)
        body = wrapper.content
        ttk.Label(body, text=title.upper(), style="Muted.TLabel").pack(anchor="w")
        ttk.Label(body, textvariable=variable, style="StatusValue.TLabel").pack(anchor="w", pady=(4, 0))
        return wrapper

    def path_row(self, parent: Frame, label: str, variable: StringVar, command) -> None:
        parent = self.card_content(parent)
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text=label, style="Muted.TLabel").pack(anchor="w")
        field = ttk.Frame(row, style="Card.TFrame")
        field.pack(fill=X, pady=(3, 0))
        ttk.Entry(field, textvariable=variable, style="App.TEntry", width=34).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.pill_button(field, text="Browse", command=command).pack(side=RIGHT)

    def entry_row(self, parent: Frame, label: str, variable: StringVar) -> None:
        parent = self.card_content(parent)
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text=label, style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(row, textvariable=variable, style="App.TEntry", width=34).pack(fill=X, pady=(3, 0))

    def worker_row(self, parent: Frame) -> None:
        parent = self.card_content(parent)
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text="Worker", style="Muted.TLabel").pack(anchor="w")
        field = ttk.Frame(row, style="Card.TFrame")
        field.pack(fill=X, pady=(3, 0))
        ttk.Entry(field, textvariable=self.worker_id, style="App.TEntry", width=34).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.pill_button(field, text="Use Computer Name", command=self.use_computer_name).pack(side=RIGHT)

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
        clear_worker_stop_request(Share(share), self.worker_id.get())
        self.quit_after_batch.set(False)
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
        clear_worker_stop_request(Share(Path(self.share.get())), self.worker_id.get())
        self.quit_after_batch.set(False)
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

    def toggle_quit_after_batch(self) -> None:
        share = Share(Path(self.share.get()))
        worker_id = self.worker_id.get()
        if self.quit_after_batch.get():
            request_worker_stop_after_batch(share, worker_id)
            self.worker_should_run = False
            self.status.set("Worker will quit after the current batch")
            self.add_log("Quit-after-batch requested")
        else:
            clear_worker_stop_request(share, worker_id)
            self.status.set("Quit-after-batch cancelled")
            self.add_log("Quit-after-batch cancelled")

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
            self.start_button.set_colors(STOP_COLOR, TEXT, "#74d898")
        else:
            self.start_button_text.set("Start DreamRender")
            self.start_button.set_colors(START_COLOR, "#ffffff", "#2a2d2d")

    def process_exists(self, pid: int) -> bool:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def find_nvidia_smi(self) -> str | None:
        found = shutil.which("nvidia-smi")
        if found:
            return found
        candidate = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
        return str(candidate) if candidate.exists() else None

    def refresh_gpu_activity(self) -> None:
        if not self.gpu_poll_running:
            self.gpu_poll_running = True
            threading.Thread(target=self.poll_gpu_activity, daemon=True).start()
        self.root.after(2000, self.refresh_gpu_activity)

    def poll_gpu_activity(self) -> None:
        try:
            gpus, message = self.query_gpu_activity()
            self.root.after(0, self.gpu_graph.update_gpus, gpus, message)
        finally:
            self.gpu_poll_running = False

    def query_gpu_activity(self) -> tuple[list[dict[str, object]], str | None]:
        if not self.nvidia_smi:
            return [], "NVIDIA GPU data is not available. Install NVIDIA drivers with nvidia-smi."
        command = [
            self.nvidia_smi,
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            return [], f"Could not read GPU data: {exc}"
        if result.returncode != 0:
            return [], result.stderr.strip() or "Could not read GPU data from nvidia-smi."
        gpus: list[dict[str, object]] = []
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
        return gpus, None if gpus else "No GPU data returned by nvidia-smi."

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
            self.quit_after_batch.set(worker_stop_requested(Share(Path(self.share.get())), self.worker_id.get()))
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
        clear_worker_stop_request(Share(Path(self.share.get())), self.worker_id.get())
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
