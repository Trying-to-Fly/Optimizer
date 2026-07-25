"""Run artifacts — EXECUTION_PLAN.md section 3 rule 2.

Every run writes runs/<stamp>-<name>/ with run.json (machine-readable, the future
GUI's data source), report.html (self-contained, shareable), and inputs/ (snapshot
of the config modules used, for reproducibility).
"""

from __future__ import annotations

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
