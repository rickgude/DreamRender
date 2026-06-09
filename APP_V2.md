# DreamRender App

The current DreamRender app is the normal artist-facing control surface. The
old Tkinter control panel is kept only as an advanced troubleshooting fallback.

The renderfarm engine stays Python:

- queue handling
- worker process
- Cinema 4D command-line rendering
- dashboard server
- repair tools
- GPU status
- worker confidence and failure recovery
- submit history metadata

The UI is a modern local web app served by `dreamrender app-v2` and displayed
inside the Tauri desktop shell.

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

The repository includes a Tauri shell in `src-tauri`.

For development:

```bat
npm install
npm run tauri:dev
```

This requires Node.js and Rust/Cargo. If `cargo --version` does not work, install
Rust from rustup before running the Tauri commands.

The Tauri shell starts:

```text
dreamrender-backend.exe
```

In packaged releases, that backend is a bundled PyInstaller sidecar, so users do
not need Python installed. In development, the app can still be run from source
with `python -m dreamrender app-v2 --no-browser`.

## Packaging Notes

Packaged Windows releases bundle the DreamRender Python backend as a standalone
sidecar. The artist-facing install path is intentionally simple: download the
packaged `DreamRender_..._x64-setup.exe`, install it, start DreamRender from the
Start Menu, then use the app to install the Cinema 4D plugin.

User-specific app settings are stored outside the source tree:

```text
%APPDATA%\DreamRender\DreamRenderApp.json
```

Older installs that used `%USERPROFILE%\DreamRenderApp.json` are still read as a
fallback. Fresh installs default to `Documents\DreamRenderShare` for local
testing and should be changed to a shared/NAS folder for multiple machines.
