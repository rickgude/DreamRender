# DreamRender App v2

App v2 is the migration path away from the old Tkinter control panel.

The renderfarm engine stays Python:

- queue handling
- worker process
- Cinema 4D command-line rendering
- dashboard server
- repair tools
- GPU status

The UI is now a modern local web app served by `dreamrender app-v2`. This gives
DreamRender a much more stable layout and a cleaner path to a Tauri desktop
shell later.

## Run

Normal users should double-click:

```text
scripts\START_DreamRender_App.vbs
```

That launcher starts App v2 without a console window.

For development:

```bat
scripts\advanced\ADVANCED_Command_Line.bat app-v2
```

## Next Tauri Step

The next packaging step is to wrap the App v2 URL in Tauri:

1. Start `dreamrender app-v2 --no-browser` as the backend sidecar.
2. Open `http://127.0.0.1:8777/` inside the Tauri webview.
3. Package Python and the DreamRender source with the app.
4. Keep the command-line tools available only for advanced troubleshooting.

This keeps the proven backend intact while replacing the artist-facing UI with a
proper desktop shell.
