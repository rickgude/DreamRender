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

DreamRender uses a clean desktop app shell. See **[DreamRender App](APP_V2.md)**
for architecture and development notes.

For normal use, download a packaged DreamRender release. Cloning the GitHub
source is meant for developers and people who want to build the app themselves.

That guide covers:

- installing regular Python
- setting up the DreamRender app
- choosing the shared queue folder
- installing the Cinema 4D plugin from the app
- starting workers on render machines
- submitting from Cinema 4D
- fixing the most common setup problems

## What You Get

- A Cinema 4D submitter plugin with a scene checker.
- A desktop control app, so workers do not need command-line use.
- An integrated dashboard for jobs, takes, workers, progress, logs, previews,
  frame ownership, and render statistics.
- Frame batching, so heavy scenes do not reload for every single frame.
- Marked-take submission, grouped in the dashboard.
- Worker colors, job status labels, folder open actions, archive/requeue/cancel
  controls, and stale-worker recovery.
- App health diagnostics for missing Cinema 4D paths, plugin install state,
  queue write access, worker heartbeat loss, failed frames, and stale locks.
- Failed frames stay failed until you intentionally repair or requeue them, so
  broken frames do not loop forever in the background.
- Failed jobs show grouped failure reasons, retry controls, and a manual
  verified-done escape hatch for outputs you have checked yourself.
- Submit history records source-scene timestamps, renderer, preflight summary,
  and job-scene copy paths so you can verify which scene version rendered.
- Cinema 4D output paths are preserved from Render Settings, including common
  Cinema 4D tokens.

## Recommended Setup

DreamRender itself can live anywhere on each machine. The important part is the
shared queue folder and your Cinema 4D project/output paths.

Use the same project path on every machine. For example, if the project is on
drive `P:\` on the workstation, map it as `P:\` on the render node too.

Use one shared queue folder that every machine can read and write:

```text
DreamRenderShare/
  jobs/
  workers/
```

The queue folder can live on a NAS, a shared drive, or one of the machines. On a
fresh install, DreamRender suggests a local `Documents\DreamRenderShare` folder
so the app can start cleanly. For multiple machines, change that to the same
network/shared folder on every machine.

## Day-To-Day Workflow

1. Start `START_DREAMRENDER.vbs`.
2. Set the shared queue folder and confirm the detected Cinema 4D Commandline path.
3. Click `Install C4D Plugin` once per workstation.
4. Make sure the `Health` panel is OK.
5. Click `Start DreamRender` on every machine that should render.
6. In Cinema 4D, open `Extensions > DreamRender Submit Render`.
7. Click `Check Scene`.
8. Click `Submit Project`.
9. Confirm `Save` when DreamRender asks to save the scene.
10. Watch the integrated dashboard.

## Which Script Should I Use?

Use `START_DREAMRENDER.vbs` for normal work. It opens the native DreamRender app
without showing a console window. The app keeps the proven Python renderfarm
engine underneath, but gives artists one clean control surface.

If the packaged native app executable is not present, the launcher falls back to
the local Python app UI without requiring Node.js or Rust. Developers can still
use the Tauri commands in `APP_V2.md` when they want to build the native shell.

Advanced scripts live in `scripts\advanced`. Use
`ADVANCED_Worker_Only_C4D2026.bat` only when you deliberately want a visible
troubleshooting console.

## Cinema 4D Plugin

Install the plugin from the DreamRender App with `Install C4D Plugin`.

The app writes the current DreamRender share into the Cinema 4D submitter config
when it installs the plugin, so the submitter opens with the same queue path.

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

The scene checker also validates the DreamRender share, output folder
write-access, cache/proxy assets, external asset paths, known workers, and
whether the source scene changed since its last DreamRender submission.

DreamRender saves the current scene, then creates a separate job-scene copy in a
`DreamRenderJobs` folder near the project. Workers render that copy, while output
still goes to the path set in Cinema 4D Render Settings.

## Renderer Support

DreamRender supports Cinema 4D command-line rendering for Redshift and Octane.
The render engine must be installed and licensed on every worker machine.

For Octane jobs submitted from the Cinema 4D plugin, DreamRender stores the
detected renderer in the job metadata. Workers then use Octane's recommended
Cinema 4D command-line module path pattern so the C4D Octane plugin can load in
background renders. Octane jobs also receive an explicit command-line output path
because Octane can hide Cinema 4D's standard Save controls.

## Dashboard

The dashboard is opened from the DreamRender app. It shows:

- grouped jobs and marked takes
- current worker activity
- done/rendering/queued/error states
- progress bars and render timing
- frame ownership by worker color
- logs and browser-friendly previews
- archive, requeue, cancel, pause, resume, and priority controls
- drag priority controls plus explicit Up/Down buttons as a reliable fallback
- failure summaries with `Retry Failed` and `Mark Failed Done`
- submit metadata for source scene, renderer, preflight summary, and timestamps

PNG, JPG, WebP, and GIF previews display directly in the browser. EXR/TIFF files
need a converter on the monitor machine for thumbnails, such as ImageMagick,
OpenImageIO, or ffmpeg.

## Command Line

The app is the preferred workflow. These commands are mainly for troubleshooting
or automation.

Run the app without a console:

```bat
START_DREAMRENDER.vbs
```

The commands below are advanced troubleshooting fallbacks and may show a
console.

Run a worker:

```bat
scripts\advanced\ADVANCED_Worker_Only_C4D2026.bat "\\YOUR-SERVER\DreamRenderShare"
```

Run the monitor:

```bat
scripts\advanced\ADVANCED_Monitor_Only.bat "\\YOUR-SERVER\DreamRenderShare"
```

Check queue status:

```bat
scripts\advanced\ADVANCED_Command_Line.bat status --share "\\YOUR-SERVER\DreamRenderShare"
```

## Development Install

For editable Python development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

DreamRender can also run without installing the Python package because the
launchers set `PYTHONPATH` to the local `src` folder.

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
