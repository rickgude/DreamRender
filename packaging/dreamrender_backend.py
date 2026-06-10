import sys
import os
import traceback
from pathlib import Path

from dreamrender.app_v2 import run_app_v2, set_windows_error_mode
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


def log_fatal_exception() -> None:
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write("\nDreamRender backend crashed:\n")
            traceback.print_exc(file=handle)
    except Exception:
        pass


if __name__ == "__main__":
    set_windows_error_mode()
    try:
        if len(sys.argv) > 1:
            ensure_cli_streams()
            raise SystemExit(cli_main())
        run_app_v2(open_browser=False)
    except SystemExit:
        raise
    except BaseException:
        log_fatal_exception()
        raise SystemExit(1)
