# DreamRender

DreamRender is lightweight render farm software for small Cinema 4D 2026 setups
using Redshift or Octane. It is built for artists who have a few powerful
machines at home or in a small studio and want any available machine to pick up
frames automatically.

It follows a Deadline-style render manager workflow, but keeps the architecture
simple: every machine points to the same DreamRender share, and workers join or
leave without a database server.

## Start Here

New install? Follow the artist-friendly guide:

**[Install DreamRender](INSTALL.md)**

That guide covers:

- installing regular Python
- starting the DreamRender app
- choosing the shared queue folder
- installing the Cinema 4D plugin
- starting workers on render machines
- submitting from Cinema 4D
- fixing the most common setup problems

## What You Get

- A Cinema 4D submitter plugin with a scene checker.
- A desktop control app, so workers do not need command-line use.
- A clean browser dashboard for jobs, takes, workers, progress, logs, previews,
  frame ownership, and render statistics.
- Frame batching, so heavy scenes do not reload for every single frame.
- Marked-take submission, grouped in the dashboard.
- Worker colors, job status labels, folder open actions, archive/requeue/cancel
  controls, and stale-worker recovery.
- Cinema 4D output paths are preserved from Render Settings, including common
  Cinema 4D tokens.

## Recommended Setup

Use the same project path on every machine. For example, if the project is on
drive `P:\` on the workstation, map it as `P:\` on the render node too.

Use one shared queue folder that every machine can read and write:

```text
DreamRenderShare/
  jobs/
  workers/
```

The queue folder can live on a NAS, a shared drive, or one of the machines.

## Day-To-Day Workflow

1. Start `scripts\start-dreamrender-app.bat`.
2. In the app, choose the DreamRender share folder.
3. Click `Start DreamRender` on every machine that should render.
4. In Cinema 4D, open `Extensions > DreamRender Submit Render`.
5. Click `Check Scene`.
6. Click `Submit Project`.
7. Confirm `Save` when DreamRender asks to save the scene.
8. Watch the dashboard.

## Cinema 4D Plugin

Install the plugin with:

```bat
scripts\install-c4d-plugin-2026.bat
```

Restart Cinema 4D 2026 after installing. The command appears as:

```text
Extensions > DreamRender Submit Render
```

The submitter reads the active Cinema 4D Render Settings for:

- frame range
- output path
- output format
- Redshift, Octane, and multipass settings
- marked takes and take-specific render settings

DreamRender saves the current scene, then creates a separate job-scene copy in a
`DreamRenderJobs` folder near the project. Workers render that copy, while output
still goes to the path set in Cinema 4D Render Settings.

## Renderer Support

DreamRender supports Cinema 4D command-line rendering for Redshift and Octane.
The render engine must be installed and licensed on every worker machine.

For Octane jobs submitted from the Cinema 4D plugin, DreamRender stores the
detected renderer in the job metadata. Workers then use Octane's recommended
Cinema 4D command-line module path pattern so the C4D Octane plugin can load in
background renders.

## Dashboard

The dashboard is opened from the DreamRender app. It shows:

- grouped jobs and marked takes
- current worker activity
- done/rendering/queued/error states
- progress bars and render timing
- frame ownership by worker color
- logs and browser-friendly previews
- archive, requeue, cancel, pause, resume, and priority controls

PNG, JPG, WebP, and GIF previews display directly in the browser. EXR/TIFF files
need a converter on the monitor machine for thumbnails, such as ImageMagick,
OpenImageIO, or ffmpeg.

## Command Line

The app is the preferred workflow. These commands are mainly for troubleshooting
or automation.

Run the app:

```bat
scripts\start-dreamrender-app.bat
```

Run a worker:

```bat
scripts\start-worker-c4d2026.bat "\\RenderServer\DreamRender"
```

Run the monitor:

```bat
scripts\start-monitor.bat "\\RenderServer\DreamRender"
```

Check queue status:

```bat
scripts\dreamrender.bat status --share "\\RenderServer\DreamRender"
```

## Development Install

For editable Python development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

DreamRender can also run without installing the Python package because the batch
scripts set `PYTHONPATH` to the local `src` folder.

## License

DreamRender is released under the MIT License. See [LICENSE](LICENSE).

Cinema 4D, Redshift, Octane, Maxon, and OTOY product names belong to their
respective owners. DreamRender does not include Cinema 4D, Redshift, Octane,
plugins, render licenses, or third-party assets.

## Notes

- Use regular Python 3.10 or newer from python.org. Do not use Cinema 4D
  `c4dpy.exe` for the worker.
- Keep Cinema 4D, Redshift/Octane, plugins, OCIO, fonts, caches, and assets
  consistent across machines.
- Renderer licensing must allow command-line rendering on each worker.
- Map project folders identically on every machine for the most predictable
  output and asset behavior.
