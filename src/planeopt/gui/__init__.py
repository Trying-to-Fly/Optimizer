"""Desktop GUI (M5) — a second thin client over the same library and artifacts.

Qt is imported lazily: `planeopt.gui.runindex`, `.missionfile` and `.jobs` are
Qt-free on purpose so the logic is testable headless and a CLI-only install can
import them.
"""

from __future__ import annotations

from pathlib import Path

INSTALL_HINT = (
    "The GUI needs the optional `gui` extra (PySide6).\n"
    "  source install:  uv sync --extra gui\n"
    "  packaged build:  the GUI is bundled — this message means it was excluded"
)


def launch(project_dir: Path | None = None) -> int:
    """Start the desktop app. Returns the Qt exit code.

    project_dir=None lets the app work out where to look (remembered choice,
    working directory, then the folder the .exe lives in) and ask if it cannot.
    """
    try:
        from .window import run_app
        from .workspace import Workspace
    except ImportError as e:  # PySide6 absent
        raise RuntimeError(f"{INSTALL_HINT}\n\n({e})") from e
    return run_app(Workspace(project_dir) if project_dir else None)
