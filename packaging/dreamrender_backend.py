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



def extract_parent_pid(argv: list[str]) -> tuple[list[str], int | None]:
    cleaned = [argv[0]]
    parent_pid = None
    index = 1
    while index < len(argv):
        if argv[index] == "--app-parent-pid" and index + 1 < len(argv):
            try:
                parent_pid = int(argv[index + 1])
            except ValueError:
                parent_pid = None
            index += 2
            continue
        cleaned.append(argv[index])
        index += 1
    return cleaned, parent_pid


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
        argv, parent_pid = extract_parent_pid(sys.argv)
        sys.argv = argv
        if len(sys.argv) > 1:
            ensure_cli_streams()
            raise SystemExit(cli_main())
        run_app_v2(open_browser=False, parent_pid=parent_pid)
    except SystemExit:
        raise
    except BaseException:
        log_fatal_exception()
        raise SystemExit(1)
