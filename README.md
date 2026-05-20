# DreamRender

DreamRender is a small render queue for a home Cinema 4D + Redshift setup.
It is intentionally folder-based: workers on any machine can join by pointing at
the same shared directory.

## What works in this MVP

- Create a shared queue folder.
- Submit a `.c4d` scene as a frame-based job while preserving scene/output paths.
- Run one or more workers on different machines.
- Workers heartbeat, claim frames atomically, render them, and mark them done or failed.
- Stale frames can be reclaimed when a worker disappears.
- Job status can be inspected from the command line.

## Install for development

```powershell
cd C:\DreamRender
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Quick start

For day-to-day use, launch the desktop control panel:

```bat
C:\DreamRender\scripts\start-dreamrender-app.bat
```

From there you can:

- start DreamRender with one button
- start or stop this machine's worker
- start the monitor and open the dashboard
- initialize the queue folder
- open the queue folder
- create a Desktop shortcut
- set batch size and run diagnostics
- keep the worker running automatically if it exits unexpectedly
- reset the worker name to the current computer name
- detect and adopt an already-running worker for this machine
- stop the worker when the control app closes

For artist-facing use, this is the preferred workflow. The command-line examples
below are still useful for troubleshooting and automation.

On Windows `cmd.exe`, use one-line commands. The backtick examples are for
PowerShell only.

You can run DreamRender without installing it by using:

```bat
C:\DreamRender\scripts\dreamrender.bat status --share "C:\DreamRenderShare"
```

Create a shared queue folder. This folder must be visible to every render node.

```powershell
dreamrender init-share --share "\\RenderServer\DreamRender"
```

Submit a job:

```powershell
dreamrender submit `
  --share "\\RenderServer\DreamRender" `
  --scene "P:\projects\shot_010\shot_010.c4d" `
  --frames 1-120 `
  --output "P:\renders\shot_010" `
  --name "shot_010"
```

By default DreamRender stores the exact scene and output paths you submit. That
is the right mode when every render machine has the project folder mapped the
same way, because relative assets, caches, Redshift proxies, and output paths
stay exactly where Cinema 4D expects them.

If you want to copy only the `.c4d` file into the queue folder, add
`--copy-scene`. Shared project paths are still recommended for real work because
copying the scene does not collect textures, caches, proxies, or plugin assets.

Run a worker on each machine:

```powershell
dreamrender worker `
  --share "\\RenderServer\DreamRender" `
  --c4d "C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe" `
  --chunk-size 5
```

Or from `cmd.exe` without installing:

```bat
C:\DreamRender\scripts\start-worker-c4d2026.bat "\\RenderServer\DreamRender"
```

`--chunk-size 5` means each worker launches Cinema 4D once for five contiguous
frames, instead of loading the scene once per frame. Increase it for heavy scenes
if startup/load time dominates render time; decrease it if you want finer
balancing between machines.

Each worker machine needs regular Python 3.10 or newer. Do not use Cinema 4D's
`c4dpy.exe` as the worker runtime; on some machines it can crash outside Cinema
4D.

Check status:

```powershell
dreamrender status --share "\\RenderServer\DreamRender"
```

Run the monitor:

```powershell
dreamrender monitor --share "\\RenderServer\DreamRender"
```

Or from `cmd.exe` without installing:

```bat
C:\DreamRender\scripts\start-monitor.bat "\\RenderServer\DreamRender"
```

Each machine running the monitor needs regular Python 3.10 or newer.

Then open:

```text
http://127.0.0.1:8765
```

The dashboard can display browser-friendly outputs directly: PNG, JPG, WebP,
and GIF. EXR and TIFF renders are detected, but browsers cannot display them by
themselves. To get dashboard thumbnails for EXR/TIFF frames, install one of
these on the machine running the monitor and make sure it is on `PATH`:
ImageMagick (`magick`), OpenImageIO (`oiiotool`), or ffmpeg.

## Cinema 4D submitter

The Cinema 4D submitter lives here:

```text
cinema4d/DreamRenderSubmit.py
```

Drop that file into Cinema 4D's scripts folder and run it from Script Manager.
It opens a small submit dialog with:

- DreamRender share path
- job name
- output path
- start frame
- end frame
- frames per batch
- optional marked-take submission
- scene checker / preflight

Start and end frame are read from Cinema 4D's active Render Settings frame
range. The submitter respects Manual, Current Frame, All Frames, and Preview
Range modes, then shows the detected source beside the frame field.

Use `Check Scene` before submitting when you want a render-farm-style preflight.
It checks whether the scene is saved, the queue and job folders are writable,
the frame range and batch size are valid, marked takes are usable, the output
path looks sane, and Cinema 4D reports missing assets. Errors block submit;
warnings ask for confirmation.

Frames per batch controls how many contiguous frames a worker claims and renders
per Cinema 4D commandline launch for that job. Higher values reduce scene reload
overhead; lower values balance work more evenly between machines.

Enable marked-take submission when you want every checked/marked Take in Cinema
4D's Take Manager to become its own render job. DreamRender groups those jobs
together in the dashboard, passes `-take "Take Name"` to Cinema 4D commandline,
and preserves the output path exactly as it is set in Cinema 4D Render Settings.
Cinema 4D tokens such as `$prj` and `$take` are passed through to Cinema 4D, and
DreamRender expands the common tokens only when searching for dashboard previews.
Marked takes must have unique names.

For Cinema 4D 2026 on this machine, you can install it with:

```bat
C:\DreamRender\scripts\install-c4d-submitter-2026.bat
```

Then restart Cinema 4D and open the Script Manager. The script is named:

```text
DreamRenderSubmit.py
```

To install the menu command plugin instead:

```bat
C:\DreamRender\scripts\install-c4d-plugin-2026.bat
```

Restart Cinema 4D and look for `DreamRender Submit Render` in the Extensions
menu or Command Manager.

When you submit, it saves a copy of the current document into a folder beside
the project:

```text
YourProject/
  DreamRenderJobs/
    20260520-123456-a1b2c3d4/
      YourScene_20260520-123456-a1b2c3d4.c4d
```

That saved copy is the scene sent to the queue. Because the folder sits inside
or next to your mapped project folder, workers with the same drive mapping can
resolve the same scene, assets, caches, Redshift proxies, and output path.

## Command template

Cinema 4D command line flags can vary by version and pipeline setup, so workers
use a template. The default is:

```text
"{c4d}" -render "{scene}" {take_arg} -frame {start_frame} {end_frame}
```

DreamRender does not pass `-oimage` by default. Cinema 4D writes to the output
path stored in the saved scene's Render Settings, so relative paths and Cinema
4D tokens are interpreted by Cinema 4D exactly as they are in the project.

You can override it:

```powershell
dreamrender worker `
  --share "\\RenderServer\DreamRender" `
  --c4d "C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe" `
  --command-template '"{c4d}" -render "{scene}" {take_arg} -frame {start_frame} {end_frame}'
```

Available placeholders:

- `{c4d}`
- `{scene}`
- `{take}`
- `{take_arg}`
- `{frame}`
- `{start_frame}`
- `{end_frame}`
- `{output}`
- `{job_id}`
- `{job_dir}`
- `{worker_id}`

## Folder layout

```text
DreamRenderShare/
  jobs/
    job-id/
      job.json
      frames/
        0001.json
      logs/
  workers/
    machine-name.json
```

## Notes

- Keep Cinema 4D, Redshift, plugins, OCIO, fonts, and assets consistent across machines.
- Map project folders identically on every machine when you want scene, asset, cache, and output paths to resolve exactly.
- Redshift licensing must allow rendering on each worker.
- For the first version, frames are the unit of work. Chunking can be added later.
