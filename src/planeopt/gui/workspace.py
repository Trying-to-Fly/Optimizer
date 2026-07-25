"""Where the GUI looks for aircraft, missions and runs.

The CLI can assume its working directory is the project — you typed the paths.
A double-clicked .exe cannot: its working directory is wherever Explorer left
it, so "aircraft/" resolves to nothing and the app comes up empty. This module
is the resolution order that fixes that, kept Qt-free so it is testable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """A folder holding `aircraft/`, `missions/` and (eventually) `runs/`."""

    root: Path

    @property
    def aircraft_dir(self) -> Path:
        return self.root / "aircraft"

    @property
    def missions_dir(self) -> Path:
        return self.root / "missions"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def is_usable(self) -> bool:
        """Has something to work with — runs/ is created on demand, so it does
        not count; aircraft definitions are what you cannot proceed without."""
        return self.aircraft_dir.is_dir() or self.missions_dir.is_dir()

    def aircraft_packages(self) -> list[Path]:
        if not self.aircraft_dir.is_dir():
            return []
        return sorted(p for p in self.aircraft_dir.iterdir() if (p / "aircraft.py").is_file())

    def missions(self) -> list[Path]:
        if not self.missions_dir.is_dir():
            return []
        return sorted(self.missions_dir.glob("*.py"))


def bundle_dir() -> Path | None:
    """The folder holding the frozen executable, if this is a frozen build.

    Not sys._MEIPASS: the payload directory is an implementation detail, while
    the folder the user actually sees — and where the shipped sample aircraft
    sits — is the one containing the .exe.
    """
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def resolve(explicit: Path | None = None, remembered: Path | None = None) -> Workspace:
    """First usable candidate, in order of how strongly it was intended.

    Explicit beats a remembered choice, which beats the working directory,
    which beats the folder the .exe lives in. When nothing qualifies, hand back
    the best guess anyway — the UI asks the user rather than dying.
    """
    candidates = [explicit, remembered, Path.cwd(), bundle_dir()]
    for candidate in candidates:
        if candidate is not None and Workspace(Path(candidate)).is_usable:
            return Workspace(Path(candidate))
    fallback = explicit or remembered or bundle_dir() or Path.cwd()
    return Workspace(Path(fallback))
