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


def launch(runs_dir: Path, aircraft_dir: Path, missions_dir: Path) -> int:
    """Start the desktop app. Returns the Qt exit code."""
    try:
        from .window import run_app
    except ImportError as e:  # PySide6 absent
        raise RuntimeError(f"{INSTALL_HINT}\n\n({e})") from e
    return run_app(runs_dir=runs_dir, aircraft_dir=aircraft_dir, missions_dir=missions_dir)
