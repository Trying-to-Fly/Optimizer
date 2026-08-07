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
        # Formatted from whatever the artifact carried, so the type is checked
        # here rather than assumed: this string is built while the run TREE is
        # being filled in, and a ValueError raised here empties the whole list
        # rather than one row.
        if not isinstance(self.objective_value, (int, float)) or isinstance(
            self.objective_value, bool
        ):
            return "—"
        return f"{self.objective_value:.1f} {self.objective_units}".strip()

    @property
    def has_report(self) -> bool:
        return (self.path / "report.html").is_file()

    @property
    def has_3d(self) -> bool:
        return (self.path / "interactive_3d.html").is_file()


def mapping(value: Any) -> dict:
    """`value` if it is a dict, else an empty one.

    `data.get("masses") or {}` covers a MISSING or null block and nothing else:
    a block that is present but is a list, a string or a number sails through
    and raises on the next `.get`. That is the difference between a row that
    reads "unreadable" and a `scan` that returns nothing at all.

    Public because `views` reads the same blocks out of the same file and had
    the same hole — one guard, so the two cannot drift.
    """
    return value if isinstance(value, dict) else {}


#: Kept for readability inside this module.
_mapping = mapping


def _constraint_flags(constraints: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Split boolean constraint flags into 'binding' and 'violated'.

    `*_active` True means the constraint is binding at the optimum (interesting:
    it is what sizes the design). `*_ok` / `*_in_range` False means violated.
    """
    active, violated = [], []
    for key, value in _mapping(constraints).items():
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
    if not isinstance(data, dict):
        # Valid JSON of the wrong shape — `null`, a list, a bare number. Nothing
        # below can read it, and a run directory this app did not write is not a
        # reason to refuse to list the ones it did.
        summary.error = f"run.json is not a run record (it holds {type(data).__name__})"
        return summary

    # `str(...)` on the identity fields: they are put straight into tree columns
    # and tooltips, which want text, and an artifact carrying a number here
    # should read oddly rather than crash Qt.
    summary.created = str(data.get("created", ""))
    summary.aircraft = str(data.get("aircraft", ""))
    summary.mission = str(data.get("mission", ""))
    summary.objective = str(data.get("objective", ""))
    summary.status = str(data.get("status", ""))

    performance = _mapping(data.get("performance"))
    best = _mapping(performance.get("best"))
    summary.objective_units = str(performance.get("objective_units", ""))
    summary.objective_value = best.get("objective_value")
    summary.v_ms = best.get("V_ms")
    summary.optimized = "optimization" in performance

    summary.span_m = _mapping(data.get("geometry")).get("span_m")
    summary.auw_kg = _mapping(data.get("masses")).get("auw_kg")
    summary.active_constraints, summary.violated_constraints = _constraint_flags(
        data.get("constraints")
    )
    return summary


def scan(runs_root: Path) -> list[RunSummary]:
    """All runs under `runs_root`, newest first (the stamp sorts chronologically).

    One unreadable directory costs ONE flagged row. `summarize` is written to
    return a row rather than raise, and this is the belt to that pair of braces:
    this list is what the whole browser is built on, and a directory nothing
    here wrote — the selector takes any folder holding a `run.json` — must not
    be able to empty it.
    """
    if not runs_root.is_dir():
        return []
    dirs = [
        p
        for p in runs_root.iterdir()
        if p.is_dir() and (_STAMP.match(p.name) or (p / "run.json").is_file())
    ]
    summaries = []
    for path in sorted(dirs, key=lambda p: p.name, reverse=True):
        try:
            summaries.append(summarize(path))
        except Exception as e:  # noqa: BLE001 — one bad run, not the run list
            summaries.append(
                RunSummary(
                    path=path,
                    stamp=path.name.split("-")[0],
                    error=f"could not be read: {type(e).__name__}: {e}",
                )
            )
    return summaries


def load_full(run_dir: Path) -> dict:
    """The whole run.json, for the detail and compare views.

    Always a dict: both callers immediately `.get` on it, and valid JSON that is
    a list or a bare number would otherwise raise an AttributeError inside a Qt
    selection slot rather than the OSError/ValueError they guard against.
    """
    return mapping(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
