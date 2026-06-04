"""DreamRender Cinema 4D submit dialog.

The Cinema 4D plugin wrapper loads this module from the user's plugins folder.
It saves a render copy of the current document into a DreamRenderJobs folder near
the project, then creates a job in the shared DreamRender queue.
"""

from __future__ import annotations

import json
import os
import webbrowser
import uuid
from datetime import datetime, timezone

import c4d
from c4d import gui


DEFAULT_JOB_FOLDER = "DreamRenderJobs"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), "DreamRenderSubmit.json")
SUBMIT_HISTORY_FILENAME = "submit_history.json"
CACHE_EXTENSIONS = {".abc", ".vdb", ".rs", ".ass", ".usd", ".usda", ".usdc", ".bgeo", ".bgeo.sc"}

IDC_SHARE = 1001
IDC_NAME = 1002
IDC_OUTPUT = 1003
IDC_START = 1004
IDC_END = 1005
IDC_SUBMIT = 1006
IDC_CHUNK_SIZE = 1007
IDC_BROWSE_SHARE = 1008
IDC_OPEN_DASHBOARD = 1009
IDC_NOTES = 1010
IDC_MARKED_TAKES = 1011
IDC_CHECK_SCENE = 1014
IDC_CHECK_STATUS = 1016
IDC_CHECK_PROGRESS = 1019
IDC_CHECK_TABLE = 1020
IDC_IGNORE_WARNINGS = 1021
IDC_CONFIRM_SAVE = 1030
IDC_CONFIRM_CANCEL = 1031

CHECK_ERROR = "ERROR"
CHECK_WARNING = "WARNING"
CHECK_OK = "OK"


def default_share_path():
    home = os.path.expanduser("~")
    documents = os.path.join(home, "Documents")
    if os.path.isdir(documents):
        return os.path.join(documents, "DreamRenderShare")
    return os.path.join(home, "DreamRenderShare")


DEFAULT_SHARE = default_share_path()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json_atomic(path, payload):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = os.path.join(folder, "%s.%s.tmp" % (os.path.basename(path), uuid.uuid4().hex))
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def read_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception:
        return {}


def write_config(payload):
    try:
        write_json_atomic(CONFIG_PATH, payload)
    except Exception:
        pass


def frame_number(value, fps):
    try:
        return int(value.GetFrame(fps))
    except AttributeError:
        return int(value)


def frame_from_doc_time(doc, value):
    return frame_number(value, doc.GetFps())


def get_render_range_from_render_data(doc, render_data):
    fps = doc.GetFps()
    data = render_data.GetData()
    try:
        sequence = data[c4d.RDATA_FRAMESEQUENCE]
    except Exception:
        sequence = c4d.RDATA_FRAMESEQUENCE_MANUAL

    if sequence == c4d.RDATA_FRAMESEQUENCE_CURRENTFRAME:
        frame = frame_from_doc_time(doc, doc.GetTime())
        return frame, frame, "current"
    if sequence == c4d.RDATA_FRAMESEQUENCE_ALLFRAMES:
        start = frame_from_doc_time(doc, doc.GetMinTime())
        end = frame_from_doc_time(doc, doc.GetMaxTime())
        return start, end, "all"
    if sequence == c4d.RDATA_FRAMESEQUENCE_PREVIEWRANGE:
        start = frame_from_doc_time(doc, doc.GetLoopMinTime())
        end = frame_from_doc_time(doc, doc.GetLoopMaxTime())
        return start, end, "preview"

    start = frame_number(data[c4d.RDATA_FRAMEFROM], fps)
    end = frame_number(data[c4d.RDATA_FRAMETO], fps)
    return start, end, "manual"


def get_project_folder(doc):
    folder = doc.GetDocumentPath()
    if folder:
        return folder
    return os.path.expanduser("~")


def get_document_name(doc):
    name = doc.GetDocumentName() or "untitled.c4d"
    if not name.lower().endswith(".c4d"):
        name += ".c4d"
    return name


def source_scene_path(doc):
    folder = doc.GetDocumentPath()
    if not folder:
        return ""
    return os.path.join(folder, get_document_name(doc))


def path_mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def document_has_unsaved_changes(doc):
    try:
        return bool(doc.IsDirty(c4d.DIRTYFLAGS_DATA))
    except Exception:
        pass
    try:
        return bool(doc.GetDirty(c4d.DIRTYFLAGS_DATA))
    except Exception:
        pass
    return False


def history_path_for_doc(doc):
    project = get_project_folder(doc)
    return os.path.join(project, DEFAULT_JOB_FOLDER, SUBMIT_HISTORY_FILENAME)


def read_submit_history(doc):
    try:
        with open(history_path_for_doc(doc), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"submits": []}


def last_submit_for_scene(doc):
    history = read_submit_history(doc)
    scene = os.path.normcase(os.path.abspath(source_scene_path(doc) or ""))
    matches = []
    for entry in history.get("submits", []):
        try:
            entry_scene = os.path.normcase(os.path.abspath(str(entry.get("source_scene") or "")))
        except Exception:
            entry_scene = ""
        if entry_scene and entry_scene == scene:
            matches.append(entry)
    if not matches:
        return None
    return sorted(matches, key=lambda item: str(item.get("submitted_at") or ""))[-1]


def append_submit_history(doc, entry):
    path = history_path_for_doc(doc)
    history = read_submit_history(doc)
    submits = list(history.get("submits", []))
    submits.append(entry)
    history["submits"] = submits[-80:]
    write_json_atomic(path, history)


class ConfirmSaveDialog(gui.GeDialog):
    def __init__(self, scene_path):
        super(ConfirmSaveDialog, self).__init__()
        self.scene_path = scene_path
        self.accepted = False

    def CreateLayout(self):
        self.SetTitle("DreamRender")
        self.GroupBegin(2000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.GroupBorderSpace(14, 14, 14, 14)
        self.GroupSpace(0, 10)
        self.AddStaticText(0, c4d.BFH_SCALEFIT, name="DreamRender needs to save the current Cinema 4D scene before submitting.")
        self.AddStaticText(0, c4d.BFH_SCALEFIT, name=self.scene_path)
        self.GroupBegin(2001, c4d.BFH_RIGHT, 2, 1)
        self.GroupSpace(8, 0)
        self.AddButton(IDC_CONFIRM_CANCEL, c4d.BFH_LEFT, initw=92, name="Cancel")
        self.AddButton(IDC_CONFIRM_SAVE, c4d.BFH_LEFT, initw=92, name="Save")
        self.GroupEnd()
        self.GroupEnd()
        return True

    def Command(self, control_id, msg):
        if control_id == IDC_CONFIRM_SAVE:
            self.accepted = True
            self.Close()
            return True
        if control_id == IDC_CONFIRM_CANCEL:
            self.accepted = False
            self.Close()
            return True
        return True


def confirm_save_before_submit(doc):
    folder = doc.GetDocumentPath()
    if not folder:
        gui.MessageDialog("Save the Cinema 4D scene once before submitting to DreamRender.")
        return False
    source_path = os.path.join(folder, get_document_name(doc))
    try:
        dialog = ConfirmSaveDialog(source_path)
        dialog.Open(c4d.DLG_TYPE_MODAL, defaultw=460, defaulth=145)
        return bool(dialog.accepted)
    except Exception:
        return bool(gui.QuestionDialog("DreamRender needs to save the current Cinema 4D scene before submitting.\n\nSave and submit?"))


def save_current_document(doc):
    folder = doc.GetDocumentPath()
    if not folder:
        gui.MessageDialog("Save the Cinema 4D scene once before submitting to DreamRender.")
        return False
    source_path = os.path.join(folder, get_document_name(doc))
    flags = c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST
    if not c4d.documents.SaveDocument(doc, source_path, flags, c4d.FORMAT_C4DEXPORT):
        gui.MessageDialog("Cinema 4D could not save the current scene before submitting:\n%s" % source_path)
        return False
    return True


def get_render_range(doc):
    return get_render_range_from_render_data(doc, doc.GetActiveRenderData())


def render_data_path(data, parameter_id):
    try:
        value = data[parameter_id]
    except Exception:
        value = None
    if value:
        text = str(value).strip()
        if text:
            return text
    try:
        text = data.GetString(parameter_id).strip()
        if text:
            return text
    except Exception:
        pass
    try:
        text = str(data.GetFilename(parameter_id)).strip()
        if text:
            return text
    except Exception:
        pass
    return ""


def get_output_path_info(doc):
    return get_output_path_info_for_render_data(doc, doc.GetActiveRenderData())


def get_output_path_info_for_render_data(doc, render_data):
    data = render_data.GetData()
    for label, parameter_id in (
        ("image", c4d.RDATA_PATH),
        ("multipass", c4d.RDATA_MULTIPASS_FILENAME),
    ):
        output = render_data_path(data, parameter_id)
        if output:
            return output, label
    project = get_project_folder(doc)
    name = os.path.splitext(get_document_name(doc))[0]
    return os.path.join(project, "render", name), "fallback"


def get_output_path(doc):
    return get_output_path_info(doc)[0]


def render_data_name(render_data, fallback="Render Settings"):
    try:
        return render_data.GetName() or fallback
    except Exception:
        return fallback


def render_data_value(data, parameter_id, fallback=None):
    try:
        return data[parameter_id]
    except Exception:
        return fallback


def detect_render_engine(doc):
    render_data = doc.GetActiveRenderData()
    data = render_data.GetData()
    engine = render_data_value(data, c4d.RDATA_RENDERENGINE, "")
    names = []
    try:
        video_post = render_data.GetFirstVideoPost()
        while video_post:
            names.append(video_post.GetName() or str(video_post.GetType()))
            video_post = video_post.GetNext()
    except Exception:
        pass
    info = ", ".join(names) if names else "engine id %s" % engine
    lowered = info.lower()
    if "octane" in lowered:
        return "Octane", info
    if "redshift" in lowered or str(engine) in ("1036219", "1036220"):
        return "Redshift", info
    return "", info


def active_camera_info(doc):
    try:
        base_draw = doc.GetActiveBaseDraw()
        camera = base_draw.GetSceneCamera(doc) if base_draw else None
        if camera is not None:
            name = camera.GetName() or "Scene Camera"
            if name and name.lower() not in ("editor camera", "default camera"):
                return CHECK_OK, "active scene camera", name
            try:
                if camera.CheckType(c4d.Ocamera):
                    return CHECK_OK, "active scene camera", name
            except Exception:
                pass
            return CHECK_WARNING, "no scene camera defined and/or active", name
    except Exception as exc:
        return CHECK_WARNING, "could not inspect active camera", str(exc)
    return CHECK_WARNING, "no scene camera defined and/or active", ""


def render_engine_info(doc):
    renderer, info = detect_render_engine(doc)
    if renderer:
        return CHECK_OK, "%s renderer detected" % renderer, info
    return CHECK_WARNING, "unsupported renderer detected", info


def fps_info(doc):
    fps = doc.GetFps()
    if fps > 0:
        return CHECK_OK, "%d fps" % fps, ""
    return CHECK_ERROR, "invalid FPS", str(fps)


def resolution_info(doc):
    data = doc.GetActiveRenderData().GetData()
    xres = render_data_value(data, c4d.RDATA_XRES, None)
    yres = render_data_value(data, c4d.RDATA_YRES, None)
    try:
        xres = int(float(xres))
        yres = int(float(yres))
    except Exception:
        return CHECK_WARNING, "could not read resolution", ""
    if xres > 0 and yres > 0:
        return CHECK_OK, "%dpx x %dpx" % (xres, yres), ""
    return CHECK_ERROR, "invalid resolution", "%s x %s" % (xres, yres)


def format_info(doc, output):
    extension = os.path.splitext(output)[1].lstrip(".").upper()
    if extension:
        return CHECK_OK, extension, ""
    data = doc.GetActiveRenderData().GetData()
    image_format = render_data_value(data, getattr(c4d, "RDATA_FORMAT", 0), "")
    if image_format:
        return CHECK_OK, "format id %s" % image_format, ""
    return CHECK_WARNING, "could not determine output format", ""


def multipass_info(doc):
    data = doc.GetActiveRenderData().GetData()
    enabled = False
    for parameter_name in ("RDATA_MULTIPASS_ENABLE", "RDATA_MULTIPASS_SAVEIMAGE"):
        try:
            enabled = enabled or bool(data[getattr(c4d, parameter_name)])
        except Exception:
            pass
    output = render_data_path(data, c4d.RDATA_MULTIPASS_FILENAME)
    if enabled or output:
        label = "enabled"
        if output:
            label = "enabled, %s" % output
        return CHECK_OK, label, ""
    return CHECK_OK, "not enabled", ""


def iter_takes(take):
    if take is None:
        return
    yield take
    child = take.GetDown()
    while child:
        for item in iter_takes(child):
            yield item
        child = child.GetNext()


def get_marked_takes(doc):
    take_data = doc.GetTakeData()
    if take_data is None:
        return []
    main_take = take_data.GetMainTake()
    takes = []
    for take in iter_takes(main_take):
        try:
            if take.IsChecked():
                takes.append(take)
        except Exception:
            pass
    return takes


def get_take_render_data(doc, take):
    for method_name in ("GetTakeRenderData", "GetRenderData"):
        method = getattr(take, method_name, None)
        if method is None:
            continue
        try:
            if method_name == "GetRenderData":
                render_data = method(doc.GetTakeData())
            else:
                render_data = method()
        except Exception:
            render_data = None
        if render_data is not None:
            return render_data
    return doc.GetActiveRenderData()


def marked_take_render_data(doc, takes):
    return [get_take_render_data(doc, take) for take in takes]


def marked_takes_have_different_render_settings(doc, takes):
    render_data = marked_take_render_data(doc, takes)
    active = doc.GetActiveRenderData()
    return len(set(id(item) for item in render_data)) > 1 or any(item != active for item in render_data)


def take_name(take):
    try:
        return take.GetName() or "Main"
    except Exception:
        return "Main"


def has_c4d_tokens(value):
    return "$" in value


def add_check(checks, level, title, detail=""):
    checks.append({"level": level, "title": title, "detail": detail})


def checks_with_level(checks, level):
    return [item for item in checks if item["level"] == level]


def has_check_level(checks, level):
    return bool(checks_with_level(checks, level))


def check_summary_line(checks):
    errors = len(checks_with_level(checks, CHECK_ERROR))
    warnings = len(checks_with_level(checks, CHECK_WARNING))
    ok = len(checks_with_level(checks, CHECK_OK))
    return "%d errors, %d warnings, %d checks passed" % (errors, warnings, ok)


def check_result_text(level, message, info=""):
    prefix = "Success"
    if level == CHECK_WARNING:
        prefix = "Warning"
    elif level == CHECK_ERROR:
        prefix = "Error"
    text = "%s: %s" % (prefix, message)
    if info:
        text += " Info: %s" % info
    return text


def add_report_row(rows, label, level, message, info=""):
    rows.append({"label": label, "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)})


def report_has_level(rows, level):
    return any(row["level"] == level for row in rows)


def report_status_text(rows):
    if report_has_level(rows, CHECK_ERROR):
        return "Errors detected. Fix these before submitting."
    if report_has_level(rows, CHECK_WARNING):
        return "Warnings detected. Ready to submit with confirmation."
    return "Scene check passed. Ready to submit."


def report_state_text(level):
    if level == CHECK_ERROR:
        return "Error"
    if level == CHECK_WARNING:
        return "Warning"
    return "Success"


def format_scene_report(rows):
    label_width = 15
    lines = []
    for row in rows:
        lines.append("%s %s" % ((row["label"] + ":").ljust(label_width), row["text"]))
    lines.append("")
    lines.append("%s %s" % ("STATUS:".ljust(label_width), report_status_text(rows)))
    return "\n".join(lines)


def compact_text(value, limit=92):
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class SceneCheckTableArea(gui.GeUserArea):
    MIN_W = 660
    MIN_H = 380
    HEADER_H = 30
    ROW_H = 27
    PAD_X = 12
    SCROLL_W = 12
    SCROLL_H = 12
    CONTENT_W = 1180

    def __init__(self):
        super(SceneCheckTableArea, self).__init__()
        self.rows = []
        self.current_index = -1
        self.spinner = ""
        self._width = self.MIN_W
        self._height = self.MIN_H
        self._scroll_x = 0
        self._scroll_y = 0
        self._drag = None
        self.dialog = None

    def GetMinSize(self):
        return self.MIN_W, self.MIN_H

    def Sized(self, width, height):
        self._width = max(1, int(width))
        self._height = max(1, int(height))

    def set_rows(self, rows, current_index=-1, spinner=""):
        self.rows = list(rows or [])
        self.current_index = current_index
        self.spinner = spinner
        try:
            self.Redraw()
        except Exception:
            pass

    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.OffScreenOn()
        width = max(1, int(x2) - int(x1) + 1)
        height = max(1, int(y2) - int(y1) + 1)
        self._width = width
        self._height = height
        self._clamp_scroll()
        self._fill(0, 0, width, height, (0.115, 0.118, 0.124))
        self._draw_header(width)
        for index, row in enumerate(self.rows):
            top = self.HEADER_H + index * self.ROW_H - self._scroll_y
            if top > height:
                break
            if top + self.ROW_H < self.HEADER_H:
                continue
            self._draw_row(index, row, top, width)
        self._draw_scrollbars(width, height)

    def InputEvent(self, msg):
        if msg.GetInt32(c4d.BFM_INPUT_DEVICE) != c4d.BFM_INPUT_MOUSE:
            return False
        channel = msg.GetInt32(c4d.BFM_INPUT_CHANNEL)
        position = self._event_position(msg)
        if position:
            x, y = position
            if channel == c4d.BFM_INPUT_MOUSELEFT:
                if msg.GetInt32(c4d.BFM_INPUT_VALUE) == 0:
                    if self._drag is not None:
                        self._drag = None
                        return True
                elif self._drag is not None:
                    self._update_scroll_drag(x, y)
                    return True
                elif self._hit_v_scrollbar(x, y):
                    self._handle_v_scroll_click(y)
                    return True
                elif self._hit_h_scrollbar(x, y):
                    self._handle_h_scroll_click(x)
                    return True
            move_channel = getattr(c4d, "BFM_INPUT_MOUSEMOVE", None)
            if move_channel is not None and channel == move_channel and self._drag is not None:
                self._update_scroll_drag(x, y)
                return True
        wheel_channel = getattr(c4d, "BFM_INPUT_MOUSEWHEEL", None)
        if wheel_channel is not None and channel == wheel_channel:
            delta = msg.GetInt32(c4d.BFM_INPUT_VALUE)
            if delta > 0:
                self._set_scroll_y(self._scroll_y - self.ROW_H * 2)
            elif delta < 0:
                self._set_scroll_y(self._scroll_y + self.ROW_H * 2)
            return True
        return False

    def Message(self, msg, result):
        if msg.GetId() == c4d.BFM_INPUT:
            if self.InputEvent(msg):
                return True
        return super(SceneCheckTableArea, self).Message(msg, result)

    def poll_drag(self):
        if self._drag is None:
            return False
        state = self._mouse_state()
        if state is None:
            self._drag = None
            return False
        down, x, y = state
        if not down:
            self._drag = None
            return False
        self._update_scroll_drag(x, y)
        return True

    def is_dragging(self):
        return self._drag is not None

    def _ensure_timer(self):
        dialog = getattr(self, "dialog", None)
        if dialog is None:
            return
        try:
            dialog.SetTimer(20)
        except Exception:
            pass

    def _mouse_state(self):
        result = c4d.BaseContainer()
        try:
            ok = self.GetInputState(c4d.BFM_INPUT_MOUSE, c4d.BFM_INPUT_MOUSELEFT, result)
        except Exception:
            return None
        if not ok:
            return None
        down = bool(result.GetInt32(c4d.BFM_INPUT_VALUE))
        move = c4d.BaseContainer()
        try:
            if self.GetInputState(c4d.BFM_INPUT_MOUSE, c4d.BFM_INPUT_MOUSEMOVE, move):
                if move.GetInt32(c4d.BFM_INPUT_X) or move.GetInt32(c4d.BFM_INPUT_Y):
                    result = move
        except Exception:
            pass
        position = self._event_position(result)
        if position is None:
            return None
        return down, position[0], position[1]

    def _event_position(self, msg):
        try:
            x = msg.GetInt32(c4d.BFM_INPUT_X)
            y = msg.GetInt32(c4d.BFM_INPUT_Y)
        except Exception:
            return None
        for converter_name in ("Screen2Local", "Global2Local"):
            converter = getattr(self, converter_name, None)
            if converter is None:
                continue
            try:
                result = converter(x, y)
                if isinstance(result, dict):
                    return int(result.get("x", 0)), int(result.get("y", 0))
                if isinstance(result, tuple):
                    if len(result) == 2:
                        return int(result[0]), int(result[1])
                    if len(result) >= 3:
                        return int(result[1]), int(result[2])
            except TypeError:
                try:
                    offset = converter()
                    if isinstance(offset, dict):
                        candidates = (
                            (x + int(offset.get("x", 0)), y + int(offset.get("y", 0))),
                            (x - int(offset.get("x", 0)), y - int(offset.get("y", 0))),
                        )
                        for cx, cy in candidates:
                            if 0 <= cx <= self._width and 0 <= cy <= self._height:
                                return int(cx), int(cy)
                except Exception:
                    pass
            except Exception:
                pass
        return int(x), int(y)

    def _columns(self, width):
        icon_w = 42
        check_w = 160
        state_w = 105
        result_w = 260
        info_w = max(460, self.CONTENT_W - self.PAD_X * 2 - icon_w - check_w - state_w - result_w)
        x = self.PAD_X - self._scroll_x
        columns = []
        for w in (icon_w, check_w, state_w, result_w, info_w):
            columns.append((x, x + w))
            x += w
        return columns

    def _draw_header(self, width):
        self._fill(0, 0, width, self.HEADER_H, (0.075, 0.078, 0.084))
        columns = self._columns(width)
        headers = ("", "Check", "State", "Result", "Info")
        for (left, _right), header in zip(columns, headers):
            self._text(header, left + 4, 9, (0.72, 0.74, 0.76), bold=True, bg=(0.075, 0.078, 0.084))

    def _draw_row(self, index, row, top, width):
        bg = (0.142, 0.145, 0.152) if index % 2 else (0.125, 0.128, 0.134)
        if index == self.current_index:
            bg = (0.180, 0.160, 0.118)
        self._fill(0, top, width, top + self.ROW_H, bg)
        self._line(0, top + self.ROW_H, width, top + self.ROW_H, (0.085, 0.088, 0.094))
        columns = self._columns(width)
        level = row.get("level")
        icon, color = self._icon(level)
        if index == self.current_index and self.spinner:
            icon = self.spinner
            color = (1.0, 0.72, 0.25)
        values = (
            icon,
            row.get("label", ""),
            report_state_text(level),
            row.get("message", ""),
            row.get("info", ""),
        )
        colors = (
            color,
            (0.94, 0.94, 0.92),
            color,
            (0.88, 0.88, 0.86),
            (0.72, 0.74, 0.74),
        )
        for column, value, text_color in zip(columns, values, colors):
            self._text(value, column[0] + 4, top + 8, text_color, bold=value in (icon, row.get("label", "")), bg=bg)

    def _icon(self, level):
        if level == CHECK_ERROR:
            return "✕", (0.94, 0.30, 0.36)
        if level == CHECK_WARNING:
            return "⚠", (1.00, 0.58, 0.22)
        if level == CHECK_OK:
            return "✓", (0.35, 0.79, 0.51)
        return "•", (0.65, 0.67, 0.68)

    def _fill(self, x1, y1, x2, y2, color):
        self.DrawSetPen(c4d.Vector(color[0], color[1], color[2]))
        self.DrawRectangle(int(x1), int(y1), int(x2), int(y2))

    def _line(self, x1, y1, x2, y2, color):
        self.DrawSetPen(c4d.Vector(color[0], color[1], color[2]))
        self.DrawLine(int(x1), int(y1), int(x2), int(y2))

    def _content_height(self):
        return self.HEADER_H + len(self.rows) * self.ROW_H

    def _visible_width(self):
        return max(1, self._width - self.SCROLL_W)

    def _visible_height(self):
        return max(1, self._height - self.SCROLL_H)

    def _max_scroll_x(self):
        return max(0, self.CONTENT_W - self._visible_width())

    def _max_scroll_y(self):
        return max(0, self._content_height() - self._visible_height())

    def _clamp_scroll(self):
        self._scroll_x = max(0, min(self._scroll_x, self._max_scroll_x()))
        self._scroll_y = max(0, min(self._scroll_y, self._max_scroll_y()))

    def _set_scroll_y(self, value):
        self._scroll_y = max(0, min(int(value), self._max_scroll_y()))
        self.Redraw()

    def _set_scroll_x(self, value):
        self._scroll_x = max(0, min(int(value), self._max_scroll_x()))
        self.Redraw()

    def _draw_scrollbars(self, width, height):
        if self._max_scroll_y() > 0:
            track_x1, track_y1, track_x2, track_y2 = self._v_scroll_track(width, height)
            thumb_x1, thumb_y1, thumb_x2, thumb_y2 = self._v_thumb_rect(width, height)
            self._fill(track_x1, track_y1, track_x2, track_y2, (0.090, 0.092, 0.098))
            self._fill(thumb_x1, thumb_y1, thumb_x2, thumb_y2, (0.32, 0.34, 0.35))
        if self._max_scroll_x() > 0:
            track_x1, track_y1, track_x2, track_y2 = self._h_scroll_track(width, height)
            thumb_x1, thumb_y1, thumb_x2, thumb_y2 = self._h_thumb_rect(width, height)
            self._fill(track_x1, track_y1, track_x2, track_y2, (0.090, 0.092, 0.098))
            self._fill(thumb_x1, thumb_y1, thumb_x2, thumb_y2, (0.32, 0.34, 0.35))

    def _v_scroll_track(self, width=None, height=None):
        width = self._width if width is None else int(width)
        height = self._height if height is None else int(height)
        return width - self.SCROLL_W, self.HEADER_H, width, height - self.SCROLL_H

    def _h_scroll_track(self, width=None, height=None):
        width = self._width if width is None else int(width)
        height = self._height if height is None else int(height)
        return 0, height - self.SCROLL_H, width - self.SCROLL_W, height

    def _v_thumb_rect(self, width=None, height=None):
        track_x1, track_y1, track_x2, track_y2 = self._v_scroll_track(width, height)
        track_h = max(1, track_y2 - track_y1)
        content_h = max(1, self._content_height())
        thumb_h = max(24, int(float(self._visible_height()) * track_h / float(content_h)))
        thumb_h = min(track_h, thumb_h)
        usable = max(1, track_h - thumb_h)
        thumb_y = track_y1 + int(float(self._scroll_y) / float(max(1, self._max_scroll_y())) * usable)
        return track_x1 + 2, thumb_y, track_x2 - 3, thumb_y + thumb_h

    def _h_thumb_rect(self, width=None, height=None):
        track_x1, track_y1, track_x2, track_y2 = self._h_scroll_track(width, height)
        track_w = max(1, track_x2 - track_x1)
        thumb_w = max(36, int(float(self._visible_width()) * track_w / float(max(1, self.CONTENT_W))))
        thumb_w = min(track_w, thumb_w)
        usable = max(1, track_w - thumb_w)
        thumb_x = track_x1 + int(float(self._scroll_x) / float(max(1, self._max_scroll_x())) * usable)
        return thumb_x, track_y1 + 2, thumb_x + thumb_w, track_y2 - 3

    def _hit_v_scrollbar(self, x, y):
        if self._max_scroll_y() <= 0:
            return False
        track_x1, track_y1, track_x2, track_y2 = self._v_scroll_track()
        return track_x1 <= x <= track_x2 and track_y1 <= y <= track_y2

    def _hit_h_scrollbar(self, x, y):
        if self._max_scroll_x() <= 0:
            return False
        track_x1, track_y1, track_x2, track_y2 = self._h_scroll_track()
        return track_x1 <= x <= track_x2 and track_y1 <= y <= track_y2

    def _in_rect(self, x, y, rect):
        x1, y1, x2, y2 = rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _handle_v_scroll_click(self, y):
        thumb = self._v_thumb_rect()
        if self._in_rect(self._width - self.SCROLL_W + 1, y, thumb):
            self._drag = {
                "kind": "vscroll",
                "mouse": float(y),
                "scroll": self._scroll_y,
            }
            self._ensure_timer()
            return
        page = max(1, self._visible_height() - self.HEADER_H - self.ROW_H)
        if y < thumb[1]:
            self._set_scroll_y(self._scroll_y - page)
        else:
            self._set_scroll_y(self._scroll_y + page)

    def _handle_h_scroll_click(self, x):
        thumb = self._h_thumb_rect()
        if self._in_rect(x, self._height - self.SCROLL_H + 1, thumb):
            self._drag = {
                "kind": "hscroll",
                "mouse": float(x),
                "scroll": self._scroll_x,
            }
            self._ensure_timer()
            return
        page = max(1, self._visible_width() - 80)
        if x < thumb[0]:
            self._set_scroll_x(self._scroll_x - page)
        else:
            self._set_scroll_x(self._scroll_x + page)

    def _update_scroll_drag(self, x, y):
        if self._drag is None:
            return
        if self._drag.get("kind") == "vscroll":
            _tx1, track_y1, _tx2, track_y2 = self._v_scroll_track()
            _x1, thumb_y1, _x2, thumb_y2 = self._v_thumb_rect()
            usable = max(1, (track_y2 - track_y1) - max(1, thumb_y2 - thumb_y1))
            dy = float(y) - float(self._drag.get("mouse", y))
            delta = int(dy * float(self._max_scroll_y()) / float(usable))
            self._set_scroll_y(int(self._drag.get("scroll", 0)) + delta)
        elif self._drag.get("kind") == "hscroll":
            track_x1, _ty1, track_x2, _ty2 = self._h_scroll_track()
            thumb_x1, _y1, thumb_x2, _y2 = self._h_thumb_rect()
            usable = max(1, (track_x2 - track_x1) - max(1, thumb_x2 - thumb_x1))
            dx = float(x) - float(self._drag.get("mouse", x))
            delta = int(dx * float(self._max_scroll_x()) / float(usable))
            self._set_scroll_x(int(self._drag.get("scroll", 0)) + delta)

    def _text(self, text, x, y, color, bold=False, bg=None):
        self.DrawSetFont(c4d.FONT_BOLD if bold else c4d.FONT_STANDARD)
        bg = bg or (0.125, 0.128, 0.134)
        self.DrawSetTextCol(c4d.Vector(color[0], color[1], color[2]), c4d.Vector(bg[0], bg[1], bg[2]))
        self.DrawText(str(text or ""), int(x), int(y))


def format_checks(checks, title="DreamRender Scene Check"):
    lines = [title, check_summary_line(checks), ""]
    sections = (
        (CHECK_ERROR, "Errors"),
        (CHECK_WARNING, "Warnings"),
        (CHECK_OK, "Passed"),
    )
    for level, label in sections:
        items = checks_with_level(checks, level)
        if not items:
            continue
        lines.append(label)
        visible = items[:12]
        for item in visible:
            lines.append("- %s" % item["title"])
            if item["detail"]:
                lines.append("  %s" % item["detail"])
        if len(items) > len(visible):
            lines.append("- ...and %d more" % (len(items) - len(visible)))
        lines.append("")
    return "\n".join(lines).strip()


def folder_for_output_path(output):
    if not output:
        return ""
    if os.path.splitext(output)[1]:
        return os.path.dirname(output)
    if os.path.isdir(output):
        return output
    parent = os.path.dirname(output)
    if parent:
        return parent
    return output


def output_folder_check(output):
    output_folder = folder_for_output_path(output)
    if not output:
        return CHECK_ERROR, "empty output path", "Set Render Settings output"
    if output_folder and has_c4d_tokens(output_folder):
        return CHECK_OK, "Cinema 4D token path", output
    if output_folder and os.path.isdir(output_folder):
        writable, reason = probe_writable_folder(output_folder)
        if not writable:
            return CHECK_ERROR, "output folder is not writable", "%s\n%s" % (output_folder, reason)
        if output_folder != output:
            return CHECK_OK, "output folder exists and is writable", output_folder
        return CHECK_OK, "folder exists and is writable", output_folder
    if output_folder:
        return CHECK_WARNING, "folder does not exist yet", output_folder
    return CHECK_WARNING, "path has no folder", output


def output_path_info_check(output, source, renderer=""):
    if source == "fallback":
        if renderer == "Octane":
            return CHECK_OK, "Octane commandline output", output
        return CHECK_ERROR, "no render settings output path", "Set the save/output path in Cinema 4D Render Settings"
    return output_folder_check(output)


def worst_level(levels):
    if CHECK_ERROR in levels:
        return CHECK_ERROR
    if CHECK_WARNING in levels:
        return CHECK_WARNING
    return CHECK_OK


def marked_take_output_check(doc, marked_takes, renderer=""):
    levels = []
    details = []
    for take in marked_takes:
        render_data = get_take_render_data(doc, take)
        output, source = get_output_path_info_for_render_data(doc, render_data)
        level, message, detail = output_path_info_check(output, source, renderer)
        levels.append(level)
        if level != CHECK_OK:
            details.append("%s: %s" % (take_name(take), detail or message))
    level = worst_level(levels or [CHECK_OK])
    if level == CHECK_OK:
        return CHECK_OK, "marked take outputs ready", "%d takes checked" % len(marked_takes)
    return level, "marked take output issue", "; ".join(details[:3])


def history_check(doc):
    scene = source_scene_path(doc)
    if not scene:
        return CHECK_WARNING, "no saved scene history yet", "Save the scene once before submitting."
    if document_has_unsaved_changes(doc):
        return CHECK_WARNING, "scene has unsaved changes", "DreamRender will ask to save before submitting."
    last = last_submit_for_scene(doc)
    if not last:
        return CHECK_OK, "no previous DreamRender submit", "This scene has not been submitted from this project folder yet."
    current_mtime = path_mtime(scene)
    last_mtime = last.get("source_scene_mtime")
    if current_mtime is not None and last_mtime is not None and float(current_mtime) > float(last_mtime) + 1:
        return CHECK_WARNING, "scene changed since last submit", "Last submit: %s" % (last.get("submitted_at") or "unknown")
    return CHECK_OK, "scene matches last submit timestamp", "Last submit: %s" % (last.get("submitted_at") or "unknown")


def cache_asset_summary(doc):
    assets, asset_error = collect_scene_assets(doc)
    if asset_error:
        return CHECK_WARNING, "could not inspect caches", str(asset_error)
    project = get_project_folder(doc)
    document_folder = doc.GetDocumentPath()
    cache_paths = []
    external_cache_paths = []
    for asset in assets:
        path = asset_text(asset, ("filename", "assetname", "name", "url", "nodePath"))
        if not path:
            continue
        normalized = normalize_asset_path(path, project)
        lowered = normalized.lower()
        if not any(lowered.endswith(extension) for extension in CACHE_EXTENSIONS):
            continue
        cache_paths.append(normalized)
        if is_local_asset_path(normalized) and document_folder and not same_or_child(normalized, project):
            external_cache_paths.append(normalized)
    if external_cache_paths:
        return CHECK_WARNING, "cache/proxy paths outside project", "Workers need identical mappings:\n%s" % "\n".join(external_cache_paths[:8])
    if cache_paths:
        return CHECK_OK, "cache/proxy assets found", "%d cache/proxy assets checked" % len(cache_paths)
    return CHECK_OK, "no cache/proxy assets reported", ""


def worker_share_check(share):
    if not share or not os.path.isdir(share):
        return CHECK_WARNING, "workers cannot be checked yet", "DreamRender share is not available."
    workers_dir = os.path.join(share, "workers")
    if not os.path.isdir(workers_dir):
        return CHECK_WARNING, "no workers have checked in yet", workers_dir
    workers = [name for name in os.listdir(workers_dir) if name.lower().endswith(".json")]
    if workers:
        return CHECK_OK, "workers have checked in", "%d known worker(s)" % len(workers)
    return CHECK_WARNING, "no workers have checked in yet", workers_dir


def scene_report_step_builders(doc, share, output, start, end, chunk_size, submit_marked_takes):
    marked_takes = get_marked_takes(doc) if submit_marked_takes else []
    take_driven = bool(marked_takes) and marked_takes_have_different_render_settings(doc, marked_takes)
    renderer, _renderer_info = detect_render_engine(doc)

    def camera_row():
        level, message, info = active_camera_info(doc)
        return {"label": "CAMERA", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def project_row():
        document_folder = doc.GetDocumentPath()
        document_name = get_document_name(doc)
        if document_folder:
            level, message, info = CHECK_OK, "scene saved", os.path.join(document_folder, document_name)
        else:
            level, message, info = CHECK_ERROR, "scene not saved", "Save the Cinema 4D file once before submitting"
        return {"label": "PROJECT", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def history_row():
        level, message, info = history_check(doc)
        return {"label": "HISTORY", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def textures_row():
        assets, asset_error = collect_scene_assets(doc)
        project = get_project_folder(doc)
        document_folder = doc.GetDocumentPath()
        if asset_error:
            level, message, info = CHECK_WARNING, "could not inspect assets", str(asset_error)
        else:
            missing = []
            external = []
            for asset in assets:
                path = asset_text(asset, ("filename", "assetname", "name", "url", "nodePath"))
                if not path:
                    continue
                normalized = normalize_asset_path(path, project)
                if not asset_exists(asset, path, project):
                    missing.append(path)
                elif is_local_asset_path(normalized) and document_folder and not same_or_child(normalized, project):
                    external.append(normalized)
            if missing:
                level, message, info = CHECK_WARNING, "missing assets found", "%d missing, first: %s" % (len(missing), missing[0])
            elif external:
                level, message, info = CHECK_WARNING, "external asset paths found", "%d outside project; workers need same mapping" % len(external)
            else:
                level, message, info = CHECK_OK, "all assets found", "%d assets checked" % len(assets)
        return {"label": "TEXTURES", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def render_engine_row():
        level, message, info = render_engine_info(doc)
        return {"label": "RENDERENGINE", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def cache_row():
        level, message, info = cache_asset_summary(doc)
        return {"label": "CACHE", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def fps_row():
        level, message, info = fps_info(doc)
        return {"label": "FPS", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def output_row():
        if take_driven:
            level, message, info = marked_take_output_check(doc, marked_takes, renderer)
        else:
            level, message, info = output_path_info_check(output, get_output_path_info(doc)[1], renderer)
        return {"label": "OUTPUT", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def multipass_row():
        level, message, info = multipass_info(doc)
        return {"label": "MULTIPASS", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def format_row():
        level, message, info = format_info(doc, output)
        return {"label": "FORMAT", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def frame_row():
        if take_driven:
            level, message, info = CHECK_OK, "marked take frame ranges", "%d takes use their own render settings" % len(marked_takes)
        elif end < start:
            level, message, info = CHECK_ERROR, "invalid range", "%d-%d" % (start, end)
        elif start == end:
            level, message, info = CHECK_OK, "single frame", str(start)
        else:
            level, message, info = CHECK_OK, "frame range", "%d-%d" % (start, end)
        return {"label": "FRAME", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def resolution_row():
        level, message, info = resolution_info(doc)
        return {"label": "RESOLUTION", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def batch_row():
        if chunk_size < 1:
            level, message, info = CHECK_ERROR, "invalid frames per batch", str(chunk_size)
        else:
            level, message, info = CHECK_OK, "frames per batch", str(chunk_size)
        return {"label": "BATCH", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def queue_row():
        if share and os.path.isdir(share):
            writable, reason = probe_writable_folder(share)
            if writable:
                level, message, info = CHECK_OK, "DreamRender share writable", share
            else:
                level, message, info = CHECK_ERROR, "DreamRender share not writable", reason
        elif share:
            level, message, info = CHECK_ERROR, "DreamRender share inaccessible", share
        else:
            level, message, info = CHECK_ERROR, "DreamRender share missing", ""
        return {"label": "QUEUE", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def workers_row():
        level, message, info = worker_share_check(share)
        return {"label": "WORKERS", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    def takes_row():
        if submit_marked_takes:
            if not marked_takes:
                level, message, info = CHECK_ERROR, "no marked takes found", ""
            else:
                labels = [take_name(take) for take in marked_takes]
                duplicates = sorted(set(label for label in labels if labels.count(label) > 1))
                if duplicates:
                    level, message, info = CHECK_ERROR, "duplicate take names", ", ".join(duplicates)
                else:
                    render_data_names = sorted(set(render_data_name(item) for item in marked_take_render_data(doc, marked_takes)))
                    if len(render_data_names) > 1:
                        level, message, info = CHECK_OK, "marked takes ready", "%d takes, %d render settings" % (len(marked_takes), len(render_data_names))
                    else:
                        level, message, info = CHECK_OK, "marked takes ready", "%d takes" % len(marked_takes)
        else:
            level, message, info = CHECK_OK, "single render job", "marked takes disabled"
        return {"label": "TAKES", "level": level, "message": message, "info": info, "text": check_result_text(level, message, info)}

    return [
        ("CAMERA", camera_row),
        ("PROJECT", project_row),
        ("HISTORY", history_row),
        ("TEXTURES", textures_row),
        ("CACHE", cache_row),
        ("RENDERENGINE", render_engine_row),
        ("FPS", fps_row),
        ("OUTPUT", output_row),
        ("MULTIPASS", multipass_row),
        ("FORMAT", format_row),
        ("FRAME", frame_row),
        ("RESOLUTION", resolution_row),
        ("BATCH", batch_row),
        ("QUEUE", queue_row),
        ("WORKERS", workers_row),
        ("TAKES", takes_row),
    ]


def same_or_child(path, root):
    if not path or not root:
        return False
    try:
        path = os.path.normcase(os.path.abspath(path))
        root = os.path.normcase(os.path.abspath(root))
        return path == root or path.startswith(root + os.sep)
    except Exception:
        return False


def is_local_asset_path(path):
    if not path:
        return False
    text = str(path).strip()
    lowered = text.lower()
    if not text or has_c4d_tokens(text):
        return False
    if "://" in lowered and not lowered.startswith("file://"):
        return False
    if lowered.startswith(("asset:", "maxon:", "tex/")):
        return False
    return os.path.isabs(text)


def normalize_asset_path(path, project):
    if not path:
        return ""
    text = str(path).strip()
    if has_c4d_tokens(text):
        return text
    if text.lower().startswith("file://"):
        text = text[7:]
        if text.startswith("/") and len(text) > 3 and text[2] == ":":
            text = text[1:]
    if os.path.isabs(text):
        return text
    if project and text and "://" not in text:
        return os.path.join(project, text)
    return text


def probe_writable_folder(folder, create=False):
    if not folder:
        return False, "No folder path."
    try:
        if create and not os.path.isdir(folder):
            os.makedirs(folder)
        if not os.path.isdir(folder):
            return False, "Folder does not exist."
        probe = os.path.join(folder, ".dreamrender_write_%s.tmp" % uuid.uuid4().hex)
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def asset_text(asset, keys):
    if not isinstance(asset, dict):
        return ""
    for key in keys:
        try:
            value = asset.get(key)
        except Exception:
            value = None
        if value:
            return str(value)
    return ""


def asset_exists(asset, path, project):
    if isinstance(asset, dict):
        for key in ("exists", "existsOnDisk", "found", "isFound"):
            if key in asset:
                try:
                    return bool(asset.get(key))
                except Exception:
                    pass
    normalized = normalize_asset_path(path, project)
    if is_local_asset_path(normalized):
        return os.path.exists(normalized)
    return True


def collect_scene_assets(doc):
    assets = []
    documents = c4d.documents
    flags = 0
    try:
        flags = c4d.ASSETDATA_FLAG_TEXTURESONLY
    except Exception:
        pass

    last_error = None
    if hasattr(documents, "GetAllAssetsNew"):
        try:
            result = documents.GetAllAssetsNew(doc, False, "", flags, assets)
            failed = getattr(c4d, "GETALLASSETSRESULT_FAILED", None)
            if failed is not None and result == failed:
                return [], "Cinema 4D asset collection failed."
            return assets, None
        except Exception as exc:
            last_error = exc

    if hasattr(documents, "GetAllAssets"):
        try:
            result = documents.GetAllAssets(doc, False, "", flags)
            if result is None:
                return [], "Cinema 4D asset collection failed."
            return result, None
        except Exception as exc:
            last_error = exc
        try:
            result = documents.GetAllAssets(doc, False, "")
            if result is None:
                return [], "Cinema 4D asset collection failed."
            return result, None
        except Exception as exc:
            last_error = exc

    return [], last_error or "Cinema 4D asset API is not available."


def run_scene_checks(doc, share, output, start, end, chunk_size, submit_marked_takes):
    checks = []
    document_folder = doc.GetDocumentPath()
    document_name = get_document_name(doc)
    project = get_project_folder(doc)
    marked_takes = get_marked_takes(doc) if submit_marked_takes else []
    take_driven = bool(marked_takes) and marked_takes_have_different_render_settings(doc, marked_takes)
    renderer, _renderer_info = detect_render_engine(doc)

    if document_folder:
        add_check(checks, CHECK_OK, "Scene has been saved", os.path.join(document_folder, document_name))
        level, message, detail = history_check(doc)
        add_check(checks, level, message, detail)
    else:
        add_check(checks, CHECK_ERROR, "Scene has not been saved", "Save the Cinema 4D document once before submitting.")

    if share and os.path.isdir(share):
        writable, reason = probe_writable_folder(share)
        if writable:
            add_check(checks, CHECK_OK, "DreamRender share is writable", share)
        else:
            add_check(checks, CHECK_ERROR, "DreamRender share is not writable", "%s\n%s" % (share, reason))
    elif share:
        add_check(checks, CHECK_ERROR, "DreamRender share is not accessible", share)
    else:
        add_check(checks, CHECK_ERROR, "DreamRender share is missing", "Choose the shared DreamRender queue folder.")

    level, message, detail = worker_share_check(share)
    add_check(checks, level, message, detail)

    if document_folder:
        jobs_root = os.path.join(project, DEFAULT_JOB_FOLDER)
        if os.path.isdir(jobs_root):
            writable, reason = probe_writable_folder(jobs_root)
            detail = jobs_root
        else:
            writable, reason = probe_writable_folder(project)
            detail = "%s can be created in %s" % (DEFAULT_JOB_FOLDER, project)
        if writable:
            add_check(checks, CHECK_OK, "DreamRender job scene folder is writable", detail)
        else:
            add_check(checks, CHECK_ERROR, "DreamRender job scene folder is not writable", "%s\n%s" % (jobs_root, reason))

    if take_driven:
        add_check(checks, CHECK_OK, "Frame ranges come from marked takes", "%d marked takes use their own render settings." % len(marked_takes))
    elif end < start:
        add_check(checks, CHECK_ERROR, "Frame range is invalid", "End frame must be greater than or equal to start frame.")
    else:
        add_check(checks, CHECK_OK, "Frame range is valid", "%d-%d" % (start, end))

    if chunk_size < 1:
        add_check(checks, CHECK_ERROR, "Frames per batch must be at least 1")
    else:
        add_check(checks, CHECK_OK, "Frames per batch is valid", str(chunk_size))

    if take_driven:
        level, message, detail = marked_take_output_check(doc, marked_takes, renderer)
        add_check(checks, level, message, detail)
    elif output:
        level, message, detail = output_path_info_check(output, get_output_path_info(doc)[1], renderer)
        add_check(checks, level, message, detail)
    else:
        add_check(checks, CHECK_ERROR, "Output path is empty", "Set an output path in Cinema 4D Render Settings.")

    if submit_marked_takes:
        if not marked_takes:
            add_check(checks, CHECK_ERROR, "No marked takes were found", "Mark takes in the Take Manager or disable marked-take submission.")
        else:
            labels = [take_name(take) for take in marked_takes]
            duplicates = sorted(set(label for label in labels if labels.count(label) > 1))
            if duplicates:
                add_check(checks, CHECK_ERROR, "Marked takes must have unique names", "\n".join(duplicates))
            else:
                add_check(checks, CHECK_OK, "Marked takes are valid", "%d takes" % len(marked_takes))

    assets, asset_error = collect_scene_assets(doc)
    if asset_error:
        add_check(checks, CHECK_WARNING, "Could not run Cinema 4D asset check", str(asset_error))
    else:
        missing = []
        external = []
        for asset in assets:
            path = asset_text(asset, ("filename", "assetname", "name", "url", "nodePath"))
            if not path:
                continue
            normalized = normalize_asset_path(path, project)
            if not asset_exists(asset, path, project):
                missing.append(path)
            elif is_local_asset_path(normalized) and document_folder and not same_or_child(normalized, project):
                external.append(normalized)
        if missing:
            add_check(checks, CHECK_WARNING, "Missing assets were found", "\n".join(missing[:12]))
        else:
            add_check(checks, CHECK_OK, "No missing assets reported", "%d assets checked" % len(assets))
        if external:
            add_check(
                checks,
                CHECK_WARNING,
                "Assets outside the project folder",
                "Workers need the same path mapping for these files:\n%s" % "\n".join(external[:12]),
            )
        level, message, detail = cache_asset_summary(doc)
        add_check(checks, level, message, detail)

    return checks


def farm_style_scene_report(doc, share, output, start, end, chunk_size, submit_marked_takes):
    return [build_row() for _label, build_row in scene_report_step_builders(doc, share, output, start, end, chunk_size, submit_marked_takes)]


def create_job(share, scene, output, frames, name, chunk_size, notes, metadata=None):
    job_id = "%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])
    job_dir = os.path.join(share, "jobs", job_id)
    frames_dir = os.path.join(job_dir, "frames")
    logs_dir = os.path.join(job_dir, "logs")
    os.makedirs(frames_dir)
    os.makedirs(logs_dir)
    job_metadata = {
        "submitted_from": "Cinema 4D",
        "job_scene_folder": os.path.dirname(scene),
        "chunk_size": chunk_size,
        "notes": notes,
        "render_output_path": output,
    }
    if metadata:
        job_metadata.update(metadata)

    job = {
        "id": job_id,
        "name": name,
        "created_at": utc_now(),
        "scene": scene,
        "source_scene": scene,
        "output": output,
        "path_mode": "c4d_saved_job_copy",
        "frames": frames,
        "status": "queued",
        "metadata": job_metadata,
    }
    write_json_atomic(os.path.join(job_dir, "job.json"), job)

    for frame in frames:
        write_json_atomic(
            os.path.join(frames_dir, "%04d.json" % frame),
            {
                "frame": frame,
                "status": "queued",
                "attempts": 0,
                "worker_id": None,
                "updated_at": utc_now(),
            },
        )
    return job_id


class DreamRenderDialog(gui.GeDialog):
    def __init__(self):
        super(DreamRenderDialog, self).__init__()
        self.doc = c4d.documents.GetActiveDocument()
        self.config = read_config()
        self.check_rows = []
        self.check_table = SceneCheckTableArea()
        self.check_table.dialog = self
        self.check_steps = []
        self.check_step_index = 0
        self.check_step_phase = ""
        start, end, frame_source = get_render_range(self.doc)
        self.start = start
        self.end = end
        self.frame_source = frame_source

    def CreateLayout(self):
        self.SetTitle("Submit to DreamRender")
        self.GroupBegin(2000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 2, 1)
        self.GroupBorderSpace(12, 12, 12, 12)
        self.GroupSpace(18, 10)
        self.GroupBegin(2001, c4d.BFH_LEFT | c4d.BFV_TOP, 1, 0, title="Submit")
        self.GroupBorderSpace(10, 10, 10, 10)
        self.GroupSpace(0, 7)
        self.AddButton(IDC_CHECK_SCENE, c4d.BFH_SCALEFIT, name="Check Scene")
        self.AddButton(IDC_OPEN_DASHBOARD, c4d.BFH_SCALEFIT, name="Open Dashboard")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Queue")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Share")
        self.AddEditText(IDC_SHARE, c4d.BFH_SCALEFIT)
        self.AddButton(IDC_BROWSE_SHARE, c4d.BFH_LEFT, name="Browse")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Job")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Job name")
        self.AddEditText(IDC_NAME, c4d.BFH_SCALEFIT)
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Batching")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Frames per batch")
        self.AddEditNumberArrows(IDC_CHUNK_SIZE, c4d.BFH_LEFT)
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.GroupBegin(2004, c4d.BFH_SCALEFIT, 1, 0, title="Takes")
        self.GroupBorderSpace(6, 6, 6, 6)
        self.AddCheckbox(IDC_MARKED_TAKES, c4d.BFH_LEFT, initw=0, inith=0, name="Render all marked takes")
        self.GroupEnd()
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Notes")
        self.AddEditText(IDC_NOTES, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.AddCheckbox(IDC_IGNORE_WARNINGS, c4d.BFH_LEFT, initw=0, inith=0, name="Ignore warnings on submit")
        self.AddButton(IDC_SUBMIT, c4d.BFH_SCALEFIT, name="Submit Project")
        self.GroupEnd()
        self.GroupBegin(2002, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0, title="Scene Check")
        self.GroupBorderSpace(12, 10, 12, 10)
        self.GroupSpace(0, 8)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Render farm preflight")
        self.AddStaticText(IDC_CHECK_PROGRESS, c4d.BFH_LEFT, name="Idle")
        self.AddUserArea(IDC_CHECK_TABLE, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 760, 380)
        self.AttachUserArea(self.check_table, IDC_CHECK_TABLE)
        self.AddStaticText(IDC_CHECK_STATUS, c4d.BFH_SCALEFIT, name="Run Check Scene before submitting.")
        self.GroupEnd()
        return True

    def InitValues(self):
        self.SetString(IDC_SHARE, self.config.get("share", DEFAULT_SHARE))
        self.SetString(IDC_NAME, os.path.splitext(get_document_name(self.doc))[0])
        self.SetInt32(IDC_CHUNK_SIZE, int(self.config.get("chunk_size", 5)))
        self.SetBool(IDC_MARKED_TAKES, bool(self.config.get("marked_takes", False)))
        self.SetBool(IDC_IGNORE_WARNINGS, bool(self.config.get("ignore_warnings", False)))
        self.SetString(IDC_NOTES, self.config.get("notes", ""))
        self.start_scene_check_animation()
        return True

    def Command(self, control_id, msg):
        if control_id == IDC_SUBMIT:
            self.submit()
            return True
        if control_id == IDC_BROWSE_SHARE:
            path = c4d.storage.LoadDialog(title="Choose DreamRender queue folder", flags=c4d.FILESELECT_DIRECTORY)
            if path:
                self.SetString(IDC_SHARE, path)
            return True
        if control_id == IDC_OPEN_DASHBOARD:
            webbrowser.open("http://127.0.0.1:8766")
            return True
        if control_id == IDC_CHECK_SCENE:
            self.start_scene_check_animation()
            return True
        if control_id == IDC_MARKED_TAKES:
            self.start_scene_check_animation()
            return True
        return True

    def collect_submit_values(self):
        share = self.GetString(IDC_SHARE).strip()
        name = self.GetString(IDC_NAME).strip() or os.path.splitext(get_document_name(self.doc))[0]
        self.start, self.end, self.frame_source = get_render_range(self.doc)
        output = get_output_path_info(self.doc)[0]
        start = self.start
        end = self.end
        chunk_size = self.GetInt32(IDC_CHUNK_SIZE)
        submit_marked_takes = self.GetBool(IDC_MARKED_TAKES)
        notes = self.GetString(IDC_NOTES).strip()
        ignore_warnings = self.GetBool(IDC_IGNORE_WARNINGS)
        return share, name, output, start, end, chunk_size, submit_marked_takes, notes, ignore_warnings

    def update_check_table(self, rows, current_index=-1, spinner=""):
        self.check_rows = rows
        self.check_table.set_rows(rows, current_index=current_index, spinner=spinner)

    def start_scene_check_animation(self):
        self.SetTimer(0)
        share, name, output, start, end, chunk_size, submit_marked_takes, notes, ignore_warnings = self.collect_submit_values()
        self.check_steps = scene_report_step_builders(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        self.check_step_index = 0
        self.check_step_phase = "show"
        self.update_check_table([])
        self.SetString(IDC_CHECK_STATUS, "Checking scene...")
        self.SetString(IDC_CHECK_PROGRESS, "Starting scene check")
        self.SetTimer(95)

    def Timer(self, msg):
        dragging = self.check_table.poll_drag()
        if not self.check_steps or self.check_step_index >= len(self.check_steps):
            self.SetTimer(20 if dragging or self.check_table.is_dragging() else 0)
            return
        label, build_row = self.check_steps[self.check_step_index]
        spinner_frames = ("◐", "◓", "◑", "◒")
        spinner = spinner_frames[self.check_step_index % len(spinner_frames)]
        if self.check_step_phase == "show":
            pending_row = {"label": label, "level": None, "message": "checking...", "info": "", "text": ""}
            self.SetString(
                IDC_CHECK_PROGRESS,
                "%s Checking %s (%d/%d)" % (spinner, label, self.check_step_index + 1, len(self.check_steps)),
            )
            self.update_check_table(self.check_rows + [pending_row], current_index=len(self.check_rows), spinner=spinner)
            self.check_step_phase = "build"
            return

        row = build_row()
        rows = list(self.check_rows)
        if rows and rows[-1].get("message") == "checking..." and rows[-1].get("label") == row.get("label"):
            rows[-1] = row
        else:
            rows.append(row)
        self.update_check_table(rows)
        self.check_step_index += 1
        self.check_step_phase = "show"
        if self.check_step_index >= len(self.check_steps):
            self.SetTimer(0)
            self.SetString(IDC_CHECK_PROGRESS, "Done: %d checks" % len(rows))
            self.SetString(IDC_CHECK_STATUS, report_status_text(rows))

    def run_scene_check(self, show_dialog=True):
        share, name, output, start, end, chunk_size, submit_marked_takes, notes, ignore_warnings = self.collect_submit_values()
        checks = run_scene_checks(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        rows = farm_style_scene_report(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        report = format_scene_report(rows)
        self.update_check_table(rows)
        self.SetString(IDC_CHECK_PROGRESS, "Done: %d checks" % len(rows))
        self.SetString(IDC_CHECK_STATUS, report_status_text(rows))
        if show_dialog:
            gui.MessageDialog(report)
        return checks

    def submit(self):
        share, name, output, start, end, chunk_size, submit_marked_takes, notes, ignore_warnings = self.collect_submit_values()
        output_source = get_output_path_info(self.doc)[1]
        frame_source = self.frame_source
        render_engine, render_engine_info_text = detect_render_engine(self.doc)
        chunk_size = max(1, self.GetInt32(IDC_CHUNK_SIZE))
        checks = run_scene_checks(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        preflight_summary = check_summary_line(checks)
        if has_check_level(checks, CHECK_ERROR):
            gui.MessageDialog(format_checks(checks, "DreamRender cannot submit this scene yet"))
            return
        if has_check_level(checks, CHECK_WARNING) and not ignore_warnings:
            if not gui.QuestionDialog("%s\n\nSubmit anyway?" % format_checks(checks, "DreamRender found warnings")):
                return

        if not confirm_save_before_submit(self.doc):
            return
        if not save_current_document(self.doc):
            return
        source_scene = source_scene_path(self.doc)
        source_scene_mtime = path_mtime(source_scene)

        project = get_project_folder(self.doc)
        jobs_root = os.path.join(project, DEFAULT_JOB_FOLDER)
        job_stamp = "%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])
        job_scene_dir = os.path.join(jobs_root, job_stamp)
        os.makedirs(job_scene_dir)
        source_name = os.path.splitext(get_document_name(self.doc))[0]
        scene_path = os.path.join(job_scene_dir, "%s_%s.c4d" % (source_name, job_stamp))

        flags = c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST
        saved = c4d.documents.SaveDocument(self.doc, scene_path, flags, c4d.FORMAT_C4DEXPORT)
        if not saved:
            gui.MessageDialog("Cinema 4D could not save the DreamRender job scene.")
            return

        frames = list(range(start, end + 1))
        marked_takes = get_marked_takes(self.doc) if submit_marked_takes else []
        take_driven = bool(marked_takes) and marked_takes_have_different_render_settings(self.doc, marked_takes)
        if submit_marked_takes and not marked_takes:
            gui.MessageDialog("No marked takes were found. Mark the takes in the Take Manager or disable marked-take submission.")
            return
        if marked_takes:
            labels = [take_name(take) for take in marked_takes]
            duplicates = sorted(set(label for label in labels if labels.count(label) > 1))
            if duplicates:
                gui.MessageDialog("Marked takes must have unique names for commandline rendering:\n%s" % "\n".join(duplicates))
                return

        try:
            common_metadata = {
                "project_folder": project,
                "document_name": get_document_name(self.doc),
                "source_scene": source_scene,
                "source_scene_mtime": source_scene_mtime,
                "source_scene_saved_at": utc_now(),
                "submitted_by": os.environ.get("USERNAME") or os.environ.get("USER") or "",
                "submitted_machine": os.environ.get("COMPUTERNAME") or "",
                "submitter_version": "DreamRender C4D 2026",
                "preflight_summary": preflight_summary,
                "output_source": output_source,
                "frame_source": frame_source,
                "render_engine": render_engine,
                "render_engine_info": render_engine_info_text,
            }
            if marked_takes:
                group_id = "%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])
                job_ids = []
                for index, take in enumerate(marked_takes, 1):
                    label = take_name(take)
                    take_output = output
                    take_frames = frames
                    take_frame_source = frame_source
                    take_render_setting = render_data_name(self.doc.GetActiveRenderData())
                    if take_driven:
                        take_render_data = get_take_render_data(self.doc, take)
                        take_output = get_output_path_info_for_render_data(self.doc, take_render_data)[0]
                        take_start, take_end, take_frame_source = get_render_range_from_render_data(self.doc, take_render_data)
                        take_frames = list(range(take_start, take_end + 1))
                        take_render_setting = render_data_name(take_render_data)
                    job_ids.append(
                        create_job(
                            share,
                            scene_path,
                            take_output,
                            take_frames,
                            "%s - %s" % (name, label),
                            chunk_size,
                            notes,
                            dict(common_metadata, **{
                                "group_id": group_id,
                                "group_name": name,
                                "group_index": index,
                                "group_size": len(marked_takes),
                                "take_name": label,
                                "take_render_setting": take_render_setting,
                                "frame_source": take_frame_source,
                            }),
                        )
                    )
            else:
                job_ids = [
                    create_job(
                        share,
                        scene_path,
                        output,
                        frames,
                        name,
                        chunk_size,
                        notes,
                        common_metadata,
                    )
                ]
        except Exception as exc:
            gui.MessageDialog("Could not submit DreamRender job:\n%s" % exc)
            return

        write_config(
            {
                "share": share,
                "chunk_size": chunk_size,
                "notes": notes,
                "marked_takes": submit_marked_takes,
                "ignore_warnings": ignore_warnings,
            }
        )
        append_submit_history(
            self.doc,
            {
                "submitted_at": utc_now(),
                "source_scene": source_scene,
                "source_scene_mtime": source_scene_mtime,
                "job_scene": scene_path,
                "job_ids": job_ids,
                "name": name,
                "output": output,
                "frames": "%d-%d" % (start, end),
                "render_engine": render_engine,
                "preflight_summary": preflight_summary,
            },
        )
        if marked_takes:
            gui.MessageDialog("Submitted %d marked takes to DreamRender:\n%s\n\nScene copy:\n%s" % (len(job_ids), "\n".join(job_ids), scene_path))
        else:
            gui.MessageDialog("Submitted DreamRender job:\n%s\n\nScene copy:\n%s" % (job_ids[0], scene_path))
        self.Close()


dialog = None


def main():
    global dialog
    dialog = DreamRenderDialog()
    dialog.Open(c4d.DLG_TYPE_ASYNC, defaultw=980, defaulth=520)


if __name__ == "__main__":
    main()
