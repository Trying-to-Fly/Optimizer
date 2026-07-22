"""Run orchestration — MODEL_DETAILS.md section 6; the single entry point.

`run()` is what the CLI (and the future GUI) calls. M0 scope: fixed-design echo —
build geometry, sum fixed equipment, emit a complete run artifact with no
aero/propulsion evaluation and no optimizer. M1 replaces the middle with the real
fixed-design evaluation pipeline (the Phase 1 gate); M2 adds the NLP.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from . import geometry, massmodel
from .mission import OBJECTIVES
from .report import assemble
from .types import AircraftDefinition, MissionSpec, RunResult

M0_STATUS = "M0 scaffold: fixed-design echo — no aero/propulsion models, no optimizer"


def run(
    aircraft: AircraftDefinition,
    mission: MissionSpec,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
) -> tuple[RunResult, Path]:
    objective = OBJECTIVES[mission.objective]  # KeyError early if mission is bad

    airplane = aircraft.geometry(None)
    fixed = aircraft.fixed_equipment()
    battery = aircraft.powertrain().battery

    result = RunResult(
        aircraft=aircraft.name,
        mission=mission.name,
        objective=objective.name,
        status=M0_STATUS,
        created=datetime.datetime.now().isoformat(timespec="seconds"),
        geometry=geometry.summarize(airplane),
        masses={
            "fixed_equipment": {c.name: c.mass_kg for c in fixed},
            "fixed_totals": massmodel.totals(fixed),
        },
        performance={"usable_energy_wh": battery.usable_energy_wh},
        constraints={"v_min_ms": mission.v_min_ms, "v_stall_max_ms": mission.v_stall_max_ms},
        diagnostics={"objective_units": objective.units, "wind_mode": objective.wind_mode},
        notes=[
            "Structure mass, aero, propulsion, and trim are not evaluated at M0.",
            "fixed_totals CG covers fixed equipment only — not an aircraft CG.",
        ],
    )

    run_dir = assemble.write_run_dir(result, runs_root, input_files or [])
    return result, run_dir
