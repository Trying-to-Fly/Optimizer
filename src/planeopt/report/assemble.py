"""Run artifacts — EXECUTION_PLAN.md section 3 rule 2.

Every run writes runs/<stamp>-<name>/ with run.json (machine-readable, the future
GUI's data source), report.html (self-contained, shareable), and inputs/ (snapshot
of the config modules used, for reproducibility).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import shutil
from pathlib import Path

from ..types import RunResult


def write_run_dir(result: RunResult, runs_root: Path, input_files: list[Path]) -> Path:
    stamp = result.created.replace(":", "").replace("-", "")  # 20260723T140501
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{result.mission}-{result.aircraft}").strip("-")
    run_dir = runs_root / f"{stamp}-{slug}"
    (run_dir / "figures").mkdir(parents=True, exist_ok=False)

    # encoding is explicit everywhere artifacts are written: Python falls back to
    # the locale encoding otherwise, and the reports carry non-Latin-1 characters
    # (eta, Delta, arrows) that cp1252 cannot represent — on Windows that is a
    # crash at the very end of a multi-hour run.
    (run_dir / "run.json").write_text(
        json.dumps(dataclasses.asdict(result), indent=2, default=str), encoding="utf-8"
    )

    inputs_dir = run_dir / "inputs"
    inputs_dir.mkdir()
    for f in input_files:
        shutil.copy2(f, inputs_dir / f.name)

    return run_dir


def load(run_dir: Path) -> RunResult:
    data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    data["constraints"] = data.get("constraints") or {}
    return RunResult(**data)


def champion_config(result: RunResult) -> dict:
    """The DISCRETE configuration the champion was actually solved with.

    A champion is only half described by its design vector: the studies also
    chose a tail type, a fuselage topology, a mount, a prop and whether to keep
    the winglet, and those live as plain attributes on the aircraft rather than
    in `dv`. Rebuilding from `dv` alone silently gets the aircraft's DEFAULT
    choices instead — which is how a regenerated build document grew a winglet
    the champion had rejected.

    Prefers the configuration recorded on the champion; falls back to recovering
    it from the study blocks so runs made before it was recorded still rebuild
    correctly. An evaluation run has neither, and correctly yields {}.
    """
    opt = (result.performance or {}).get("optimization") or {}
    champ = opt.get("champion") or {}
    if champ.get("discrete"):
        return dict(champ["discrete"])
    cfg = {
        attr: study["adopted"]
        for attr, study in (opt.get("discrete_studies") or {}).items()
        if "adopted" in study
    }
    winglet = opt.get("winglet_study") or {}
    if "winglet_rejected" in winglet:
        cfg["winglet"] = not winglet["winglet_rejected"]
    return cfg


@contextlib.contextmanager
def as_champion(result: RunResult, aircraft):
    """Apply the champion's discrete configuration to `aircraft`, then restore it.

    Mirrors what `solve.optimize` does around its own champion re-evaluation, so
    anything rebuilding a champion out of band gets the same aircraft the solver
    analysed rather than the aircraft file's defaults.
    """
    cfg = champion_config(result)
    applied = {a: getattr(aircraft, a) for a in cfg if hasattr(aircraft, a)}
    try:
        for attr, value in cfg.items():
            if hasattr(aircraft, attr):
                setattr(aircraft, attr, value)
        yield cfg
    finally:
        for attr, value in applied.items():
            setattr(aircraft, attr, value)
