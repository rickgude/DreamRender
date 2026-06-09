# Install DreamRender

This is the simple setup path for Cinema 4D 2026 with Redshift or Octane.

You only need three things:

1. DreamRender installed or copied to each machine.
2. One shared DreamRender queue folder that every machine can read and write.
3. Cinema 4D 2026 with Redshift or Octane installed and licensed on each render machine.

## 1. Download DreamRender

For artists, download the latest packaged Windows release from GitHub and run:

```text
DreamRender_..._x64-setup.exe
```

This is the recommended installer. It installs DreamRender for the current user,
creates a Start Menu entry, and includes the local DreamRender backend. Artists
do not need to install Python, Node.js, Rust, or clone this repository.

Every machine can use a different DreamRender install folder. The queue folder
and Cinema 4D project/output paths are the parts that must be shared
consistently.

Node.js, Rust, and Python are only needed if you want to build DreamRender from
source. They are not part of the normal artist setup.

## 2. Create The DreamRender Share

Create one shared folder that all machines can read and write.

Examples:

```text
\\YOUR-SERVER\DreamRenderShare
X:\DreamRenderShare
R:\DreamRenderShare
```

This folder is only for the queue. Your Cinema 4D project files can stay in your
normal project folder.

Important: each render machine also needs access to the project files and output
folder using the same paths that Cinema 4D uses.

On first launch, DreamRender may suggest a local folder such as:

```text
C:\Users\<you>\Documents\DreamRenderShare
```

That is fine for testing on one machine. For a render farm, change it to the
same NAS/shared folder on every machine.

## 3. Start The App

Start DreamRender from the Windows Start Menu.

If you are running a source checkout instead of the packaged release,
double-click:

```text
START_DREAMRENDER.vbs
```

In the app:

1. Choose or create the DreamRender share folder.
2. Confirm the Cinema 4D Render Command. DreamRender tries to detect Cinema 4D
   automatically, but you can also use a custom `.bat` or `.cmd` wrapper if your
   renderer needs environment variables or custom plugin paths.
3. Click `Install C4D Plugin` on the workstation you submit from.
4. Click `Start DreamRender` on every machine that should render.
5. Open the `Dashboard` tab when you want to watch the farm.

The `Health` panel should say the queue, Cinema 4D path, plugin, and queue
access are OK before you render.

When the app closes, its worker is stopped too. This keeps the render node state
clear and avoids hidden workers running in the background.

Use the app for normal work. The `.vbs` launcher opens DreamRender without a
console window when working from source. Only use scripts in `scripts\advanced`
when you deliberately want a visible troubleshooting console.

## 4. Install The Cinema 4D Plugin

The easiest way is from the DreamRender app:

```text
Install C4D Plugin
```

Then restart Cinema 4D 2026.

The installer also writes the selected DreamRender share path into the Cinema 4D
submitter config. If you change the share later, click `Install C4D Plugin`
again or set the share manually in the submitter.

Open the submitter from:

```text
Extensions > DreamRender Submit Render
```

If you do not see it:

1. Start Cinema 4D 2026 once.
2. Close Cinema 4D.
3. Click `Install C4D Plugin` in the DreamRender app again.
4. Start Cinema 4D again.
5. Check the Extensions menu and Command Manager.

## 5. Submit A Render

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
DreamRender also stores a small submit history in that folder, so the dashboard
can show which source scene, renderer, preflight result, and timestamp were used.

## 6. Render Marked Takes

To submit multiple takes:

1. Mark the takes in Cinema 4D's Take Manager.
2. Enable `Render all marked takes` in DreamRender.
3. Click `Check Scene`.
4. Submit.

Each marked take becomes a separate render job. The dashboard groups them
together.

If marked takes use different render settings, DreamRender uses each take's own
output path and frame range.

## 7. Frames Per Batch

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

Use the DreamRender App launcher instead of typing `dreamrender` directly:

```bat
START_DREAMRENDER.vbs
```

### Python is not found

Install Python 3.10 or newer from python.org. If Windows opens the Microsoft
Store instead, disable the Python app execution aliases in Windows Settings.

### The C4D plugin is missing

Click `Install C4D Plugin` in the DreamRender app, then restart Cinema 4D 2026.

### A worker is offline in the dashboard

Open the DreamRender app on that machine and click `Start DreamRender`.

If the machine is still rendering but the dashboard says offline, stop and start
DreamRender from the app so the worker heartbeat is refreshed.

### A job has failed frames

Open the job in the Dashboard and read the failure summary. Fix the cause first,
then click `Retry Failed`.

Use `Mark Failed Done` only if you have opened the render folder and verified
that the output frames are actually there and usable.

### Output goes to the wrong place

DreamRender uses the output path from Cinema 4D Render Settings. Make sure every
machine can access that same path.

For best results, map project folders and output folders identically on every
machine.

### Redshift or Octane renders black frames

Some renderers need environment variables or plugin paths that you normally set
from your own startup batch file. If command-line renders need that setup, point
DreamRender's `Cinema 4D Render Command` field to a wrapper `.bat` or `.cmd`
instead of directly to `Commandline.exe`.

Example:

```bat
@echo off
set "REDSHIFT_COREDATAPATH=C:\ProgramData\Redshift"
set "PATH=C:\ProgramData\Redshift\bin;%PATH%"
"C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe" %*
```

The `%*` part is important. It forwards DreamRender's `-render`, `-frame`,
`-take`, and output arguments to Cinema 4D.

Also make sure texture, cache, OCIO, font, and plugin paths are available on
every worker. Local asset paths only work if the same path exists on every
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
4. Start the DreamRender app and click `Install C4D Plugin`.
5. Restart Cinema 4D.
6. Click `Start DreamRender`.

If the dashboard says a worker needs restart, click `Restart Outdated Workers`
in the dashboard.

## What DreamRender Does Not Do Yet

- It does not collect every texture/cache/proxy into a package.
- It does not install Cinema 4D, Redshift, Octane, fonts, OCIO, or plugins.
- It does not solve license issues.
- It does not make different drive mappings magically equivalent.

Keep the render machines as similar as possible. That is the boring part, but it
makes the render farm feel calm.
