"""Run orchestration — MODEL_DETAILS.md section 6; the single entry point.

M1 scope: fixed-design evaluation (the Phase 1 gate pipeline). geometry ->
mass/CG -> trimmed aero over a speed sweep -> propulsion -> mission objective,
plus stall, static margin, and diagnostic figures. No optimizer yet: the "best"
operating point comes from the sweep, which doubles as the report's power curve.
M2 replaces the sweep with the NLP.
"""

from __future__ import annotations

import datetime
import logging
import time
from pathlib import Path

import numpy as np

from . import aero, geometry, massmodel, memory, propulsion
from .mission import OBJECTIVES
from .report import assemble, figures, geometry_export, manufacturing
from .report import html as report_html
from .types import AircraftDefinition, MissionSpec, RunResult

# Progress goes through logging, never print: the library stays silent by default
# (tests, GUI), and each front end attaches the handler it wants. A single solve
# is 5-6 minutes and a full battery runs for hours, so a client that shows nothing
# is indistinguishable from a hang.
log = logging.getLogger("planeopt")

G = 9.81
M1_STATUS = "M1: fixed-design evaluation (Phase 1 gate pipeline) — no optimizer"

#: Wall-clock ceiling for ONE member solve, minutes. A converging solve on this
#: model takes 4-10 minutes; the cap exists because a diverging one has no
#: natural end — the 2026-07-29 flatness sweep spent 172 minutes on a single
#: member before failing anyway, which is 43% of that run's wall clock spent
#: learning nothing. Generous enough (3-5x the normal solve) that hitting it is
#: itself the diagnosis, and recorded as `Maximum_WallTime_Exceeded` when it is.
SOLVE_TIMEOUT_MIN = 30.0
#: Iteration ceiling for one member solve (IPOPT's own `max_iter`).
SOLVE_MAX_ITER = 1000
#: How far outside the mission's static-margin window a reported SM may land and
#: still count as satisfying it. An optimizer holds this constraint ACTIVE, so
#: the comparison has to admit the solver's own convergence tolerance or it
#: reports every champion as out of range.
SM_ACTIVE_TOL = 1e-4


class RunPaused(RuntimeError):
    """A battery stopped cleanly at a member boundary, on request.

    Not an error: everything finished is on disk in the checkpoint directory,
    and re-running the same command resumes from there.
    """


def _jsonable(value):
    """Plain-Python copy of a solve result, so it survives a JSON round trip.

    Results carry numpy scalars and tuples (`clmax_ab_used`), which `json` would
    either refuse or stringify — and a checkpoint that reloads a float as the
    string "np.float64(1.23)" is worse than no checkpoint at all.
    """
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    return str(value)


class _SolveCache:
    """Per-member results on disk, so a battery can be stopped and continued.

    A battery is a few dozen INDEPENDENT solves spread over hours, which is what
    makes this tractable: each member's result is pure data, so finishing one is
    progress that never has to be repeated. The cache is keyed by
    (phase label, member key) — the sequence is deterministic for a given
    aircraft and mission, so that is enough to line a resumed run up with the
    one it continues.

    It deliberately does NOT try to checkpoint a solve in progress; see
    `optimize`'s docstring for why that is not possible.
    """

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, label: str, key) -> Path:
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in f"{label}__{key}")
        return self.dir / f"{safe}.json"

    def get(self, label: str, key):
        path = self._path(label, key)
        if not path.is_file():
            return None
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt entry just means "re-solve"
            log.warning("checkpoint %s is unreadable; re-solving that member", path.name)
            return None

    def put(self, label: str, key, result: dict) -> None:
        import json

        path = self._path(label, key)
        try:
            # write-then-rename: a run killed mid-write must not leave a
            # half-file that the next run trusts
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps(_jsonable(result), indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:  # noqa: BLE001 — checkpointing must never kill a run
            log.warning("could not checkpoint %s/%s: %s", label, key, e)


class SolveFailure(RuntimeError):
    """A member solve that did not converge, carrying the solver's own verdict.

    CasADi's assertion text ends with `return_status is '...'` — the single
    piece of information a reader needs — so truncating that message for a log
    line drops exactly the diagnosis and keeps the boilerplate. The status is
    therefore read from the solver's stats and put first.

    `Infeasible_Problem_Detected` (over-constrained corner), `Restoration_Failed`
    (usually a NaN or a badly scaled constraint) and `Maximum_WallTime_Exceeded`
    (hit the guard above) call for completely different fixes, and until now the
    run artifact could not tell them apart.
    """

    def __init__(self, opti, exc: BaseException, labels: dict[int, str] | None = None):
        try:
            stats = opti.debug.stats()
        except Exception:  # pragma: no cover — stats missing before the first iterate
            stats = {}
        self.return_status = str(stats.get("return_status", "unknown"))
        self.iter_count = stats.get("iter_count")
        self.detail = str(exc)
        self.violations = _worst_violations(opti, labels or {})
        iters = "" if self.iter_count is None else f" after {self.iter_count} iterations"
        worst = f"; closest miss {self.violations[0]['what']}" if self.violations else ""
        super().__init__(f"{self.return_status}{iters}{worst}")


def _worst_violations(opti, labels: dict[int, str], top: int = 5) -> list[dict]:
    """Which constraints the last iterate could not satisfy, worst first.

    A status alone says the solve failed; this says what it failed ON, which is
    the difference between "the solver is broken" and "you asked for an aircraft
    that does not exist". Both of the 2026-07-30 chronic failures turned out to
    be the latter, and it took a bespoke script to find out — so the run now
    answers it itself.

    Diagnostics must never turn a failed solve into a crashed one, so the whole
    thing is best-effort.
    """
    try:
        import casadi as cas

        x, g = opti.x, opti.g
        if g.shape[0] == 0:
            return []
        xs = opti.debug.value(x)
        gv = np.array(cas.Function("g", [x], [g])(xs)).ravel()
        lbg = np.array(opti.debug.value(opti.lbg)).ravel()
        ubg = np.array(opti.debug.value(opti.ubg)).ravel()
        # how far outside its own bounds each row sits (0 when satisfied)
        below = np.where(np.isfinite(lbg), lbg - gv, -np.inf)
        above = np.where(np.isfinite(ubg), gv - ubg, -np.inf)
        viol = np.maximum(np.maximum(below, above), 0.0)
        viol = np.where(np.isfinite(viol), viol, 0.0)
        rows = [r for r in np.argsort(-viol)[:top] if viol[r] > 1e-8]
        return [
            {
                "row": int(r),
                "by": float(viol[r]),
                "value": float(gv[r]),
                "what": labels.get(int(r), f"g[{int(r)}]"),
            }
            for r in rows
        ]
    except Exception:  # noqa: BLE001 — never mask the real failure
        return []


class _ConstraintLabels:
    """Records which source line produced each row of `opti.g`, while building.

    CasADi numbers constraint rows; a person needs "the static-margin floor".
    Wrapping `subject_to` for the duration of the build is the only way to keep
    that mapping, and it costs one stack walk per constraint against a solve
    measured in minutes. Used only to make a FAILURE readable.

    The wrapper is bound to the INSTANCE, not the class: an exception during the
    build then cannot leave a global patch behind to corrupt every later solve
    in the process, and two Opti stacks alive at once cannot see each other's.
    """

    def __init__(self, opti):
        import traceback

        self.spans: list[tuple[int, int, str]] = []
        real = opti.subject_to  # already bound to this instance
        spans = self.spans

        def traced(constraint, *a, **kw):
            before = opti.g.shape[0]
            out = real(constraint, *a, **kw)
            added = opti.g.shape[0] - before
            if added > 0:
                frame = next(
                    (f for f in reversed(traceback.extract_stack()[:-1])
                     if "aerosandbox" not in f.filename),
                    None,
                )
                where = (
                    f"{Path(frame.filename).name}:{frame.lineno} {(frame.line or '').strip()}"
                    if frame is not None else "?"
                )
                spans.append((before, added, where[:120]))
            return out

        opti.subject_to = traced
        self._opti = opti

    def stop(self) -> None:
        """Hand the Opti back its own method; safe to call more than once."""
        self._opti.__dict__.pop("subject_to", None)

    def as_dict(self) -> dict[int, str]:
        return {r: src for start, n, src in self.spans for r in range(start, start + n)}


def _failure_record(exc: BaseException) -> dict:
    """The dict a failed job contributes to run.json."""
    rec = {"failed": str(exc)[:280]}
    if isinstance(exc, SolveFailure):
        rec["return_status"] = exc.return_status
        rec["iter_count"] = exc.iter_count
        if exc.violations:
            rec["violations"] = exc.violations
        if exc.return_status == "unknown":
            # no stats to read — the solver did not get far enough to have a
            # verdict, so the raw exception text is all there is. Keep it.
            rec["detail"] = exc.detail[:400]
    return rec


#: What a batch member's failure carries forward into the study/battery entry.
#: Every summariser projects a solve result down to a few fields, and each one
#: used to drop everything but the message.
_FAILURE_FIELDS = (
    "failed", "return_status", "iter_count", "violations", "detail", "solve_minutes",
)


def _failed_entry(r: dict) -> dict:
    return {k: r[k] for k in _FAILURE_FIELDS if k in r}


def run(
    aircraft: AircraftDefinition,
    mission: MissionSpec,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    v_sweep: tuple[float, float, float] | None = None,
    dv: dict | None = None,
    trim_guess: tuple[float, float] | None = None,
) -> tuple[RunResult, Path]:
    objective = OBJECTIVES[mission.objective]
    # The sweep window is the aircraft's speed envelope, so the aircraft may
    # declare it. A loiter plane and a speed plane do not overlap much: sweeping
    # 8-17 m/s over an airframe that stalls at 12.4 yields three usable points
    # and an empty power curve.
    if v_sweep is None:
        v_sweep = getattr(aircraft, "speed_sweep_ms", (8.0, 17.0, 0.5))
    log.info(
        "evaluating %s / %s over %d speed points",
        getattr(aircraft, "name", type(aircraft).__name__), mission.name,
        len(np.arange(*v_sweep)),
    )
    pt = aircraft.powertrain()
    bodies = aircraft.parasite_bodies(dv)
    pitch_control = getattr(aircraft, "pitch_control_name", "ruddervator")

    airplane = aircraft.geometry(dv)
    components, printed_breakdown = massmodel.build(aircraft, airplane, dv)
    mass_totals = massmodel.totals(components)
    auw, x_cg = mass_totals["auw_kg"], mass_totals["x_cg_m"]
    weight_n = auw * G

    # --- speed sweep: trim + power at each V ---
    # Continuation: each point seeds the next. Trim is a stiff root-find, and a
    # fixed starting guess only works while the sweep stays near it — marching
    # the solution along the sweep is what makes a wide speed range converge.
    sweep = []
    # Start from the caller's operating point when there is one — re-evaluating an
    # optimizer champion should begin where the optimizer left off, not at a
    # generic loiter guess several tens of degrees away.
    guess = trim_guess
    for V in np.arange(*v_sweep):
        try:
            t = aero.trim(
                airplane, float(V), weight_n, x_cg, bodies,
                control_name=pitch_control, guess=guess,
            )
            guess = (t["alpha_deg"], t["deflection_deg"])
            p = propulsion.solve(float(V), t["drag_n"], pt)
        except (RuntimeError, ValueError) as e:
            log.debug("V = %.1f m/s infeasible: %s", float(V), e)
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
    if not candidates:
        # Every point failed to trim or to close the propulsion chain. Report the
        # distinct causes: bare "max() iterable argument is empty" tells the user
        # nothing, and this is exactly where a broken install surfaces.
        reasons: dict[str, list[float]] = {}
        for s in sweep:
            reasons.setdefault(s.get("infeasible", "unknown"), []).append(s["V_ms"])
        detail = "; ".join(
            f"{reason} [V = {', '.join(f'{v:.1f}' for v in speeds[:3])}"
            f"{', ...' if len(speeds) > 3 else ''} m/s]"
            for reason, speeds in reasons.items()
        )
        raise RuntimeError(
            f"no feasible operating point anywhere in the {len(sweep)}-point speed "
            f"sweep, so there is nothing to report. Causes: {detail}"
        )
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
            # recorded, not just checked: the build document derives the allowable
            # CG window from this and cannot do so from the run artifact otherwise
            "static_margin_range": [float(x) for x in mission.static_margin_range],
            # Tolerance, for the same reason stall_ok has one: the NLP drives
            # this constraint ACTIVE, so an exact comparison against the bound
            # reports every optimized design as violating it — IPOPT converges
            # to 0.07999999 against a 0.08 floor and is entitled to. The
            # tolerance is deliberately tight (1e-4, one part in 800 of this
            # project's SM window): it absorbs solver and round-off noise and
            # nothing else, so a design that genuinely misses its floor still
            # says so.
            "sm_in_range": bool(
                mission.static_margin_range[0] - SM_ACTIVE_TOL
                <= sm["static_margin"]
                <= mission.static_margin_range[1] + SM_ACTIVE_TOL
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
    log.info("writing artifacts to %s", run_dir)
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
    # Buildable geometry: the loft definition and the placed 3D curves. A report
    # tells you whether the design is good; these tell you how to cut it, and
    # they come from the same airplane object that was analysed.
    geometry_export.write(airplane, run_dir)
    # Build document: the same geometry again, but answering "what do I cut and
    # what must I hit" — spars, hinges, edge polylines and the CG window.
    manufacturing.write(result, airplane, aircraft, run_dir)
    (run_dir / "report.html").write_text(report_html.render(result, run_dir), encoding="utf-8")
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
    timeout_min: float = SOLVE_TIMEOUT_MIN,
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
    # Record which source line each constraint row comes from, so that if this
    # solve fails the artifact can name the constraint it could not satisfy
    # rather than a row index (_ConstraintLabels).
    labels = _ConstraintLabels(opti)
    dv = aircraft.design_variables(opti, inits)
    bodies = aircraft.parasite_bodies(dv)  # may be symbolic (fuselage loft)
    # Operating-point box bounds. These are numerical brackets, not physics —
    # the physics is in the constraints below — but a bracket sized for a loiter
    # plane silently caps a speed design (V at 25 m/s, elevator at 15 deg). The
    # aircraft may therefore declare its own envelope; the defaults are the
    # values every M0-M4.8 run used, so declared-free aircraft are unaffected.
    envelope = getattr(aircraft, "operating_bounds", None) or {}
    v_lo, v_hi = envelope.get("V_ms", (6.0, 25.0))
    a_lo, a_hi = envelope.get("alpha_deg", (-2.0, 10.0))
    d_lo, d_hi = envelope.get("deflection_deg", (-15.0, 15.0))
    n_lo, n_hi = envelope.get("prop_rev_s", (20.0, 200.0))
    V = opti.variable(
        init_guess=(inits or {}).get("V", 11.0), lower_bound=v_lo, upper_bound=v_hi
    )
    alpha = opti.variable(init_guess=4.0, lower_bound=a_lo, upper_bound=a_hi)
    defl = opti.variable(init_guess=0.0, lower_bound=d_lo, upper_bound=d_hi)
    n = opti.variable(init_guess=65.0, lower_bound=n_lo, upper_bound=n_hi)

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

    # static margin about the produced CG: regression slope over the shared
    # alpha window (LL's local Cm derivative is noisy — FINDINGS.md), plus the
    # Munk fuselage destabilizing term converted to CL-space via the lift slope.
    # The estimator itself lives in aero, so the numeric re-evaluation below
    # measures the same quantity this constraint holds (aero.SM_ALPHA_OFFSETS).
    offs = aero.SM_ALPHA_OFFSETS
    sm_runs = [
        asb.LiftingLine(
            airplane=airplane,
            op_point=asb.OperatingPoint(velocity=V, alpha=alpha + o),
            xyz_ref=[x_cg, 0, 0],
        ).run()
        for o in offs
    ]
    sm = aero.static_margin_from_polar(
        [r["CL"] for r in sm_runs], [r["Cm"] for r in sm_runs],
        list(offs), bodies, s_ref, airplane.c_ref,
    )
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

    # --- powertrain envelope (MODEL_DETAILS section 2.5) ---
    # Real limits, not preferences: the motor cannot be fed more than the pack
    # holds (terminal voltage <= pack voltage IS throttle <= 100%), and current
    # must stay inside the rating this objective is allowed to use. Both are
    # slack by orders of magnitude at a loiter point and both bind on a speed
    # objective — without them "maximize speed" is bounded only by where the
    # prop fit runs out, which is an artefact rather than an airplane.
    opti.subject_to(pr["voltage"] <= pt.battery.v_nominal)
    current_cap = (
        pt.motor.max_current_a
        if objective.current_limit == "burst"
        else pt.esc_continuous_current_a
    )
    opti.subject_to(pr["current_a"] <= current_cap)
    # Declared placard speed: flutter and divergence are beyond this model, so a
    # speed objective is capped by a number the aircraft declares rather than by
    # a prediction the model cannot make (MODEL_DETAILS section 2.5).
    placard = getattr(aircraft, "placard_speed_ms", None)
    if placard is not None:
        opti.subject_to(V <= float(placard))

    p_bus_eff = pr["p_bus_w"] / eta_scale  # eta_scale: chain-efficiency re-solves
    # Two expressions, deliberately: `obj_expr` is what gets REPORTED, in the
    # objective's own units, and is read back from the solution below. What the
    # solver minimizes may be a better-behaved monotone equivalent — endurance's
    # reported form is a quotient with a pole inside the variable box
    # (mission.Objective.nlp_surrogate, FINDINGS §14.5.5).
    obj_expr = objective.evaluator(V, p_bus_eff, mission, pt)
    opti.minimize(objective.nlp_expression(V, p_bus_eff, mission, pt))

    # detect_simple_bounds: hand the plain variable bounds to IPOPT as BOUNDS
    # rather than as ordinary constraint rows. Without it the box lives in `g`,
    # which an interior-point method is free to violate on the way to a
    # solution — so the model gets evaluated at negative chords and negative
    # boom lengths, and the resulting NaN is a solver failure rather than a
    # rejected point. It also drops 2 rows per design variable from the
    # Jacobian.
    labels.stop()
    try:
        sol = opti.solve(
            verbose=False,
            max_iter=SOLVE_MAX_ITER,
            detect_simple_bounds=True,
            # WALL time, not CPU time. AeroSandbox's own `max_runtime` maps to
            # IPOPT's `max_cpu_time`, which is the wrong unit for this guard: a
            # solve peaks near 13 GB on a 25 GB machine, and the case worth
            # bailing out of is exactly the one where it starts swapping and CPU
            # time falls behind the clock. What is being protected is the run's
            # wall clock, so that is what gets capped.
            options={"ipopt.max_wall_time": 60.0 * timeout_min},
        )
    except RuntimeError as e:
        raise SolveFailure(opti, e, labels.as_dict()) from None
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
        "motor_voltage": float(sol(pr["voltage"])),
        "motor_current_a": float(sol(pr["current_a"])),
        "throttle_frac": float(sol(pr["voltage"])) / pt.battery.v_nominal,
        "current_cap_a": current_cap,
        "placard_speed_ms": float(placard) if placard is not None else None,
        "drag_n": float(sol(drag)),
        "J": float(sol(pr["J"])),
        "clmax_ab_used": clmax_ab,
    }


def _solve_worker(conn, aircraft, mission, kw):  # pragma: no cover — child process
    t0 = time.monotonic()
    try:
        r = _solve_nlp(aircraft, mission, **kw)
    except Exception as e:
        r = _failure_record(e)
    r["solve_minutes"] = round((time.monotonic() - t0) / 60.0, 2)
    # A forked worker is the only place a genuine per-solve peak can be read:
    # this process did exactly one solve, so its high-water mark IS that solve's.
    # It is what the next run's memory budget divides by (memory.py).
    r["peak_rss_gb"] = memory.peak_rss_gb()
    conn.send(r)
    conn.close()


def parallel_available() -> bool:
    """Whether concurrent solves are possible on this platform.

    Workers inherit the aircraft/mission objects across the fork instead of
    pickling them — those objects carry bound methods and CasADi state and are
    not picklable, so `spawn` (the only start method on Windows) cannot serve
    them. Concurrency is therefore POSIX-only; every other feature is portable.
    """
    import multiprocessing as mp

    return "fork" in mp.get_all_start_methods()


def check_parallel(parallel: int) -> None:
    """Reject an impossible width up front, not after the first batch."""
    if parallel > 1 and not parallel_available():
        raise RuntimeError(
            f"parallel={parallel} needs the 'fork' start method, which this platform "
            "(Windows) does not have — the aircraft definition cannot be pickled for "
            "a spawned worker. Run with parallel=1; solves then run one at a time."
        )


def _log_result(label: str, key, done: int, total: int, result: dict) -> None:
    # THIS solve's minutes, not the batch's elapsed time: a sequential batch
    # reported cumulative time against every member, which reads as though each
    # one got slower than the last.
    mins = result.get("solve_minutes") or 0.0
    peak = result.get("peak_rss_gb") or 0.0
    ram = f", peak {peak:.1f} GB" if peak else ""
    if "failed" in result:
        log.info("  %s [%d/%d] %s: FAILED — %s (%.1f min%s)",
                 label, done, total, key, result["failed"], mins, ram)
    else:
        log.info("  %s [%d/%d] %s: objective %.4g (%.1f min%s)",
                 label, done, total, key, result["objective_value"], mins, ram)


def _solve_many(
    aircraft, mission, jobs, parallel: int = 1, prep=None, restore=None,
    label: str = "solve", timeout_min: float = SOLVE_TIMEOUT_MIN,
    cache: "_SolveCache | None" = None, pause_file: Path | None = None,
) -> dict:
    """Run independent _solve_nlp jobs, `parallel` at a time.

    jobs: [(key, kwargs)] -> {key: result | {"failed": ...}}. prep(key)/restore()
    bracket each launch so per-candidate aircraft attrs (discrete studies,
    winglet toggles) are seen by that job only — with parallel > 1 the forked
    child snapshots them at launch. parallel=1 is the historical in-process
    path and the only safe mode under a ~15 GB WSL cap (each solve peaks
    ~13 GB — HANDOFF section 2); 2-wide needs the 26 GB .wslconfig active.
    A job failure never kills the batch. `label` names the batch in the
    progress log.

    `cache` makes each finished member durable, so a stopped run continues
    rather than restarting; `pause_file`, if it exists when a member finishes,
    stops the battery cleanly at that boundary (RunPaused). Member boundaries
    are the only place a pause can free memory — see `optimize`.
    """
    check_parallel(parallel)
    results = {}
    jobs = [(key, {"timeout_min": timeout_min, **kw}) for key, kw in jobs]
    total = len(jobs)
    log.info("%s: %d solve(s), %d-wide", label, total, max(1, parallel))
    if parallel <= 1:
        for key, kw in jobs:
            done = cache.get(label, key) if cache is not None else None
            if done is not None:
                results[key] = done
                log.info("  %s [%d/%d] %s: from checkpoint", label, len(results), total, key)
                continue
            if prep is not None:
                prep(key)
            t_job = time.monotonic()
            try:
                results[key] = _solve_nlp(aircraft, mission, **kw)
            except RuntimeError as e:
                results[key] = _failure_record(e)
            finally:
                if restore is not None:
                    restore()
            results[key]["solve_minutes"] = round((time.monotonic() - t_job) / 60.0, 2)
            # In-process, the high-water mark spans the whole batch rather than
            # this one solve — an over-estimate of a single peak, which is the
            # safe direction for a number that later sizes a parallel width.
            results[key]["peak_rss_gb"] = memory.peak_rss_gb()
            _log_result(label, key, len(results), total, results[key])
            if cache is not None:
                cache.put(label, key, results[key])
            if pause_file is not None and Path(pause_file).exists():
                raise RunPaused(
                    f"paused after {label}/{key} — {len(results)} of {total} members "
                    f"of this phase are checkpointed"
                )
        return results

    import multiprocessing as mp
    from multiprocessing.connection import wait as conn_wait

    ctx = mp.get_context("fork")  # children inherit aircraft/mission — no pickling
    pending = list(jobs)
    running = {}  # receiving pipe end -> (key, process)
    while pending or running:
        while pending and len(running) < parallel:
            key, kw = pending.pop(0)
            done = cache.get(label, key) if cache is not None else None
            if done is not None:
                results[key] = done
                log.info("  %s [%d/%d] %s: from checkpoint", label, len(results), total, key)
                continue
            rx, tx = ctx.Pipe(duplex=False)
            if prep is not None:
                prep(key)
            proc = ctx.Process(target=_solve_worker, args=(tx, aircraft, mission, kw))
            proc.start()
            tx.close()
            if restore is not None:
                restore()
            running[rx] = (key, proc)
        for rx in conn_wait(list(running)):
            key, proc = running.pop(rx)
            try:
                results[key] = rx.recv()
            except EOFError:  # child died without reporting — OOM killer, most likely
                results[key] = {"failed": "worker died before reporting (OOM?)"}
            proc.join()
            rx.close()
            _log_result(label, key, len(results), total, results[key])
            if cache is not None:
                cache.put(label, key, results[key])
        # A pause waits for the whole in-flight group: killing a running child
        # would throw away a solve that is minutes from finishing.
        if pause_file is not None and Path(pause_file).exists() and not running:
            raise RunPaused(
                f"paused during {label} — {len(results)} of {total} members "
                f"of this phase are checkpointed"
            )
    return results


def optimize(
    aircraft,
    mission,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    multistart: int = 3,
    flatness: bool = True,
    parallel: int = 1,
    memory_budget_gb: float | None = None,
    warm_start: dict | None = None,
    warm_start_from: str | None = None,
    solve_timeout_min: float = SOLVE_TIMEOUT_MIN,
    checkpoint_dir: Path | None = None,
    pause_file: Path | None = None,
) -> tuple[RunResult, Path]:
    """M2 entry point: multi-start NLP -> champion -> shadow price -> flatness
    sweep -> numeric re-evaluation of the champion through the M1 pipeline.

    parallel: how many NLP solves may run concurrently within each independent
    batch (multistart+bump, flatness, re-solve battery, discrete-study
    alternatives, winglet pair). 1 = sequential (default; required under the
    15 GB WSL cap). Cross-batch order is unchanged, so study semantics are
    identical at any width.

    memory_budget_gb: how much RAM the user is willing to dedicate. It does not
    make a solve faster — a solve is single-core and memory-bound — it decides
    how many fit side by side, so it is just a friendlier way to say `parallel`
    (memory.py). Divided by the per-solve peak this aircraft has actually been
    measured at, so the arithmetic gets better the more you run. An explicit
    `parallel` wins, since it is the more specific instruction.

    solve_timeout_min: wall-clock ceiling for any ONE member solve. A battery is
    a fixed set of independent solves and a diverging one has no natural end, so
    without a cap a single bad member can own the whole run (SOLVE_TIMEOUT_MIN).
    Members that hit it are recorded as `Maximum_WallTime_Exceeded` and the
    battery carries on.

    checkpoint_dir / pause_file: stop a multi-hour battery and get the machine
    back, without losing what it has already done. Creating `pause_file` makes
    the run finish the member in flight, then exit with `RunPaused`; every member
    completed so far is in `checkpoint_dir`, and re-running the same command with
    the same checkpoint directory continues from there.

    **The pause is at MEMBER boundaries, and that is not a shortcut — it is the
    only point where memory can actually be released.** A solve in progress is
    ~13 GB of CasADi graph plus IPOPT's barrier state, filter and MUMPS
    factorization; none of that is serialisable through CasADi, so freeing the
    memory necessarily destroys it. The most that could be salvaged mid-solve is
    the current iterate as a warm start, and this project has already measured
    warm starts as a wash on this model (HANDOFF: the champion sits on many
    active bounds, so IPOPT pushes off them at startup regardless). Waiting for
    the member boundary therefore costs at most `solve_timeout_min` and loses
    nothing, where a mid-solve pause would free the same memory and throw the
    solve away."""
    if memory_budget_gb is not None and parallel <= 1:
        per = memory.observed_peak_gb(runs_root)
        parallel, why = memory.plan_parallel(memory_budget_gb, per_solve_gb=per)
        log.info(
            "memory budget %.0f GB: %s%s",
            memory_budget_gb, why,
            "" if per else f" (no measured peak yet — assuming {memory.DEFAULT_PER_SOLVE_GB:.0f} GB)",
        )
    check_parallel(parallel)
    t_start = time.monotonic()
    total_gb, avail_gb = memory.machine_ram()
    log.info(
        "optimize: %s / %s — objective %s. Each NLP solve takes minutes and peaks "
        "near %.0f GB; a full battery runs for hours. RAM: %.1f GB free of %.1f GB.",
        getattr(aircraft, "name", type(aircraft).__name__), mission.name, mission.objective,
        memory.observed_peak_gb(runs_root) or memory.DEFAULT_PER_SOLVE_GB, avail_gb, total_gb,
    )
    if warm_start:
        log.info("warm start: seeding the nominal solve and every study candidate "
                 "from %s (all variables stay free — this is an initial guess, "
                 "not a constraint)", warm_start_from or "a previous champion")
    warm = {"inits": dict(warm_start)} if warm_start else {}

    # Where the hours actually went. Reconstructing this from the progress log
    # after the fact is what turned up the 2026-07-29 finding that 87% of a
    # 405-minute run was spent on phases that failed or barely informed; it
    # belongs in the artifact, next to what each phase concluded.
    phase_minutes: dict[str, float] = {}

    cache = _SolveCache(checkpoint_dir) if checkpoint_dir is not None else None
    if cache is not None:
        log.info("checkpointing members to %s%s", cache.dir,
                 f"; create {pause_file} to pause at the next member boundary"
                 if pause_file is not None else "")

    def batch(label, jobs, **kw):
        t_phase = time.monotonic()
        try:
            return _solve_many(
                aircraft, mission, jobs, parallel, label=label,
                timeout_min=solve_timeout_min, cache=cache, pause_file=pause_file,
                **kw
            )
        finally:
            phase_minutes[label] = round(
                phase_minutes.get(label, 0.0) + (time.monotonic() - t_phase) / 60.0, 1
            )

    rng = np.random.default_rng(0)
    # The nominal start is warmed; the PERTURBED starts are deliberately left
    # cold, so multistart still answers "does this converge from elsewhere?".
    # A warm start that also seeded them would agree with itself by construction.
    jobs = [("nominal", dict(warm))]
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
        jobs.append((f"perturbed_{i}", {"inits": inits}))
    # the +20 g shadow-price bump is independent of the champion, so it rides
    # the same batch; its delta is computed afterwards
    jobs.append(("mass_bump", {"extra_mass_kg": 0.020}))
    first = batch("multistart", jobs)
    starts, results = [], []
    for key, _ in jobs:
        if key == "mass_bump":
            continue
        r = first[key]
        results.append(r)
        starts.append(key if "failed" not in r else f"{key} (failed)")

    ok = [r for r in results if "failed" not in r]
    sign = 1 if OBJECTIVES[mission.objective].direction == "maximize" else -1
    champion = max(ok, key=lambda r: sign * r["objective_value"])
    spread = max(abs(r["objective_value"] - champion["objective_value"]) for r in ok)

    # shadow price: minutes (objective units) per gram of structure
    bumped = first["mass_bump"]
    shadow_per_g = (
        (bumped["objective_value"] - champion["objective_value"]) / 20.0
        if "failed" not in bumped
        else None
    )

    # flatness: re-optimize everything else at fixed spans (up to the cap)
    flat = []
    span_cap = getattr(aircraft, "span_cap_m", 3.0)
    if flatness:
        # Swept DOWNWARD from the cap, and short-circuited when a member proves
        # infeasible. Both halves matter:
        #
        # Downward, because feasibility in span is an interval [s_min, cap] on
        # this class of model — shrinking span at a fixed wing area drives CL up
        # and makes the stall, gust and stability constraints harder, never
        # easier. Sweeping up from the bottom licenses no inference at all: 1.5 m
        # being infeasible says nothing about 1.6 m.
        #
        # Only on a PROOF, because `Infeasible_Problem_Detected` is the solver
        # certifying there is no aircraft there, whereas a timeout certifies
        # nothing — cascading a timeout would silently discard spans that are
        # merely slow. The 2026-07-30 sweep spent ~2 hours re-deriving that its
        # bottom end is empty (FINDINGS §14.5.8).
        spans = sorted((float(s) for s in np.linspace(1.5, span_cap, 6)), reverse=True)
        fr, floor = {}, None
        for span in spans:
            if floor is not None:
                fr[span] = {
                    "failed": f"skipped: {floor:.2f} m proved infeasible and span "
                    "feasibility is an interval up to the cap",
                    "return_status": "Skipped_Below_Infeasible_Span",
                }
                log.info("  flatness sweep: %.2f m skipped (below the infeasible %.2f m)",
                         span, floor)
                continue
            one = batch("flatness sweep", [(span, {"fixed": {"span": span}})])
            fr[span] = one[span]
            if fr[span].get("return_status") == "Infeasible_Problem_Detected":
                floor = span
        spans = sorted(spans)
        flat = [
            {"span": s, "objective_value": None, **_failed_entry(fr[s])}
            if "failed" in fr[s]
            else {
                "span": s,
                "objective_value": fr[s]["objective_value"],
                "solve_minutes": fr[s].get("solve_minutes"),
            }
            for s in spans
        ]

    # re-solve battery (MODEL_DETAILS 6.4 item 2): each is a full re-optimization
    battery_jobs = [
        ("printed_mass_x1.10", {"printed_scale": 1.10}),
        ("printed_mass_x0.90", {"printed_scale": 0.90}),
        ("chain_eta_x0.90", {"eta_scale": 0.90}),
        ("chain_eta_x1.10", {"eta_scale": 1.10}),
    ]
    battery = {}
    battery_results = batch("re-solve battery", battery_jobs)
    for label, r in battery_results.items():
        if "failed" in r:
            battery[label] = _failed_entry(r)
        else:
            battery[label] = {
                "objective_value": r["objective_value"],
                "delta": r["objective_value"] - champion["objective_value"],
                "span": r["dv"]["span"],
                "static_margin": r["static_margin"],
                "ballast_kg": r["dv"]["ballast_kg"],
            }

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
        cands = [c for c in candidates if c != baseline]
        # alternatives within one attr are independent solves (each candidate's
        # solve depends only on its own attr value, not on the champion), so
        # they may run concurrently; adoption below is order-identical to the
        # sequential greedy (winner = argmax over baseline + candidates)
        res = batch(
            f"study {attr}", [(c, dict(warm)) for c in cands],
            prep=lambda c, a=attr: setattr(aircraft, a, c),
            restore=lambda a=attr, b=baseline: setattr(aircraft, a, b),
        )
        for cand in cands:
            r_c = res[cand]
            if "failed" in r_c:
                study["alternatives"][cand] = _failed_entry(r_c)
                continue
            delta = r_c["objective_value"] - champion["objective_value"]
            study["alternatives"][cand] = {
                **{k: r_c[k] for k in ("objective_value", "V_ms", "auw_kg")},
                "delta_objective": delta,
            }
            if sign * delta > 0:
                champion = r_c
                study["adopted"] = cand
                setattr(aircraft, attr, cand)
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
        prev_cant = getattr(aircraft, "tip_dihedral_max_deg", 20.0)

        def _wl_prep(key):
            aircraft.winglet = False
            if key == "continuous_cant":
                aircraft.tip_dihedral_max_deg = 88.0

        def _wl_restore():
            aircraft.winglet = True
            aircraft.tip_dihedral_max_deg = prev_cant

        wr = batch(
            "winglet study", [("off", {}), ("continuous_cant", {})],
            prep=_wl_prep, restore=_wl_restore,
        )

        r_off = wr["off"]
        if "failed" in r_off:
            winglet_study["off"] = _failed_entry(r_off)
        else:
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

        r_cant = wr["continuous_cant"]
        if "failed" in r_cant:
            winglet_study["continuous_cant"] = _failed_entry(r_cant)
        else:
            winglet_study["continuous_cant"] = {
                "objective_value": r_cant["objective_value"],
                "tip_dihedral_deg": r_cant["dv"].get("dihedral_tip"),
                "d_exp": r_cant["dv"].get("d_exp"),
                "span": r_cant["dv"]["span"],
                "caveat": "Schrenk stall stations include the canted region — "
                "indicative only; the spar-fit constraint also binds high cant",
            }

    # numeric re-evaluation of the champion through the full M1 pipeline
    # (winglet-free when the study rejected it — champion is the off-solve then)
    log.info("re-evaluating the champion numerically and writing artifacts")
    if winglet_rejected:
        aircraft.winglet = False
    # A champion is only half described by its design vector; the studies also
    # picked tail type, topology, mount, prop and winglet, and those are plain
    # attributes. Record them, so rebuilding the champion later cannot silently
    # fall back to the aircraft file's defaults (report/assemble.as_champion).
    champion["discrete"] = {
        attr: getattr(aircraft, attr)
        for attr in (getattr(aircraft, "discrete_options", None) or {})
        if hasattr(aircraft, attr)
    }
    if hasattr(aircraft, "winglet"):
        champion["discrete"]["winglet"] = bool(aircraft.winglet)
    reeval_error = None
    try:
        result, run_dir = run(
            aircraft, mission, runs_root, input_files, dv=champion["dv"],
            trim_guess=(champion["alpha_deg"], champion["deflection_deg"]),
        )
        # tripped-polar dual evaluation at the champion point (MODEL_DETAILS 3.2)
        best = result.performance["best"]
        champ_plane = aircraft.geometry(champion["dv"])
    except Exception as e:  # noqa: BLE001
        # The re-evaluation is a *reporting* step: it re-runs the champion through
        # the numeric M1 pipeline for cross-checking. Losing it costs the check,
        # not the optimization — and an optimization is hours of solving. Write
        # everything the NLP found, flagged, instead of discarding the run.
        reeval_error = f"{type(e).__name__}: {e}"
        log.warning("champion re-evaluation failed; writing NLP results without it — %s",
                    reeval_error)
        best = champ_plane = None
        result = RunResult(
            aircraft=getattr(aircraft, "name", type(aircraft).__name__),
            mission=mission.name,
            objective=mission.objective,
            status=M2_STATUS,
            created=datetime.datetime.now().isoformat(timespec="seconds"),
            performance={"objective_units": OBJECTIVES[mission.objective].units},
        )
        run_dir = assemble.write_run_dir(result, runs_root, input_files or [])
    finally:
        if winglet_rejected:
            aircraft.winglet = True
        for attr, val in discrete_originals.items():
            setattr(aircraft, attr, val)
    result.status = M2_STATUS
    if best is not None:
        # The two SM numbers side by side. They now come from the same estimator
        # (aero.SM_ALPHA_OFFSETS), so what is left is the difference between the
        # NLP's cruise alpha and the re-evaluation's trimmed one — real, since
        # SM varies with alpha on this model, and worth seeing rather than
        # rediscovering as a mystery 0.002.
        result.constraints["static_margin_nlp"] = champion["static_margin"]
        result.constraints["static_margin_gap"] = (
            result.constraints["static_margin"] - champion["static_margin"]
        )
    if warm_start:
        # provenance: a champion seeded from another run must say so, because the
        # local optimum it found may depend on where it started
        result.diagnostics["warm_started_from"] = warm_start_from or "(unnamed)"
    if reeval_error is not None:
        result.diagnostics["champion_reeval_failed"] = reeval_error
        result.notes.append(
            "Champion re-evaluation through the numeric M1 pipeline FAILED — the "
            "design vector and study results below are the optimizer's, "
            "un-cross-checked. Treat them as provisional."
        )

    tripped = None
    if best is not None:
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
        "nlp_vs_reeval_gap": (
            champion["objective_value"]
            - result.performance["best"].get("objective_value", float("nan"))
            if best is not None
            else None
        ),
    }
    result.notes.append(
        "M3 NLP: trimmed (explicit deflection), SM window, gust margin, spar "
        "stress/deflection sizing, ballast cap, battery-position balance."
    )
    # Measured per-solve peak, so the NEXT run's memory budget divides by data
    # rather than by the folklore 13 GB. Children cover the forked (parallel)
    # path, self covers the in-process one; whichever ran, the other reads 0.
    result.diagnostics["peak_rss_gb"] = round(
        max(memory.peak_rss_gb(children=True), memory.peak_rss_gb()), 2
    )
    result.diagnostics["parallel_width"] = parallel
    result.diagnostics["solve_timeout_min"] = solve_timeout_min
    phase_minutes["re-eval + artifacts"] = round(
        (time.monotonic() - t_start) / 60.0 - sum(phase_minutes.values()), 1
    )
    result.diagnostics["phase_minutes"] = phase_minutes
    if memory_budget_gb is not None:
        result.diagnostics["memory_budget_gb"] = memory_budget_gb
    figures.flatness_plot(flat, champion, run_dir / "figures")
    # run.json is the machine-readable truth and is written first: rendering the
    # HTML must never be what loses a completed optimization.
    (run_dir / "run.json").write_text(
        __import__("json").dumps(__import__("dataclasses").asdict(result), indent=2, default=str),
        encoding="utf-8",
    )
    try:
        (run_dir / "report.html").write_text(report_html.render(result, run_dir), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("report.html could not be rendered (run.json is intact): %s", e)
    log.info(
        "done in %.1f min — champion objective %.4g, artifacts in %s",
        (time.monotonic() - t_start) / 60.0, champion["objective_value"], run_dir,
    )
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
