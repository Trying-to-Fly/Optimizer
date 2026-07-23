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
    dv: dict | None = None,
) -> tuple[RunResult, Path]:
    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()
    bodies = aircraft.parasite_bodies(dv)
    pitch_control = getattr(aircraft, "pitch_control_name", "ruddervator")

    airplane = aircraft.geometry(dv)
    components, printed_breakdown = massmodel.build(aircraft, airplane, dv)
    mass_totals = massmodel.totals(components)
    auw, x_cg = mass_totals["auw_kg"], mass_totals["x_cg_m"]
    weight_n = auw * G

    # --- speed sweep: trim + power at each V ---
    sweep = []
    for V in np.arange(*v_sweep):
        try:
            t = aero.trim(airplane, float(V), weight_n, x_cg, bodies, control_name=pitch_control)
            p = propulsion.solve(float(V), t["drag_n"], pt)
        except (RuntimeError, ValueError) as e:
            sweep.append({"V_ms": float(V), "infeasible": str(e)})
            continue
        point = {**t, **p}
        if objective.evaluator is not None:
            point["objective_value"] = objective.evaluator(float(V), p["P_elec_w"], mission, pt)
        sweep.append(point)

    # --- stall: critical-section method (also feeds the gust-margin filter) ---
    clmax_ab = aero.clmax_log_fit(airplane.wings[0].xsecs[0].airfoil)
    stall = aero.critical_stall_speed(airplane, weight_n, clmax_ab)
    re_s = 1.225 * stall["v_stall_ms"] * airplane.c_ref / 1.81e-5
    stall["cl_max_3d"] = 0.9 * (clmax_ab[0] + clmax_ab[1] * np.log(re_s))

    feasible = [s for s in sweep if "infeasible" not in s]
    # same feasibility rules as the NLP: wind floor, gust margin, and the prop
    # advance-ratio cap (beyond 95% of the fitted table the CT->0 tail of the
    # polynomial fit is not trustworthy)
    j_cap = 0.95 * propulsion.PropTable(pt.prop.proxy_table).j_max
    # throw-limit policy may be a plain number or a callable of the design vector
    # (hinge fraction free -> the degree cap depends on the control chord)
    defl_cap = getattr(aircraft, "trim_deflection_limit_deg", None)
    if callable(defl_cap):
        defl_cap = float(defl_cap(dv))
    legal = [
        s
        for s in feasible
        if s["V_ms"] >= mission.v_min_ms - 1e-9
        and s["CL"] <= 0.7 * stall["cl_max_3d"] + 1e-6
        and s["J"] <= j_cap + 1e-6
        and (defl_cap is None or abs(s["deflection_deg"]) <= defl_cap + 1e-3)
    ]
    candidates = legal if legal else feasible
    sign = 1 if objective.direction == "maximize" else -1
    best = max(candidates, key=lambda s: sign * s.get("objective_value", -np.inf))
    # evaluate dCm/dCL at the trim alpha — LiftingLine's derivative is
    # alpha-dependent, so a fixed reference alpha disagrees with the NLP
    sm = aero.static_margin(
        airplane, best["V_ms"], x_cg, airplane.c_ref, alpha0=best["alpha_deg"], bodies=bodies
    )

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
            or (stall["v_stall_ms"] <= mission.v_stall_max_ms * 1.01),  # 1% tol: active != violated
            "static_margin": float(sm["static_margin"]),
            "sm_in_range": bool(
                mission.static_margin_range[0]
                <= sm["static_margin"]
                <= mission.static_margin_range[1]
            ),
            "trim_deflection_deg": best["deflection_deg"],
        },
        diagnostics={
            "wind_mode": objective.wind_mode,
            "stall_detail": stall,
            "neutral_point_m": sm["x_np_m"],
            "sm_local_slopes": sm.get("sm_local_slopes"),
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
    figures.stall_spanwise(stall, run_dir / "figures")
    planes = {"current": airplane}
    if dv is not None:
        planes = {"baseline (defaults)": aircraft.geometry(None), "optimized": airplane}
    figures.planform_compare(planes, run_dir / "figures")
    # viz twin: attach the fuselage loft(s) for the 3D artifacts only — the aero
    # airplane stays wings-only (LL would double-count fuselage drag, section 7)
    viz_plane = airplane
    if hasattr(aircraft, "fuselage_lofts"):
        import aerosandbox as asb

        lofts = aircraft.fuselage_lofts(dv)
        if lofts:
            viz_plane = asb.Airplane(
                name=airplane.name, wings=airplane.wings, fuselages=lofts,
                s_ref=airplane.s_ref, c_ref=airplane.c_ref, b_ref=airplane.b_ref,
            )
    figures.three_view(viz_plane, run_dir / "figures")
    figures.interactive_3d(viz_plane, run_dir)
    (run_dir / "report.html").write_text(report_html.render(result, run_dir))
    return result, run_dir


# --------------------------------------------------------------------------- M2

M2_STATUS = "M3: full-vehicle optimization (wing + tail + balance + spars + trim) + numeric re-evaluation"


def _solve_nlp(
    aircraft,
    mission,
    inits: dict | None = None,
    fixed: dict | None = None,
    extra_mass_kg: float = 0.0,
    printed_scale: float = 1.0,
    eta_scale: float = 1.0,
) -> dict:
    """One NLP solve. Returns the champion design + state, all numeric.

    M2 scope note: lift=weight and thrust=drag are enforced; pitch-moment trim and
    static margin join at M3 (tail is fixed here). Objective from the mission
    registry evaluator, built symbolically.
    """
    import aerosandbox as asb

    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()

    opti = asb.Opti()
    dv = aircraft.design_variables(opti, inits)
    bodies = aircraft.parasite_bodies(dv)  # may be symbolic (fuselage loft)
    V = opti.variable(init_guess=(inits or {}).get("V", 11.0), lower_bound=6.0, upper_bound=25.0)
    alpha = opti.variable(init_guess=4.0, lower_bound=-2.0, upper_bound=10.0)
    defl = opti.variable(init_guess=0.0, lower_bound=-15.0, upper_bound=15.0)
    n = opti.variable(init_guess=65.0, lower_bound=20.0, upper_bound=200.0)

    for k, val in (fixed or {}).items():
        opti.subject_to(dv[k] == val)

    airplane = aircraft.geometry(dv)
    components, _ = massmodel.build(aircraft, airplane, dv, printed_scale=printed_scale)
    totals = massmodel.totals(components)
    auw = totals["auw_kg"] + extra_mass_kg
    x_cg = totals["x_cg_m"]
    weight_n = auw * G

    # cruise point: trimmed (explicit deflection of the aircraft-declared pitch
    # surface — "ruddervator", "elevator", ... — Cm about produced CG)
    pitch_control = getattr(aircraft, "pitch_control_name", "ruddervator")
    plane_defl = airplane.with_control_deflections({pitch_control: defl})
    aero_run = asb.LiftingLine(
        airplane=plane_defl,
        op_point=asb.OperatingPoint(velocity=V, alpha=alpha),
        xyz_ref=[x_cg, 0, 0],
    ).run()
    q = 0.5 * 1.225 * V**2
    s_ref = airplane.s_ref
    drag = aero_run["D"] + q * s_ref * aero.body_cd0(bodies, V, s_ref)

    pr = propulsion.chain(V, n, pt)
    opti.subject_to(aero_run["L"] == weight_n)
    opti.subject_to(aero_run["Cm"] == 0)  # pitch trim
    opti.subject_to(pr["thrust_n"] == drag)
    opti.subject_to(pr["J"] < 0.95 * pr["j_max"])  # stay on the fitted table

    # static margin about the produced CG: regression slope over a +/-2 deg
    # window (LL's local Cm derivative is noisy — FINDINGS.md), plus the Munk
    # fuselage destabilizing term converted to CL-space via the lift slope
    offs = (-2.0, 0.0, 2.0)
    sm_runs = [
        asb.LiftingLine(
            airplane=airplane,
            op_point=asb.OperatingPoint(velocity=V, alpha=alpha + o),
            xyz_ref=[x_cg, 0, 0],
        ).run()
        for o in offs
    ]
    cls = [r["CL"] for r in sm_runs]
    cms = [r["Cm"] for r in sm_runs]
    cl_mean = sum(cls) / 3
    cm_mean = sum(cms) / 3
    var_cl = sum((c - cl_mean) ** 2 for c in cls)
    cov = sum((cls[i] - cl_mean) * (cms[i] - cm_mean) for i in range(3))
    sm_surf = -cov / var_cl
    a_deg = sum((offs[i] - 0.0) * (cls[i] - cl_mean) for i in range(3)) / sum(o**2 for o in offs)
    cl_alpha_rad = a_deg * 180 / np.pi
    sm = sm_surf - aero.fuselage_cm_alpha(bodies, s_ref, airplane.c_ref) / cl_alpha_rad
    opti.subject_to(sm >= mission.static_margin_range[0])
    opti.subject_to(sm <= mission.static_margin_range[1])

    # stall: critical-section method (Schrenk loading + local clmax(Re) fit),
    # evaluated at the mission stall-speed limit — MODEL_DETAILS 3.4
    clmax_ab = aero.clmax_log_fit(airplane.wings[0].xsecs[0].airfoil)
    if mission.v_stall_max_ms is not None:
        v_s = mission.v_stall_max_ms
        cl_stall = 2 * weight_n / (1.225 * v_s**2 * s_ref)
        stations = aero.wing_stations(airplane.wings[0])
        ratios = aero.critical_section_ratios(
            stations, s_ref, airplane.b_ref, cl_stall, v_s, clmax_ab
        )
        opti.subject_to(aero.smooth_max(ratios) <= 1.0)
    # gust margin (MODEL_DETAILS section 4), wing-level clmax from the same fit.
    # c_ref (area / material span), NOT s_ref/b_ref: b_ref is projected span, and
    # via that route extra dihedral would inflate the modeled chord Re and game
    # the gust constraint.
    c_mean = airplane.c_ref
    re_cruise = 1.225 * V * c_mean / 1.81e-5
    clmax_wing = 0.9 * (clmax_ab[0] + clmax_ab[1] * np.log(re_cruise))
    opti.subject_to(aero_run["CL"] <= 0.7 * clmax_wing)
    if objective.wind_mode == "constraint":
        opti.subject_to(V >= mission.v_min_ms)
    if mission.ballast_max_kg is not None and "ballast_kg" in dv:
        opti.subject_to(dv["ballast_kg"] <= mission.ballast_max_kg)
    aircraft.geometry_constraints(opti, dv, V, deflection_deg=defl)
    aircraft.structure_constraints(opti, dv, weight_n)

    p_bus_eff = pr["p_bus_w"] / eta_scale  # eta_scale: chain-efficiency re-solves
    obj_expr = objective.evaluator(V, p_bus_eff, mission, pt)
    opti.minimize(-obj_expr if objective.direction == "maximize" else obj_expr)

    sol = opti.solve(verbose=False, max_iter=1000)
    return {
        "dv": {k: float(sol(v)) for k, v in dv.items()},
        "V_ms": float(sol(V)),
        "alpha_deg": float(sol(alpha)),
        "deflection_deg": float(sol(defl)),
        "rpm": float(sol(n)) * 60,
        "objective_value": float(sol(obj_expr)),
        "auw_kg": float(sol(auw)),
        "x_cg_m": float(sol(x_cg)),
        "static_margin": float(sol(sm)),
        "P_elec_w": float(sol(p_bus_eff)),
        "drag_n": float(sol(drag)),
        "J": float(sol(pr["J"])),
        "clmax_ab_used": clmax_ab,
    }


def optimize(
    aircraft,
    mission,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    multistart: int = 3,
    flatness: bool = True,
) -> tuple[RunResult, Path]:
    """M2 entry point: multi-start NLP -> champion -> shadow price -> flatness
    sweep -> numeric re-evaluation of the champion through the M1 pipeline."""
    rng = np.random.default_rng(0)
    starts, results = [], []
    base = _solve_nlp(aircraft, mission)
    results.append(base)
    starts.append("nominal")
    for i in range(multistart - 1):
        inits = {
            "span": float(1.8 * rng.uniform(0.88, 1.12)),
            "c_root": float(0.22 * rng.uniform(0.88, 1.12)),
            "taper": float(np.clip(0.68 * rng.uniform(0.85, 1.15), 0.45, 0.95)),
            "V": float(11 * rng.uniform(0.85, 1.2)),
        }
        if getattr(aircraft, "winglet", False):
            inits["wl_len"] = float(0.12 * rng.uniform(0.5, 1.8))
            inits["wl_cant"] = float(rng.uniform(60.0, 85.0))
        try:
            results.append(_solve_nlp(aircraft, mission, inits=inits))
            starts.append(f"perturbed_{i}")
        except RuntimeError as e:
            results.append({"failed": str(e)[:120]})
            starts.append(f"perturbed_{i} (failed)")

    ok = [r for r in results if "failed" not in r]
    sign = 1 if OBJECTIVES[mission.objective].direction == "maximize" else -1
    champion = max(ok, key=lambda r: sign * r["objective_value"])
    spread = max(abs(r["objective_value"] - champion["objective_value"]) for r in ok)

    # shadow price: minutes (objective units) per gram of structure
    bumped = _solve_nlp(aircraft, mission, extra_mass_kg=0.020)
    shadow_per_g = (bumped["objective_value"] - champion["objective_value"]) / 20.0

    # flatness: re-optimize everything else at fixed spans (up to the cap)
    flat = []
    span_cap = getattr(aircraft, "span_cap_m", 3.0)
    if flatness:
        for s_fix in np.linspace(1.5, span_cap, 6):
            try:
                r = _solve_nlp(aircraft, mission, fixed={"span": float(s_fix)})
                flat.append({"span": float(s_fix), "objective_value": r["objective_value"]})
            except RuntimeError:
                flat.append({"span": float(s_fix), "objective_value": None})

    # re-solve battery (MODEL_DETAILS 6.4 item 2): each is a full re-optimization
    battery = {}
    for label, kw in [
        ("printed_mass_x1.10", {"printed_scale": 1.10}),
        ("printed_mass_x0.90", {"printed_scale": 0.90}),
        ("chain_eta_x0.90", {"eta_scale": 0.90}),
        ("chain_eta_x1.10", {"eta_scale": 1.10}),
    ]:
        try:
            r = _solve_nlp(aircraft, mission, **kw)
            battery[label] = {
                "objective_value": r["objective_value"],
                "delta": r["objective_value"] - champion["objective_value"],
                "span": r["dv"]["span"],
                "static_margin": r["static_margin"],
                "ballast_kg": r["dv"]["ballast_kg"],
            }
        except RuntimeError as e:
            battery[label] = {"failed": str(e)[:120]}

    # discrete studies (MODEL_DETAILS 6.3): the aircraft declares
    # `discrete_options = {attr: [candidate values]}` — e.g. fuselage topology
    # (section 7.4) or tail type (section 8) — every candidate a suggestion the
    # study prices, never an assumption. Plain enumeration, one full
    # re-optimization per alternative, in declared order (greedy: each study
    # runs with the previous studies' adopted values). A winner becomes the
    # champion and stays active through the winglet study and numeric
    # re-evaluation (originals restored in the re-eval finally).
    discrete_studies = {}
    discrete_originals = {}
    for attr, candidates in (getattr(aircraft, "discrete_options", None) or {}).items():
        baseline = getattr(aircraft, attr)
        discrete_originals[attr] = baseline
        study = {"baseline": baseline, "alternatives": {}, "adopted": baseline}
        for cand in candidates:
            if cand == baseline:
                continue
            setattr(aircraft, attr, cand)
            try:
                r_c = _solve_nlp(aircraft, mission)
                delta = r_c["objective_value"] - champion["objective_value"]
                study["alternatives"][cand] = {
                    **{k: r_c[k] for k in ("objective_value", "V_ms", "auw_kg")},
                    "delta_objective": delta,
                }
                if sign * delta > 0:
                    champion = r_c
                    study["adopted"] = cand
                else:
                    setattr(aircraft, attr, study["adopted"])
            except RuntimeError as e:
                study["alternatives"][cand] = {"failed": str(e)[:120]}
                setattr(aircraft, attr, study["adopted"])
        discrete_studies[attr] = study

    # winglet study (MODEL_DETAILS 3.6): paired on/off re-optimization at the
    # same span cap, an inviscid VLM second opinion on the induced-drag delta,
    # and the continuous-cant cross-check (outermost panel freed to ~88 deg, no
    # explicit winglet — does one emerge from the planform architecture alone?)
    winglet_study = None
    winglet_rejected = False
    if getattr(aircraft, "winglet", False):
        winglet_study = {}
        r_on = champion  # the winglet-bearing solve, kept for the VLM check
        aircraft.winglet = False
        try:
            r_off = _solve_nlp(aircraft, mission)
            winglet_study["off"] = {
                **{k: r_off[k] for k in ("objective_value", "V_ms", "auw_kg")},
                "span": r_off["dv"]["span"],
            }
            winglet_study["delta_objective"] = (
                champion["objective_value"] - r_off["objective_value"]
            )
            # rejection rule (EXECUTION_PLAN M4.5 gate): winglet=True only means
            # "consider one" — wl_len's lower bound forces it into the on-solve,
            # so if the off-solve wins, IT is the champion and the numeric
            # re-evaluation below runs winglet-free
            if sign * winglet_study["delta_objective"] < 0:
                winglet_rejected = True
                champion = r_off
            winglet_study["winglet_rejected"] = winglet_rejected
        except RuntimeError as e:
            winglet_study["off"] = {"failed": str(e)[:120]}
        finally:
            aircraft.winglet = True

        champ_plane_on = aircraft.geometry(r_on["dv"])
        aircraft.winglet = False
        try:
            champ_plane_off = aircraft.geometry(r_on["dv"])
        finally:
            aircraft.winglet = True
        try:
            winglet_study["vlm_check"] = aero.vlm_induced_check(
                {"winglet_on": champ_plane_on, "winglet_off": champ_plane_off},
                r_on["V_ms"],
            )
        except Exception as e:  # numeric cross-check must never kill the run
            winglet_study["vlm_check"] = {"failed": str(e)[:120]}

        prev_cant = getattr(aircraft, "tip_dihedral_max_deg", 20.0)
        aircraft.winglet, aircraft.tip_dihedral_max_deg = False, 88.0
        try:
            r_cant = _solve_nlp(aircraft, mission)
            winglet_study["continuous_cant"] = {
                "objective_value": r_cant["objective_value"],
                "tip_dihedral_deg": r_cant["dv"].get("dihedral_tip"),
                "d_exp": r_cant["dv"].get("d_exp"),
                "span": r_cant["dv"]["span"],
                "caveat": "Schrenk stall stations include the canted region — "
                "indicative only; the spar-fit constraint also binds high cant",
            }
        except RuntimeError as e:
            winglet_study["continuous_cant"] = {"failed": str(e)[:120]}
        finally:
            aircraft.winglet, aircraft.tip_dihedral_max_deg = True, prev_cant

    # numeric re-evaluation of the champion through the full M1 pipeline
    # (winglet-free when the study rejected it — champion is the off-solve then)
    if winglet_rejected:
        aircraft.winglet = False
    try:
        result, run_dir = run(
            aircraft, mission, runs_root, input_files, dv=champion["dv"]
        )
        # tripped-polar dual evaluation at the champion point (MODEL_DETAILS 3.2)
        best = result.performance["best"]
        champ_plane = aircraft.geometry(champion["dv"])
    finally:
        if winglet_rejected:
            aircraft.winglet = True
        for attr, val in discrete_originals.items():
            setattr(aircraft, attr, val)
    result.status = M2_STATUS
    trip = aero.tripped_cd_delta(champ_plane, best["V_ms"], best["CL"])
    q = 0.5 * 1.225 * best["V_ms"] ** 2
    drag_tripped = best["drag_n"] + q * champ_plane.s_ref * trip["dcd_total"]
    try:
        pr_trip = propulsion.solve(best["V_ms"], drag_tripped, aircraft.powertrain())
        obj_trip = OBJECTIVES[mission.objective].evaluator(
            best["V_ms"], pr_trip["P_elec_w"], mission, aircraft.powertrain()
        )
    except ValueError:
        obj_trip = None
    tripped = {
        "dcd_total": trip["dcd_total"],
        "objective_tripped": obj_trip,
        "delta": (obj_trip - best.get("objective_value")) if obj_trip else None,
    }

    result.performance["optimization"] = {
        "champion": champion,
        "resolve_battery": battery,
        "discrete_studies": discrete_studies or None,
        "winglet_study": winglet_study,
        "tripped_polars": tripped,
        "multistart": [
            {"start": s, **({k: v for k, v in r.items() if k != "clmax_3d_used"})}
            for s, r in zip(starts, results)
        ],
        "multistart_objective_spread": spread,
        "shadow_price_obj_per_gram": shadow_per_g,
        "flatness_span": flat,
        "nlp_vs_reeval_gap": champion["objective_value"]
        - result.performance["best"].get("objective_value", float("nan")),
    }
    result.notes.append(
        "M3 NLP: trimmed (explicit deflection), SM window, gust margin, spar "
        "stress/deflection sizing, ballast cap, battery-position balance."
    )
    figures.flatness_plot(flat, champion, run_dir / "figures")
    (run_dir / "run.json").write_text(
        __import__("json").dumps(__import__("dataclasses").asdict(result), indent=2, default=str)
    )
    (run_dir / "report.html").write_text(report_html.render(result, run_dir))
    return result, run_dir


# --------------------------------------------------------------------------- M4

def pareto(aircraft, mission, values: list[float], runs_root: Path = Path("runs")) -> dict:
    """Epsilon-constraint sweep (MODEL_DETAILS 5.3): re-optimize with a swept floor
    on cruise speed — the natural endurance-vs-penetration trade for this class.
    Warm-starts each solve from the previous champion."""
    points, inits = [], None
    for v_floor in values:
        m2 = __import__("dataclasses").replace(
            mission, v_wind_ms=0.0, penetration_margin_ms=float(v_floor)
        )
        try:
            r = _solve_nlp(aircraft, m2, inits=inits)
            inits = {**r["dv"], "V": r["V_ms"]}
            points.append({"v_floor": float(v_floor), **{k: r[k] for k in
                           ("objective_value", "V_ms", "P_elec_w", "auw_kg")},
                           "span": r["dv"]["span"]})
        except RuntimeError as e:
            points.append({"v_floor": float(v_floor), "failed": str(e)[:100]})
    return {"axis": "min cruise speed (m/s)", "points": points}


def airfoil_study(aircraft, mission, candidates: list[str]) -> dict:
    """Discrete outer loop (MODEL_DETAILS 6.3): full continuous solve per airfoil,
    champions compared under smooth AND tripped polars (rejection rule 3.2):
    a candidate whose tripped objective ranking flips is laminar-fragile."""
    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()
    results = {}
    original = aircraft.wing_airfoil
    try:
        for name in candidates:
            aircraft.wing_airfoil = name
            try:
                r = _solve_nlp(aircraft, mission)
                plane = aircraft.geometry(r["dv"])
                q = 0.5 * 1.225 * r["V_ms"] ** 2
                s_ref = float(plane.s_ref)
                cl = r["auw_kg"] * G / (q * s_ref)
                trip = aero.tripped_cd_delta(plane, r["V_ms"], cl)
                obj_tripped = None
                try:
                    pr = propulsion.solve(
                        r["V_ms"], r["drag_n"] + q * s_ref * trip["dcd_total"], pt
                    )
                    obj_tripped = objective.evaluator(r["V_ms"], pr["P_elec_w"], mission, pt)
                except ValueError:
                    pass
                results[name] = {
                    "objective_smooth": r["objective_value"],
                    "objective_tripped": obj_tripped,
                    "dv": r["dv"], "V_ms": r["V_ms"], "auw_kg": r["auw_kg"],
                    "tripped_dcd": trip["dcd_total"],
                }
            except RuntimeError as e:
                results[name] = {"failed": str(e)[:120]}
    finally:
        aircraft.wing_airfoil = original
    return results
