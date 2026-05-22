# DreamRender Scripts

Use the no-console launcher in the project root for normal testing and daily work:

## Normal Use

### `..\START_DREAMRENDER.vbs`

Use this. Double-click it to open the native DreamRender app without a console.

### `START_DreamRender_App.vbs`

Legacy shortcut. It forwards to `..\START_DREAMRENDER.vbs`.

From the app you can:

- run Quick Setup
- choose the shared queue folder
- install the Cinema 4D plugin
- start/stop DreamRender on this machine
- open the dashboard
- run diagnostics

If you are unsure, use this.

### `START_DreamRender_App.bat`

Fallback launcher for the classic Tkinter control panel. Use it only for
troubleshooting while App v2 is being finished. It may show a console window.

### `INSTALL_Cinema4D_Plugin_2026.bat`

You usually do not need this anymore, because the DreamRender App has an
`Install C4D Plugin` button.

Use this batch file only if you want to install the plugin without opening the
app. It may show a console window.

It installs the Cinema 4D 2026 submitter plugin. Restart Cinema 4D after running
it, then open:

```text
Extensions > DreamRender Submit Render
```

## Advanced / Troubleshooting

Advanced scripts are tucked away in `advanced\` so most users only see the two
scripts they need.

### `ADVANCED_Worker_Only_C4D2026.bat`

Use only when you deliberately want a visible troubleshooting worker console.
Normal artists should not need this.

### `ADVANCED_Monitor_Only.bat`

Use only when you want to run just the dashboard server without the DreamRender
App.

Normal artists should not need this.

### `ADVANCED_Command_Line.bat`

Use only for manual commands and troubleshooting.

Example:

```bat
advanced\ADVANCED_Command_Line.bat status --share "\\RenderServer\DreamRender"
```

### `_INTERNAL_find_python.bat`

Internal helper in `advanced\`, used by the other scripts. Do not run this
directly.
