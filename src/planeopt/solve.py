"""Run orchestration — MODEL_DETAILS.md section 6; the single entry point.

M1 scope: fixed-design evaluation (the Phase 1 gate pipeline). geometry ->
mass/CG -> trimmed aero over a speed sweep -> propulsion -> mission objective,
plus stall, static margin, and diagnostic figures. No optimizer yet: the "best"
operating point comes from the sweep, which doubles as the report's power curve.
M2 replaces the sweep with the NLP.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np

from . import aero, geometry, massmodel, propulsion
from .mission import OBJECTIVES
from .report import assemble, figures
from .report import html as report_html
from .types import AircraftDefinition, MissionSpec, RunResult

G = 9.81
M1_STATUS = "M1: fixed-design evaluation (Phase 1 gate pipeline) — no optimizer"


def run(
    aircraft: AircraftDefinition,
    mission: MissionSpec,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    v_sweep: tuple[float, float, float] = (8.0, 17.0, 0.5),
) -> tuple[RunResult, Path]:
    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()
    bodies = aircraft.parasite_bodies()

    airplane = aircraft.geometry(None)
    components, printed_breakdown = massmodel.build(aircraft, airplane)
    mass_totals = massmodel.totals(components)
    auw, x_cg = mass_totals["auw_kg"], mass_totals["x_cg_m"]
    weight_n = auw * G

    # --- speed sweep: trim + power at each V ---
    sweep = []
    for V in np.arange(*v_sweep):
        try:
            t = aero.trim(airplane, float(V), weight_n, x_cg, bodies)
            p = propulsion.solve(float(V), t["drag_n"], pt)
        except (RuntimeError, ValueError) as e:
            sweep.append({"V_ms": float(V), "infeasible": str(e)})
            continue
        point = {**t, **p}
        if objective.evaluator is not None:
            point["objective_value"] = objective.evaluator(float(V), p["P_elec_w"], mission, pt)
        sweep.append(point)

    feasible = [s for s in sweep if "infeasible" not in s]
    legal = [s for s in feasible if s["V_ms"] >= mission.v_min_ms - 1e-9]
    candidates = legal if legal else feasible
    sign = 1 if objective.direction == "maximize" else -1
    best = max(candidates, key=lambda s: sign * s.get("objective_value", -np.inf))

    # --- stall & stability ---
    stall = aero.stall_speed(airplane, weight_n)
    sm = aero.static_margin(airplane, best["V_ms"], x_cg, airplane.c_ref)

    result = RunResult(
        aircraft=aircraft.name,
        mission=mission.name,
        objective=objective.name,
        status=M1_STATUS,
        created=datetime.datetime.now().isoformat(timespec="seconds"),
        geometry=geometry.summarize(airplane),
        masses={
            "components": {c.name: round(float(c.mass_kg), 4) for c in components},
            "printed_breakdown": {
                k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                for k, v in printed_breakdown.items()
            },
            "auw_kg": float(auw),
            "x_cg_m": float(x_cg),
            "wing_loading_g_dm2": float(auw * 1000 / (airplane.s_ref * 100)),
        },
        performance={
            "objective_units": objective.units,
            "best": best,
            "usable_energy_wh": pt.battery.usable_energy_wh,
            "watts_per_kg": float(best["P_elec_w"] / auw),
            "wh_per_km_airspeed": float(
                (best["P_elec_w"] + pt.avionics_power_w) / (3.6 * best["V_ms"])
            ),
            "sweep": sweep,
        },
        constraints={
            "v_min_ms": mission.v_min_ms,
            "v_min_active": bool(abs(best["V_ms"] - mission.v_min_ms) < 0.26),
            "v_stall_max_ms": mission.v_stall_max_ms,
            "v_stall_ms": stall["v_stall_ms"],
            "stall_ok": (mission.v_stall_max_ms is None)
            or (stall["v_stall_ms"] <= mission.v_stall_max_ms),
            "static_margin": sm["static_margin"],
            "sm_in_range": mission.static_margin_range[0]
            <= sm["static_margin"]
            <= mission.static_margin_range[1],
            "trim_deflection_deg": best["deflection_deg"],
        },
        diagnostics={
            "wind_mode": objective.wind_mode,
            "stall_detail": stall,
            "neutral_point_m": sm["x_np_m"],
            "J_vs_peak": {"J_cruise": best["J"], "J_peak_eta": best["J_peak_eta"]},
            "uncalibrated_construction": [
                k for k, v in printed_breakdown.items() if not v["calibrated"]
            ],
        },
        notes=[
            "Stall via wing-level CLmax knockdown; critical-section method arrives at M2/M3.",
            "Smooth polars only; tripped-polar dual evaluation arrives at M2.",
            "Propulsion chain is uncalibrated (no measurement path) — rankings over absolutes.",
        ],
    )

    run_dir = assemble.write_run_dir(result, runs_root, input_files or [])
    figures.power_curves(sweep, mission, objective, run_dir / "figures")
    (run_dir / "report.html").write_text(report_html.render(result, run_dir))
    return result, run_dir
