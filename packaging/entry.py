"""Frozen-bundle entry point, shared by both executables.

PyInstaller freezes a script, not a console-script entry point, so this is the
stand-in for the `planeopt` command declared in pyproject.toml.

The bundle ships two executables built from this one script:

  planeopt.exe      console — the CLI, exactly as documented
  planeopt-gui.exe  windowed — double-clickable, opens the desktop app

They differ only in how PyInstaller builds them (console vs windowed) and in
their name, which is what this script keys off. Without the second one, a user
double-clicking the console exe gets a window that prints "Missing command" and
vanishes — indistinguishable from the app failing to start.
"""

import sys
from pathlib import Path

from planeopt.cli import main


def _launched_as_gui() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    return Path(sys.executable).stem.lower().endswith("-gui")


if __name__ == "__main__":
    # Bare double-click of the GUI executable means "open the app". Arguments
    # still work, so planeopt-gui.exe stays a normal CLI when given any.
    if _launched_as_gui() and len(sys.argv) == 1:
        sys.argv.append("gui")
    main()
