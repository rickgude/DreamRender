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
START_DREAMRENDER.vbs
```

That launcher starts the native DreamRender app without a console window.

For development:

```bat
scripts\advanced\ADVANCED_Command_Line.bat app-v2
```

## Tauri Desktop Shell

The repository now includes a Tauri shell in `src-tauri`.

For development:

```bat
npm install
npm run tauri:dev
```

This requires Node.js and Rust/Cargo. If `cargo --version` does not work, install
Rust from rustup before running the Tauri commands.

The Tauri shell starts:

```text
python -m dreamrender app-v2 --no-browser
```

Then it opens the App v2 interface in a native desktop window.

## Packaging Notes

The current shell is ready for local development. For a public installer, the
next step is to bundle Python/DreamRender as a Tauri sidecar so users do not need
to install Python manually.

Until that packaging step is done, users still need regular Python 3.10+ on each
machine.
