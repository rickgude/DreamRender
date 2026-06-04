# DreamRender Scripts

Use the no-console launcher in the project root for normal testing and daily
work:

## Normal Use

### `..\START_DREAMRENDER.vbs`

Use this. Double-click it to open the native DreamRender app without a console.

From the app you can:

- choose the shared queue folder
- install the Cinema 4D plugin
- start/stop DreamRender on this machine
- use the integrated dashboard
- run diagnostics

If you are unsure, use this.

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

Advanced scripts are tucked away in `advanced\` so most users only see the
normal launcher and optional plugin installer.

### `ADVANCED_Worker_Only_C4D2026.bat`

Use only when you deliberately want a visible troubleshooting worker console.
Normal artists should not need this.

### `ADVANCED_Classic_App.bat`

Use only if you need the old Tkinter control panel for troubleshooting. The
normal app is `..\START_DREAMRENDER.vbs`.

### `ADVANCED_Monitor_Only.bat`

Use only when you want to run just the dashboard server without the DreamRender
App.

Normal artists should not need this.

### `ADVANCED_Command_Line.bat`

Use only for manual commands and troubleshooting.

Example:

```bat
advanced\ADVANCED_Command_Line.bat status --share "\\YOUR-SERVER\DreamRenderShare"
```

### `_INTERNAL_find_python.bat`

Internal helper in `advanced\`, used by the other scripts. Do not run this
directly.
