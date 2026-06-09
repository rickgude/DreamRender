import sys
import os
from pathlib import Path

from dreamrender.app_v2 import run_app_v2
from dreamrender.cli import main as cli_main


def log_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DreamRender"
    root.mkdir(parents=True, exist_ok=True)
    return root / "dreamrender-backend.log"


def ensure_cli_streams() -> None:
    if sys.stdout is None:
        try:
            sys.stdout = os.fdopen(1, "w", encoding="utf-8", buffering=1, closefd=False)
        except OSError:
            sys.stdout = log_path().open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        try:
            sys.stderr = os.fdopen(2, "w", encoding="utf-8", buffering=1, closefd=False)
        except OSError:
            sys.stderr = sys.stdout


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ensure_cli_streams()
        raise SystemExit(cli_main())
    run_app_v2(open_browser=False)
