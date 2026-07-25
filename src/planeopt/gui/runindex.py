"""Reading `runs/` into summaries — EXECUTION_PLAN M5: "reads run.json only".

Deliberately Qt-free so it is testable headless, and deliberately tolerant: a
run directory may be half-written (a solve still going, or one the OOM killer
took), and the browser must list those rather than refuse to start.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Run directories are stamped <YYYYMMDD>T<HHMMSS>-<slug> by assemble.write_run_dir.
# Matching the stamp keeps hand-made directories under runs/ (preview renders,
# scratch) out of the list, while still showing a stamped run whose run.json is
# not written yet — that one is genuinely in progress and worth seeing.
_STAMP = re.compile(r"^\d{8}T\d{6}")

# Constraint keys are declared by the mission/aircraft, so the summary reads the
# *_active / *_ok flags generically rather than hard-coding a constraint list —
# a new constraint shows up in the UI without touching this file.
_ACTIVITY_SUFFIXES = ("_active", "_ok", "_in_range")


@dataclass
class RunSummary:
    """One row in the run list. Every field is optional-safe: an unreadable or
    partial run still produces a row, flagged, instead of an exception."""

    path: Path
    stamp: str
    created: str = ""
    aircraft: str = ""
    mission: str = ""
    objective: str = ""
    status: str = ""
    objective_value: float | None = None
    objective_units: str = ""
    v_ms: float | None = None
    span_m: float | None = None
    auw_kg: float | None = None
    optimized: bool = False
    active_constraints: list[str] = field(default_factory=list)
    violated_constraints: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def label(self) -> str:
        return f"{self.stamp}  {self.aircraft or '?'}"

    @property
    def objective_text(self) -> str:
        if self.objective_value is None:
            return "—"
        return f"{self.objective_value:.1f} {self.objective_units}".strip()

    @property
    def has_report(self) -> bool:
        return (self.path / "report.html").is_file()

    @property
    def has_3d(self) -> bool:
        return (self.path / "interactive_3d.html").is_file()


def _constraint_flags(constraints: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Split boolean constraint flags into 'binding' and 'violated'.

    `*_active` True means the constraint is binding at the optimum (interesting:
    it is what sizes the design). `*_ok` / `*_in_range` False means violated.
    """
    active, violated = [], []
    for key, value in constraints.items():
        if not isinstance(value, bool):
            continue
        name = key
        for suffix in _ACTIVITY_SUFFIXES:
            name = name.removesuffix(suffix)
        if key.endswith("_active"):
            if value:
                active.append(name)
        elif not value:
            violated.append(name)
    return active, violated


def summarize(run_dir: Path) -> RunSummary:
    stamp = run_dir.name.split("-")[0]
    summary = RunSummary(path=run_dir, stamp=stamp)
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        summary.error = "no run.json (run still in progress, or it died)"
        return summary
    try:
        data = json.loads(run_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        summary.error = f"unreadable run.json: {e}"
        return summary

    summary.created = data.get("created", "")
    summary.aircraft = data.get("aircraft", "")
    summary.mission = data.get("mission", "")
    summary.objective = data.get("objective", "")
    summary.status = data.get("status", "")

    performance = data.get("performance") or {}
    best = performance.get("best") or {}
    summary.objective_units = performance.get("objective_units", "")
    summary.objective_value = best.get("objective_value")
    summary.v_ms = best.get("V_ms")
    summary.optimized = "optimization" in performance

    summary.span_m = (data.get("geometry") or {}).get("span_m")
    summary.auw_kg = (data.get("masses") or {}).get("auw_kg")
    summary.active_constraints, summary.violated_constraints = _constraint_flags(
        data.get("constraints") or {}
    )
    return summary


def scan(runs_root: Path) -> list[RunSummary]:
    """All runs under `runs_root`, newest first (the stamp sorts chronologically)."""
    if not runs_root.is_dir():
        return []
    dirs = [
        p
        for p in runs_root.iterdir()
        if p.is_dir() and (_STAMP.match(p.name) or (p / "run.json").is_file())
    ]
    return [summarize(p) for p in sorted(dirs, key=lambda p: p.name, reverse=True)]


def load_full(run_dir: Path) -> dict:
    """The whole run.json, for the detail and compare views."""
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
