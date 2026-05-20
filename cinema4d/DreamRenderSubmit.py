"""DreamRender Cinema 4D submit script.

Drop this file into your Cinema 4D scripts folder and run it from Script Manager.
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


DEFAULT_SHARE = r"\\RenderServer\DreamRender"
DEFAULT_JOB_FOLDER = "DreamRenderJobs"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), "DreamRenderSubmit.json")

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
IDC_OUTPUT_SOURCE = 1012
IDC_FRAME_SOURCE = 1013
IDC_CHECK_SCENE = 1014

CHECK_ERROR = "ERROR"
CHECK_WARNING = "WARNING"
CHECK_OK = "OK"


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
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
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
    fps = doc.GetFps()
    render_data = doc.GetActiveRenderData()
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
    render_data = doc.GetActiveRenderData()
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
    return output


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

    if document_folder:
        add_check(checks, CHECK_OK, "Scene has been saved", os.path.join(document_folder, document_name))
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

    if end < start:
        add_check(checks, CHECK_ERROR, "Frame range is invalid", "End frame must be greater than or equal to start frame.")
    else:
        add_check(checks, CHECK_OK, "Frame range is valid", "%d-%d" % (start, end))

    if chunk_size < 1:
        add_check(checks, CHECK_ERROR, "Frames per batch must be at least 1")
    else:
        add_check(checks, CHECK_OK, "Frames per batch is valid", str(chunk_size))

    if output:
        output_folder = folder_for_output_path(output)
        if output_folder and has_c4d_tokens(output_folder):
            add_check(checks, CHECK_OK, "Output path uses Cinema 4D tokens", "Cinema 4D will resolve these at render time:\n%s" % output)
        elif output_folder and os.path.isdir(output_folder):
            add_check(checks, CHECK_OK, "Output folder exists", output_folder)
        elif output_folder:
            add_check(checks, CHECK_WARNING, "Output folder does not exist yet", output_folder)
        else:
            add_check(checks, CHECK_WARNING, "Output path has no folder", output)
    else:
        add_check(checks, CHECK_ERROR, "Output path is empty", "Set an output path in Cinema 4D Render Settings.")

    marked_takes = get_marked_takes(doc) if submit_marked_takes else []
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
            add_check(checks, CHECK_ERROR, "Missing assets were found", "\n".join(missing[:12]))
        else:
            add_check(checks, CHECK_OK, "No missing assets reported", "%d assets checked" % len(assets))
        if external:
            add_check(
                checks,
                CHECK_WARNING,
                "Assets outside the project folder",
                "Workers need the same path mapping for these files:\n%s" % "\n".join(external[:12]),
            )

    return checks


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
        start, end, frame_source = get_render_range(self.doc)
        self.start = start
        self.end = end
        self.frame_source = frame_source

    def CreateLayout(self):
        self.SetTitle("Submit to DreamRender")
        self.GroupBegin(2000, c4d.BFH_SCALEFIT, 3, 1)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Share")
        self.AddEditText(IDC_SHARE, c4d.BFH_SCALEFIT)
        self.AddButton(IDC_BROWSE_SHARE, c4d.BFH_LEFT, name="Browse")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Job name")
        self.AddEditText(IDC_NAME, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Output")
        self.AddEditText(IDC_OUTPUT, c4d.BFH_SCALEFIT)
        self.AddStaticText(IDC_OUTPUT_SOURCE, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Start frame")
        self.AddEditNumberArrows(IDC_START, c4d.BFH_LEFT)
        self.AddStaticText(IDC_FRAME_SOURCE, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="End frame")
        self.AddEditNumberArrows(IDC_END, c4d.BFH_LEFT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Frames per batch")
        self.AddEditNumberArrows(IDC_CHUNK_SIZE, c4d.BFH_LEFT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Takes")
        self.AddCheckbox(IDC_MARKED_TAKES, c4d.BFH_LEFT, initw=0, inith=0, name="Submit marked takes as a group")
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.AddStaticText(0, c4d.BFH_LEFT, name="Notes")
        self.AddEditText(IDC_NOTES, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="")
        self.GroupEnd()
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddButton(IDC_CHECK_SCENE, c4d.BFH_LEFT, name="Check Scene")
        self.AddButton(IDC_OPEN_DASHBOARD, c4d.BFH_LEFT, name="Open Dashboard")
        self.AddButton(IDC_SUBMIT, c4d.BFH_RIGHT, name="Submit")
        return True

    def InitValues(self):
        self.SetString(IDC_SHARE, self.config.get("share", DEFAULT_SHARE))
        self.SetString(IDC_NAME, os.path.splitext(get_document_name(self.doc))[0])
        output, output_source = get_output_path_info(self.doc)
        self.SetString(IDC_OUTPUT, output)
        self.SetString(IDC_OUTPUT_SOURCE, output_source)
        self.SetInt32(IDC_START, self.start)
        self.SetInt32(IDC_END, self.end)
        self.SetString(IDC_FRAME_SOURCE, self.frame_source)
        self.SetInt32(IDC_CHUNK_SIZE, int(self.config.get("chunk_size", 5)))
        self.SetBool(IDC_MARKED_TAKES, bool(self.config.get("marked_takes", False)))
        self.SetString(IDC_NOTES, self.config.get("notes", ""))
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
            self.run_scene_check(show_dialog=True)
            return True
        return True

    def collect_submit_values(self):
        share = self.GetString(IDC_SHARE).strip()
        name = self.GetString(IDC_NAME).strip() or os.path.splitext(get_document_name(self.doc))[0]
        output = self.GetString(IDC_OUTPUT).strip()
        start = self.GetInt32(IDC_START)
        end = self.GetInt32(IDC_END)
        chunk_size = self.GetInt32(IDC_CHUNK_SIZE)
        submit_marked_takes = self.GetBool(IDC_MARKED_TAKES)
        notes = self.GetString(IDC_NOTES).strip()
        return share, name, output, start, end, chunk_size, submit_marked_takes, notes

    def run_scene_check(self, show_dialog=True):
        share, name, output, start, end, chunk_size, submit_marked_takes, notes = self.collect_submit_values()
        checks = run_scene_checks(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        if show_dialog:
            gui.MessageDialog(format_checks(checks))
        return checks

    def submit(self):
        share, name, output, start, end, chunk_size, submit_marked_takes, notes = self.collect_submit_values()
        output_source = get_output_path_info(self.doc)[1]
        frame_source = self.frame_source
        chunk_size = max(1, self.GetInt32(IDC_CHUNK_SIZE))
        checks = run_scene_checks(self.doc, share, output, start, end, chunk_size, submit_marked_takes)
        if has_check_level(checks, CHECK_ERROR):
            gui.MessageDialog(format_checks(checks, "DreamRender cannot submit this scene yet"))
            return
        if has_check_level(checks, CHECK_WARNING):
            if not gui.QuestionDialog("%s\n\nSubmit anyway?" % format_checks(checks, "DreamRender found warnings")):
                return

        if not save_current_document(self.doc):
            return

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
            if marked_takes:
                group_id = "%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])
                job_ids = []
                for index, take in enumerate(marked_takes, 1):
                    label = take_name(take)
                    job_ids.append(
                        create_job(
                            share,
                            scene_path,
                            output,
                            frames,
                            "%s - %s" % (name, label),
                            chunk_size,
                            notes,
                            {
                                "group_id": group_id,
                                "group_name": name,
                                "group_index": index,
                                "group_size": len(marked_takes),
                                "take_name": label,
                                "project_folder": project,
                                "document_name": get_document_name(self.doc),
                                "output_source": output_source,
                                "frame_source": frame_source,
                            },
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
                        {
                            "project_folder": project,
                            "document_name": get_document_name(self.doc),
                            "output_source": output_source,
                            "frame_source": frame_source,
                        },
                    )
                ]
        except Exception as exc:
            gui.MessageDialog("Could not submit DreamRender job:\n%s" % exc)
            return

        write_config({"share": share, "chunk_size": chunk_size, "notes": notes, "marked_takes": submit_marked_takes})
        if marked_takes:
            gui.MessageDialog("Submitted %d marked takes to DreamRender:\n%s\n\nScene copy:\n%s" % (len(job_ids), "\n".join(job_ids), scene_path))
        else:
            gui.MessageDialog("Submitted DreamRender job:\n%s\n\nScene copy:\n%s" % (job_ids[0], scene_path))
        self.Close()


dialog = None


def main():
    global dialog
    dialog = DreamRenderDialog()
    dialog.Open(c4d.DLG_TYPE_ASYNC, defaultw=520, defaulth=180)


if __name__ == "__main__":
    main()
