# Install DreamRender

This is the simple setup path for Cinema 4D 2026 + Redshift.

You only need three things:

1. DreamRender copied to each machine.
2. Regular Python 3.10 or newer installed on each machine.
3. One shared DreamRender queue folder that every machine can read and write.

## 1. Download DreamRender

Download or clone this repository on each machine.

Recommended folder:

```text
C:\DreamRender
```

Any folder is fine, but keep it simple and avoid moving it after setup.

## 2. Install Python

Install regular Python 3.10 or newer from:

[https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)

During install, enable:

```text
Add python.exe to PATH
```

DreamRender workers should use regular Python. Do not use Cinema 4D `c4dpy.exe`
for the worker.

Quick check:

```bat
scripts\dreamrender.bat --help
```

If this opens DreamRender help, Python is ready.

## 3. Create The DreamRender Share

Create one shared folder that all machines can read and write.

Examples:

```text
\\RenderServer\DreamRender
X:\DreamRenderShare
R:\DreamRenderShare
```

This folder is only for the queue. Your Cinema 4D project files can stay in your
normal project folder.

Important: each render machine also needs access to the project files and output
folder using the same paths that Cinema 4D uses.

## 4. Start The App

Double-click:

```text
scripts\start-dreamrender-app.bat
```

In the app:

1. Choose the DreamRender share folder.
2. Click `Initialize Share` if it is a new queue folder.
3. Click `Start Monitor`.
4. Click `Open Dashboard`.
5. Click `Start DreamRender` on every machine that should render.

When the app closes, its worker is stopped too. This keeps the render node state
clear and avoids hidden workers running in the background.

## 5. Install The Cinema 4D Plugin

Run:

```text
scripts\install-c4d-plugin-2026.bat
```

Then restart Cinema 4D 2026.

Open the submitter from:

```text
Extensions > DreamRender Submit Render
```

If you do not see it:

1. Start Cinema 4D 2026 once.
2. Close Cinema 4D.
3. Run `scripts\install-c4d-plugin-2026.bat` again.
4. Start Cinema 4D again.
5. Check the Extensions menu and Command Manager.

## 6. Submit A Render

In Cinema 4D:

1. Open your scene.
2. Set the output path in Render Settings.
3. Set the frame range in Render Settings.
4. Open `Extensions > DreamRender Submit Render`.
5. Set the DreamRender share path.
6. Set `Frames per batch`.
7. Optional: enable `Render all marked takes`.
8. Click `Check Scene`.
9. Fix errors. Warnings can be ignored if you choose.
10. Click `Submit Project`.
11. Click `Save` when DreamRender asks to save the scene.

DreamRender saves the current scene first, then creates a separate job copy in a
`DreamRenderJobs` folder near the project. Workers render that job copy.

## 7. Render Marked Takes

To submit multiple takes:

1. Mark the takes in Cinema 4D's Take Manager.
2. Enable `Render all marked takes` in DreamRender.
3. Click `Check Scene`.
4. Submit.

Each marked take becomes a separate render job. The dashboard groups them
together.

If marked takes use different render settings, DreamRender uses each take's own
output path and frame range.

## 8. Frames Per Batch

`Frames per batch` controls how many contiguous frames one worker renders per
Cinema 4D command-line launch.

Good starting values:

```text
Fast-loading scene: 1-5
Heavy scene: 5-20
Very heavy scene: 20+
```

Higher values reduce scene reload time. Lower values balance work more evenly
between machines.

## 9. Common Problems

### `dreamrender` is not recognized

Use the batch files in the `scripts` folder instead of typing `dreamrender`
directly:

```bat
scripts\start-dreamrender-app.bat
```

or:

```bat
scripts\dreamrender.bat status --share "\\RenderServer\DreamRender"
```

### Python is not found

Install Python 3.10 or newer from python.org. If Windows opens the Microsoft
Store instead, disable the Python app execution aliases in Windows Settings.

### The C4D plugin is missing

Run:

```bat
scripts\install-c4d-plugin-2026.bat
```

Then restart Cinema 4D 2026.

### A worker is offline in the dashboard

Open the DreamRender app on that machine and click `Start DreamRender`.

If the machine is still rendering but the dashboard says offline, stop and start
DreamRender from the app so the worker heartbeat is refreshed.

### Output goes to the wrong place

DreamRender uses the output path from Cinema 4D Render Settings. Make sure every
machine can access that same path.

For best results, map project folders and output folders identically on every
machine.

### EXR previews do not show in the dashboard

Browsers cannot display EXR directly. Install one of these on the machine
running the monitor:

- ImageMagick
- OpenImageIO
- ffmpeg

PNG, JPG, WebP, and GIF previews work without conversion.

## 10. Updating DreamRender

After pulling or downloading a newer version:

1. Close Cinema 4D.
2. Close the DreamRender app.
3. Replace/update the DreamRender folder.
4. Run `scripts\install-c4d-plugin-2026.bat`.
5. Restart Cinema 4D.
6. Start `scripts\start-dreamrender-app.bat`.

## What DreamRender Does Not Do Yet

- It does not collect every texture/cache/proxy into a package.
- It does not install Cinema 4D, Redshift, fonts, OCIO, or plugins.
- It does not solve license issues.
- It does not make different drive mappings magically equivalent.

Keep the render machines as similar as possible. That is the boring part, but it
makes the render farm feel calm.
