"""Price the caps behind an aircraft's over-constrained corners.

WHAT THIS IS FOR

The first `vtail_rcv2` battery spent 287.7 of its 417.5 minutes (69%) on ten
members that produced nothing, all `Maximum_WallTime_Exceeded`, and three
studies returned no verdict at all. `tools/degeneracy.py` settled what they are:
NOT degenerate (cond 2.49, LICQ holds) but **over-constrained corners** — 18
rows violated at once, dominated by lift equilibrium and the static-margin
floor. FINDINGS section 14.5.7 measured that more clock does not convert one:
2.5x the iterations closed nothing.

HANDOFF names the remedy — raise chord, raise span, widen the static-margin
window, or carry less kit — and says it is a user decision. **None of the four
has a price.** This tool measures them, using the recipe section 14.5.8 already
validated on `vtail_sample`, where relaxing the SM floor 0.08 -> 0.05 turned two
chronic timeouts into converged solves in ~5 minutes each and identified the
third corner as genuinely empty.

    # the whole overnight plan, resumable, one solve per process.
    # NOTHING ELSE MAY BE SOLVING: a cell peaks near 15 GB and so does a
    # battery, and two of them on one machine is the swap path solve.py warns
    # about. There is no lock that enforces this — check with `ps` first.
    uv run python tools/price_caps.py drive

    # one cell, if you want to check something by hand
    uv run python tools/price_caps.py cell --member tail_ttail --relax sm_floor_0.05

    # what has been measured so far. Cells land in `runs/_capprice/` (untracked);
    # the ones committed with this tool are read with
    #   PRICE_CAPS_OUT=docs/studies/rcv2_cap_pricing uv run python tools/price_caps.py report
    uv run python tools/price_caps.py report

WHY ONE PROCESS PER CELL

A solve peaks at 10.18 GB on this 16 GB box (FINDINGS section 23.4) and the RSS
high-water mark only ever rises in-process. A cell per process gives every
member the same clean machine, so `peak_rss_gb` means the same thing in every
row, and a cell that dies takes nothing else with it.

WHY THE BASELINE BUDGET IS SHORTER THAN THE RUN'S

Section 14.5.7 is the licence: a stuck member's verdict does not change with
more clock (25 -> 60 min bought a worse `inf_du` and no better `inf_pr`), while
a converging member on this model lands in 5-10 minutes. So the baseline stage
runs at `--baseline-timeout-min` (default 15) and reads the three-way verdict
`solve._convergence_trace` already produces. A member that trace calls CUT OFF
rather than STUCK is re-run at the full ceiling rather than being written down
as a timeout — that distinction is exactly what the instrument was added for.

EVERY CELL IS APPENDED AS ONE JSON LINE, so an overnight run that is interrupted
keeps everything it has measured, and re-running `drive` skips what is already
there.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: Overridable so a `--max-iter 3` smoke run (FINDINGS 24.2 — exercise the whole
#: pipeline in seconds) cannot write iteration-truncated cells into the record
#: that overnight solves are accumulating. It is inherited by the per-cell
#: child processes, so setting it once covers the whole plan.
OUT = Path(os.environ.get("PRICE_CAPS_OUT") or REPO / "runs" / "_capprice")
CELLS = OUT / "cells.jsonl"

# --- the members that failed, and the caps that might unstick them ----------

#: The rcv2 battery's non-converging members, reconstructed from their declared
#: study definitions. Keys are labels; the values say how to BUILD that member —
#: `set` are aircraft attributes (what a discrete study varies), `kw` are
#: `_solve_nlp` keyword arguments (what the sensitivity battery varies).
MEMBERS: dict[str, dict] = {
    "nominal": {},
    "tail_conventional": {"set": {"tail_type": "conventional"}},
    "tail_ttail": {"set": {"tail_type": "ttail"}},
    "fuselage_integrated": {"set": {"fuselage_topology": "integrated"}},
    "dihedral_polyhedral2": {"set": {"wing_dihedral_form": "polyhedral2"}},
    "printed_mass_x1.10": {"kw": {"printed_scale": 1.10}},
    #: Not a lost member — the +20 g bump the battery rides in its own multistart
    #: batch. It is here because `solve.screen_discrete` needs the run's OWN
    #: shadow price in minutes per gram, and without it the prop screen is
    #: systematically biased toward big propellers (a 14 in disc arrives
    #: weightless — the defect that held the diameter cap at 11 in until
    #: 2026-07-30). Reproducing the battery's greedy chain therefore starts here.
    "mass_bump": {"kw": {"extra_mass_kg": 0.020}},
    # `flatness_<span>` is accepted dynamically — the sweep's spans depend on the
    # champion's span, which is not known until the nominal member converges.
}

#: The four levers HANDOFF puts in front of the user, one cell each.
#:
#: `sm_floor_0.05` is the DIAGNOSTIC, not a proposal: 0.05 is where 14.5.8 got
#: its answer, and if a corner converges there the bisection stage finds the
#: smallest floor that still works, because "you must give up 0.01 of static
#: margin" is a decision and "give up 0.03" is a different one.
#:
#: `span_cap_2.2` is included because HANDOFF lists it, and reported with the
#: caveat that this model prices none of what the 2.0 m cap is actually for
#: (transport, storage, hand-launch, print bed — see `VTailSample.span_cap_m`).
#: The two POD-LENGTH levers, added 2026-08-07 because the row that actually
#: blocks this aeroplane was not in the list above. On the
#: `20260807T061330` battery **five of six failures name
#: `aircraft.py:1138`, `usable_nose / motor["length"] >= 1.0`, as their closest
#: miss** — and they miss it by 1.4 to 3.3 mm of usable nose. None of the four
#: caps above touches it.
#:
#: The row is unrelievable on its own terms because the pod is a fully
#: determined system: the fineness ceiling pins total length at exactly
#: 8.0000 d_eq, the boat-tail floor pins the tail at exactly 1.8000 d_eq, the
#: motor pins the nose at exactly 74.07 mm, and the bay takes what is left and
#: must still hold the stack. So the levers are the two rows that BUY LENGTH.
#:
#: `boat_tail_1.5` is only expressible because `boat_tail_min_d_eq` became a
#: named attribute this session; it was a literal inside `geometry_constraints`
#: before, and `--set` cannot reach a literal.
#:
#: Not included, deliberately: a smaller motor can. It would unstick the row
#: too, but `COMPONENT_ENVELOPES` is a nested dict rather than a scalar
#: attribute, and swapping the motor is a hardware decision rather than a cap.
POD_LENGTH_RELAXATIONS: dict[str, dict] = {
    "fineness_9.0": {"set": {"fineness_max": 9.0}},
    "boat_tail_1.5": {"set": {"boat_tail_min_d_eq": 1.5}},
}

RELAXATIONS: dict[str, dict] = {
    "none": {},
    "sm_floor_0.05": {"sm_floor": 0.05},
    "c_root_0.300": {"set": {"c_root_max_m": 0.300}},
    "span_cap_2.2": {"set": {"span_cap_m": 2.2}},
    # DIAGNOSTIC, not a proposal. The payload is not optional (see
    # `AIRFRAME_ONLY_OMITS`); this cell answers "is this corner caused by the
    # payload?", and a yes points at pod size rather than at the parts list.
    "airframe_only": {"set": {"equipment_fit": "airframe_only"}},
    **POD_LENGTH_RELAXATIONS,
    #: NOT a relaxation — the GREEDY STATE. A battery's studies run in declared
    #: order, each with the previous studies' adopted values, so by the time
    #: `tail_type` is judged the aeroplane already carries the prop the prop
    #: study adopted. Every cell in this study carries the declared incumbent
    #: (`ancf_11x6`) instead, which is the same label on a different aeroplane
    #: and was the study's last open caveat.
    #:
    #: `ancf_12x10` is not a guess: `screen` ranks it first of 65 candidates at
    #: the champion's own operating point and its own shadow price, and it is
    #: what the 2.0 m sample battery adopted. Running the members under it is
    #: what turns "these converge" into "these converge where the battery ran
    #: them".
    "prop_12x10": {"set": {"prop_choice": "ancf_12x10"}},
}


def member_spec(name: str) -> dict:
    if name in MEMBERS:
        return MEMBERS[name]
    if name.startswith("flatness_"):
        return {"kw": {"fixed": {"span": float(name.removeprefix("flatness_"))}}}
    raise SystemExit(f"unknown member {name!r}")


def _one_relax_spec(name: str) -> dict:
    if name in RELAXATIONS:
        return RELAXATIONS[name]
    if name.startswith("sm_floor_"):
        return {"sm_floor": float(name.removeprefix("sm_floor_"))}
    raise SystemExit(f"unknown relaxation {name!r}")


def relax_spec(name: str) -> dict:
    """One relaxation, or several composed with `+`.

    Composition exists because the corners this study set out to price are only
    reachable in the GREEDY state — `dihedral_polyhedral2` and
    `printed_mass_x1.10` converge in under three minutes at the declared
    incumbent prop and have no design at all under the adopted one (§5c). So
    pricing a lever against them means applying `prop_12x10` AND the lever,
    which a single-relaxation cell cannot express:

        --relax prop_12x10+sm_floor_0.05

    Order matters and is left-to-right, so a later term wins a key an earlier
    one also sets. Nothing composes that way today; it is defined rather than
    left to dict ordering because the day it does happen, silently taking one of
    the two would be a cell whose label does not describe what it solved.
    """
    merged: dict = {}
    for part in name.split("+"):
        spec = _one_relax_spec(part)
        merged["set"] = {**merged.get("set", {}), **spec.get("set", {})}
        for k, v in spec.items():
            if k != "set":
                merged[k] = v
    if not merged["set"]:
        del merged["set"]
    return merged


# --- the record ------------------------------------------------------------

def load_cells() -> dict[str, dict]:
    """Every cell measured so far, keyed `member|relax`. Last write wins."""
    if not CELLS.exists():
        return {}
    out = {}
    for line in CELLS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        out[f"{rec['member']}|{rec['relax']}"] = rec
    return out


def append_cell(rec: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with CELLS.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def converged(rec: dict) -> bool:
    return rec.get("status") == "converged"


# --- one cell --------------------------------------------------------------

def run_cell(args) -> dict:
    sys.path.insert(0, str(REPO / "src"))
    from planeopt import solve as S
    from planeopt.cli import load_aircraft, load_mission

    aircraft, _ = load_aircraft(REPO / "aircraft" / args.aircraft)
    mission, _ = load_mission(REPO / "missions" / args.mission)

    mem, rel = member_spec(args.member), relax_spec(args.relax)

    # Relaxation first, member second: a member and a relaxation may name the
    # same attribute (they do not today), and the MEMBER is the thing being
    # measured, so it has to win.
    for attr, value in {**rel.get("set", {}), **mem.get("set", {})}.items():
        if not hasattr(aircraft, attr):
            raise SystemExit(f"{args.aircraft} has no attribute {attr!r}")
        current = getattr(aircraft, attr)
        setattr(aircraft, attr, type(current)(value)
                if isinstance(current, (int, float)) and not isinstance(current, bool)
                else value)
    if "sm_floor" in rel:
        lo, hi = mission.static_margin_range
        mission = dataclasses.replace(
            mission, static_margin_range=(float(rel["sm_floor"]), hi)
        )

    kw = dict(mem.get("kw", {}))
    t0 = time.monotonic()
    results = S._solve_many(
        aircraft, mission, [(args.member, kw)], parallel=1,
        label=f"{args.member} @ {args.relax}",
        timeout_min=args.timeout_min, max_iter=args.max_iter,
    )
    r = results[args.member]

    rec = {
        "member": args.member,
        "relax": args.relax,
        "aircraft": args.aircraft,
        "mission": args.mission,
        "timeout_min": args.timeout_min,
        "max_iter": args.max_iter,
        "sm_range": list(mission.static_margin_range),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip(),
        "solve_minutes": r.get("solve_minutes"),
        "peak_rss_gb": r.get("peak_rss_gb"),
        "wall_minutes": round((time.monotonic() - t0) / 60.0, 2),
    }
    if "failed" in r:
        rec.update({
            "status": "failed",
            "return_status": r.get("return_status"),
            "iter_count": r.get("iter_count"),
            "failed": r.get("failed"),
            "violations": r.get("violations"),
            "convergence": r.get("convergence"),
        })
    else:
        # A `--max-iter 3` smoke solve RETURNS a point rather than raising
        # (solve._solve_nlp harvests the last iterate on purpose), and that
        # point is not feasible and not an optimum. Calling it "converged"
        # would put exactly the false claim FINDINGS 24.2 was written about
        # into this tool's own record, where nothing downstream would catch it.
        truncated = bool(r.get("iteration_truncated"))
        rec.update({
            "status": "truncated" if truncated else "converged",
            "iteration_truncated": truncated,
            "return_status": r.get("return_status"),
            "iter_count": r.get("iter_count"),
            "objective_value": r["objective_value"],
            "static_margin": r["static_margin"],
            "auw_kg": r["auw_kg"],
            "V_ms": r["V_ms"],
            # `screen_discrete` re-solves the powertrain at the incumbent's
            # (V, thrust), so a record without `drag_n` cannot be screened
            # against — and the omission only shows up as a KeyError hours
            # later, once the solving is done and the cell is unrepeatable
            # without paying for it again. Which is exactly what happened.
            "drag_n": r["drag_n"],
            "J": r.get("J"),
            "rpm": r.get("rpm"),
            "P_elec_w": r.get("P_elec_w"),
            "deflection_deg": r["deflection_deg"],
            "dv": r["dv"],
            "active_bounds": r.get("active_bounds"),
            "dv_bounds": r.get("dv_bounds"),
        })
    append_cell(rec)
    return rec


def spawn_cell(member: str, relax: str, timeout_min: float, args,
               force: bool = False) -> dict:
    """One cell in its own process — see the module docstring on why."""
    key = f"{member}|{relax}"
    done = load_cells().get(key)
    if done is not None and not (force or args.force):
        print(f"  {key}: already measured ({done['status']})", flush=True)
        return done
    print(f"  {key}: solving (budget {timeout_min:g} min)...", flush=True)
    cmd = [
        sys.executable, str(Path(__file__).resolve()), "cell",
        "--member", member, "--relax", relax,
        "--aircraft", args.aircraft, "--mission", args.mission,
        "--timeout-min", str(timeout_min), "--max-iter", str(args.max_iter),
    ]
    proc = subprocess.run(cmd, cwd=REPO)
    rec = load_cells().get(key)
    if rec is None:
        # The child died without recording — OOM killer is the likely cause on a
        # 16 GB box, and a silent hole in the matrix would read as "not run yet"
        # forever. Write the hole down.
        rec = {
            "member": member, "relax": relax, "status": "crashed",
            "failed": f"cell process exited {proc.returncode} without recording",
            "timeout_min": timeout_min,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        append_cell(rec)
    verdict = rec.get("status")
    if verdict in ("converged", "truncated"):
        print(f"    -> {verdict} {rec['objective_value']:.3f} in "
              f"{rec.get('solve_minutes')} min, SM {rec['static_margin']:.4f}",
              flush=True)
    else:
        print(f"    -> {verdict}: {rec.get('return_status') or rec.get('failed')}",
              flush=True)
    return rec


# --- the plan --------------------------------------------------------------

#: The three readings `solve._convergence_trace` can produce, keyed by a phrase
#: from each. Matched on TEXT because the numeric rule that produces them lives
#: in `solve.py` and re-deriving it here would give this tool a second opinion
#: that could silently drift from the run's. The cost of that coupling is that
#: a reworded reading stops matching — so an unmatched reading SAYS SO rather
#: than being folded into "unknown", which is how a diagnostic goes quiet.
_TRACE_READINGS = {
    "dual blow-up": "stuck",
    "plateau short of feasible": "stuck",
    "still converging": "cutoff",
}


def stuck_or_cutoff(rec: dict) -> str:
    """Read the three-way verdict `_convergence_trace` recorded, if it did.

    A member the trace calls CUT OFF was still making progress when the budget
    ran out, so a short baseline is the wrong measurement for it and it gets the
    full ceiling. One the trace calls STUCK has already been shown (14.5.7) not
    to benefit from more clock.
    """
    reading = str((rec.get("convergence") or {}).get("reading") or "")
    if not reading:
        return "unknown"
    for phrase, verdict in _TRACE_READINGS.items():
        if phrase in reading:
            return verdict
    print(f"    WARNING: solve._convergence_trace returned a reading this tool "
          f"does not recognise, so it cannot tell stuck from cut off: "
          f"{reading!r}. Update _TRACE_READINGS.", flush=True)
    return "unknown"


def confirm_baseline(name: str, args, budget_left: float) -> dict:
    """Measure one member at the shipped caps, at the short baseline budget.

    A member the convergence trace calls CUT OFF was still making progress, so
    the short budget is the wrong measurement for it and it is re-run at the
    full ceiling before being written down as a corner. Only a STUCK verdict
    licenses the short budget, and that licence is 14.5.7's.
    """
    rec = spawn_cell(name, "none", args.baseline_timeout_min, args)
    if (rec.get("status") == "failed"
            and stuck_or_cutoff(rec) == "cutoff"
            and args.timeout_min > args.baseline_timeout_min
            and budget_left > args.timeout_min):
        print(f"    (trace says CUT OFF, not stuck — re-running at "
              f"{args.timeout_min:g} min)", flush=True)
        rec = spawn_cell(name, "none", args.timeout_min, args, force=True)
    return rec


def flatness_spans(nominal: dict, args) -> list[float]:
    """The spans `solve.flatness_sweep` would sample around this champion.

    Derived the way the sweep derives them rather than hard-coded, because the
    range is tied to the incumbent span (FINDINGS 14.5 / HANDOFF issue 0f) and a
    constant here would price a different set of members than the battery runs.
    """
    sys.path.insert(0, str(REPO / "src"))
    import numpy as np

    from planeopt import solve as S
    from planeopt.cli import load_aircraft

    aircraft, _ = load_aircraft(REPO / "aircraft" / args.aircraft)
    cap = float(aircraft.span_cap_m)
    # The span variable's own declared floor, as the solve recorded it. A
    # `fixed` value outside the box is an INVALID problem rather than an
    # infeasible one, so the sweep never goes under it (`flatness_sweep`).
    box = (nominal.get("dv_bounds") or {}).get("span")
    floor = float(box[0]) if box else 1.5
    lo = max(S.FLATNESS_SPAN_FRACTION * min(nominal["dv"]["span"], cap), floor)
    return sorted((round(float(s), 3) for s in np.linspace(lo, cap, 6)), reverse=True)


def drive(args) -> None:
    t_start = time.monotonic()

    def budget_left() -> float:
        return args.hours * 60 - (time.monotonic() - t_start) / 60.0

    def stage(title: str) -> None:
        print(f"\n=== {title}  ({budget_left():.0f} min of budget left) ===",
              flush=True)

    # --- A. reproduce the failures at the shipped caps ---------------------
    stage("A. baseline: the failing members at the caps as shipped")
    baseline = {}
    for name in MEMBERS:
        if budget_left() < args.baseline_timeout_min:
            print("  budget exhausted — stopping stage A here", flush=True)
            break
        baseline[name] = confirm_baseline(name, args, budget_left())

    # --- B. what the champion itself is worth under each cap ---------------
    stage("B. the price of each relaxation on the nominal design")
    for relax in RELAXATIONS:
        if relax == "none" or budget_left() < args.timeout_min:
            continue
        spawn_cell("nominal", relax, args.timeout_min, args)

    # --- C. is the converged rcv2 champion even airworthy? -----------------
    stage("C. re-evaluate the baseline champion — legal, or feasible fallback?")
    if converged(baseline.get("nominal", {})):
        reevaluate(baseline["nominal"], args)
    else:
        print("  skipped: the nominal member did not converge, so there is no "
              "champion to re-evaluate", flush=True)

    # --- D. does each relaxation unstick each corner? ----------------------
    stage("D. every stuck corner against every relaxation")
    stuck = [n for n, r in baseline.items()
             if n != "nominal" and r.get("status") != "converged"]
    print(f"  stuck corners: {', '.join(stuck) or 'none'}", flush=True)
    for name in stuck:
        for relax in RELAXATIONS:
            if relax == "none":
                continue
            if budget_left() < args.timeout_min:
                print("  budget exhausted — stopping stage D here", flush=True)
                return
            spawn_cell(name, relax, args.timeout_min, args)

    # --- E. the smallest static-margin give that still works ---------------
    stage("E. bisect the static-margin floor on whatever 0.05 unstuck")
    cells = load_cells()
    for name in stuck:
        if not converged(cells.get(f"{name}|sm_floor_0.05", {})):
            continue
        lo, hi = 0.05, 0.08  # hi = the shipped floor, known to fail
        for _ in range(args.bisect_steps):
            if budget_left() < args.timeout_min:
                print("  budget exhausted — stopping stage E here", flush=True)
                return
            mid = round((lo + hi) / 2, 4)
            if converged(spawn_cell(name, f"sm_floor_{mid}", args.timeout_min, args)):
                lo = mid
            else:
                hi = mid
        print(f"  {name}: converges at a floor of {lo:g}, not at {hi:g}", flush=True)

    # --- F. the flatness spans, last because they are sensitivities --------
    #
    # Four of the ten lost members were flatness spans, so this is a real share
    # of the wasted 69% — but the sweep answers "how flat is the optimum", and
    # the studies answer "which aeroplane", which is the decision the battery
    # exists to serve. So it goes after, and it is the stage the budget is
    # allowed to eat.
    stage("F. the flatness spans, at the caps and then relaxed")
    if not args.flatness:
        print("  skipped: --no-flatness", flush=True)
        return
    if not converged(baseline.get("nominal", {})):
        print("  skipped: the sweep's range is tied to the champion's span, "
              "and the nominal member did not converge", flush=True)
        return
    spans = flatness_spans(baseline["nominal"], args)
    print(f"  spans: {', '.join(format(s, 'g') for s in spans)}", flush=True)
    stuck_spans = []
    for span in spans:
        if budget_left() < args.baseline_timeout_min:
            print("  budget exhausted — stopping stage F here", flush=True)
            return
        name = f"flatness_{span:g}"
        if not converged(confirm_baseline(name, args, budget_left())):
            stuck_spans.append(name)
    for name in stuck_spans:
        for relax in RELAXATIONS:
            if relax == "none":
                continue
            if budget_left() < args.timeout_min:
                print("  budget exhausted — stopping stage F here", flush=True)
                return
            spawn_cell(name, relax, args.timeout_min, args)

    stage("done")


def reevaluate(nominal: dict, args) -> None:
    """Run the numeric re-evaluation on a converged champion's design vector.

    This is the cheap half of the question: `solve.run` sweeps speeds with no
    NLP at all, and it is the ONLY thing that produces `candidates_source` —
    the flag FINDINGS section 28 added so a champion with no legal operating
    point anywhere in its sweep cannot be reported in the same voice as a legal
    one. If it comes back `feasible_fallback` here, the caps are the second
    problem and airworthiness is the first.
    """
    sys.path.insert(0, str(REPO / "src"))
    from planeopt import solve as S
    from planeopt.cli import load_aircraft, load_mission

    aircraft, ac_file = load_aircraft(REPO / "aircraft" / args.aircraft)
    mission, ms_file = load_mission(REPO / "missions" / args.mission)
    result, run_dir = S.run(
        aircraft, mission, OUT / "reeval", input_files=[ac_file, ms_file],
        dv=nominal["dv"],
    )
    d = result.diagnostics
    rec = {
        "member": "nominal", "relax": "none:reeval", "status": "reevaluated",
        "run_dir": str(run_dir),
        "candidates_source": d.get("candidates_source"),
        # The broken rules with BOTH numbers, under the name `solve.run` gives
        # them. `rule_violations` is the FUNCTION that computes this; the
        # diagnostic it lands in is `reported_point_violations`, and reading the
        # wrong one returns None silently — which reads as "nothing violated".
        "reported_point_violations": d.get("reported_point_violations"),
        "airworthiness_price": d.get("airworthiness_price"),
        # notes[0] is where FINDINGS 28 puts the fallback statement, ahead of
        # every standing caveat, so it is the one line to carry forward.
        "note_zero": (result.notes or [None])[0],
        "objective_value": result.performance.get("best", {}).get("objective_value"),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    append_cell(rec)
    print(f"  candidates_source: {rec['candidates_source']}", flush=True)
    print(f"  {rec['note_zero']}", flush=True)
    for v in rec["reported_point_violations"] or []:
        print(f"    violates {v}", flush=True)
    print(f"  {run_dir}", flush=True)


# --- reporting -------------------------------------------------------------

def screen(args) -> None:
    """Reproduce the battery's greedy first step: which prop it would adopt.

    A study member in a battery does NOT carry the configuration it declares —
    the studies run greedily, each with the previous studies' adopted values. So
    a `tail_conventional` cell measured here against the incumbent prop and a
    `tail_conventional` member in a battery are the same label on two different
    aeroplanes, and that gap is the one caveat this study could not close by
    argument.

    Closing it is cheap because `solve.screen_discrete` holds the airframe fixed
    and re-solves only the powertrain — seconds per candidate, no NLP at all.
    What it needs is the run's OWN shadow price in objective units per gram,
    which is why `mass_bump` is a member: without it the screen is biased toward
    big propellers, the defect that held the diameter cap at 11 in until
    2026-07-30.

    This is a SHORTLISTER and never a verdict — the same caveat `screen_discrete`
    carries, and this study measured its size directly: the 20 g shadow price
    predicts +13.6 min for the 192 g payload step and the truth is +7.9.
    """
    sys.path.insert(0, str(REPO / "src"))
    from planeopt import solve as S
    from planeopt.cli import load_aircraft, load_mission

    cells = load_cells()
    champ = cells.get("nominal|none")
    bump = cells.get("mass_bump|none")
    if champ is None or champ.get("status") != "converged":
        raise SystemExit("no converged `nominal|none` cell to screen at — run it first")
    shadow = None
    if bump is not None and bump.get("status") == "converged":
        shadow = (bump["objective_value"] - champ["objective_value"]) / 20.0
    else:
        print("WARNING: no converged `mass_bump|none` cell, so the screen runs "
              "with NO shadow price and is biased toward big propellers "
              "(solve.screen_discrete). Run that member for a real ranking.")

    aircraft, _ = load_aircraft(REPO / "aircraft" / args.aircraft)
    mission, _ = load_mission(REPO / "missions" / args.mission)
    cands = [c for c in aircraft.discrete_options["prop_choice"]
             if c != aircraft.prop_choice]
    top_n = (getattr(aircraft, "discrete_screen", None) or {}).get("prop_choice", 4)
    result = S.screen_discrete(
        aircraft, mission, "prop_choice", cands, champ, top_n, shadow,
    )
    print(f"\nincumbent {aircraft.prop_choice}, {len(cands)} candidates, "
          f"shadow price {shadow if shadow is None else round(shadow, 5)} per gram")
    print(f"shortlist: {', '.join(result['shortlist'])}\n")
    for r in result["ranking"][:10]:
        print(f"  {r['candidate']:24s} {r['screened_objective']:8.3f}")
    if result["unreachable"]:
        print(f"\n{len(result['unreachable'])} candidate(s) unreachable at this "
              f"operating point")
    append_cell({
        "member": "nominal", "relax": "none:prop_screen", "status": "screened",
        "shortlist": result["shortlist"],
        "ranking": result["ranking"][:10],
        "shadow_price_obj_per_gram": shadow,
        "incumbent": aircraft.prop_choice,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


#: A constraint label is `file.py:LINE opti.subject_to(...)`, and the LINE moves
#: whenever anything above it in the file moves — the ordering-row revert alone
#: shifted `equipment.py`'s packing row from 362 to 344. Tallying by label would
#: therefore split one row across commits and report two half-strength findings
#: where there is one strong one. The constraint TEXT is what is stable, so that
#: is the key; the file name rides along because two files could in principle
#: write the same expression.
_LABEL = re.compile(r"^(?P<file>[\w./-]+):(?P<line>\d+)\s+(?P<text>.*)$", re.S)


def miss_key(what: str) -> tuple[str, str]:
    m = _LABEL.match(what.strip())
    if not m:
        return ("?", what.strip()[:70])
    return (m["file"], " ".join(m["text"].split())[:70])


def misses(args) -> None:
    """Which CONSTRAINT blocks each failing cell, and which one blocks most.

    A converged/failed table is a scoreboard; this is the explanation. The
    study's standing prediction (§8) is that `usable_nose / motor["length"] >= 1`
    is the row that actually blocks this aeroplane — it was the closest miss in
    four independent corners while none of the four caps HANDOFF names as the
    remedy touches it. A tally either carries that or kills it.
    """
    cells = load_cells()
    failed = [r for r in cells.values()
              if r.get("status") == "failed" and r.get("violations")]
    if not failed:
        raise SystemExit("no failed cells with recorded violations yet")

    rows = []
    for r in sorted(failed, key=lambda r: (r["member"], r["relax"])):
        v = r["violations"][0]
        f, text = miss_key(v["what"])
        rows.append((r["member"], r["relax"], r.get("iter_count"), v["by"],
                     f, text, stuck_or_cutoff(r)))

    w_m = max(len(x[0]) for x in rows) + 2
    w_r = max(len(x[1]) for x in rows) + 2
    print("closest miss per failing cell\n")
    print("member".ljust(w_m) + "lever".ljust(w_r) + "iters   by         row")
    for m, rx, it, by, f, text, verdict in rows:
        mark = "" if verdict == "stuck" else f"   [{verdict.upper()} — not evidence]"
        print(f"{m.ljust(w_m)}{rx.ljust(w_r)}{str(it or '-'):>5}  "
              f"{by:.2e}  {f}: {text}{mark}")

    # ONLY stuck cells are counted. A cut-off cell's "closest miss" is a
    # snapshot of an iterate still descending — it says where the solve had got
    # to, not what stopped it — and this study has already been bitten once by
    # exactly that: the cells the machine slept through reported misses of
    # 2.6e-01 on a row that, measured awake, does not block them at all.
    counted = [r for r in rows if r[6] == "stuck"]
    skipped = len(rows) - len(counted)
    tally: dict[tuple[str, str], list[float]] = {}
    for _, _, _, by, f, text, _ in counted:
        tally.setdefault((f, text), []).append(by)
    print(f"\nrows ranked by how many cells they block "
          f"({len(counted)} stuck cells counted"
          f"{f'; {skipped} cut-off cell(s) excluded' if skipped else ''})")
    for (f, text), bys in sorted(tally.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(bys):2d} cell(s)  worst {max(bys):.2e}   {f}: {text}")


def report(args) -> None:
    cells = load_cells()
    if not cells:
        # The committed cells live under docs/, not in the untracked run
        # directory this writes to, so the bare command reads as "nothing has
        # ever been measured" on a fresh clone that ships four measured cells.
        committed = REPO / "docs" / "studies" / "rcv2_cap_pricing"
        hint = (
            f"\n  {committed / 'cells.jsonl'} DOES exist — read it with:"
            f"\n      PRICE_CAPS_OUT={committed.relative_to(REPO)} "
            f"uv run python tools/price_caps.py report"
            if (committed / "cells.jsonl").exists()
            else ""
        )
        raise SystemExit(f"nothing measured yet — {CELLS} is empty or absent{hint}")
    members = sorted({r["member"] for r in cells.values()})
    relaxes = sorted({r["relax"] for r in cells.values()})

    def render(rec: dict | None) -> str:
        if rec is None:
            return "-"
        if rec.get("status") == "converged":
            return f"{rec['objective_value']:.2f} ({rec.get('solve_minutes')}m)"
        if rec.get("status") == "truncated":
            return f"TRUNCATED@{rec.get('iter_count')}"
        if rec.get("status") == "reevaluated":
            return str(rec.get("candidates_source"))
        # `Maximum_WallTime_Exceeded` on its own is the least informative true
        # statement this tool can make: it is what a genuine corner and a
        # sleeping machine both report. The iteration count and the minutes
        # actually spent separate them, and the trace's own verdict names which
        # one it thinks it is.
        status = rec.get("return_status") or rec.get("status") or "?"
        short = "WallTime" if status == "Maximum_WallTime_Exceeded" else status[:12]
        verdict = stuck_or_cutoff(rec)
        return (f"{short} {rec.get('iter_count')}it/{rec.get('solve_minutes')}m"
                f"{'' if verdict == 'unknown' else ' ' + verdict}")

    grid = {(m, rx): render(cells.get(f"{m}|{rx}")) for m in members for rx in relaxes}
    # Sized to the widest thing actually in the table, so a cell can never run
    # into its neighbour and read as one word.
    width = max(len(m) for m in [*members, "member"]) + 2
    col = max(len(v) for v in [*grid.values(), *relaxes]) + 2

    print("objective (min) if converged, else the solver's verdict\n")
    print("a FAILED cell reports iterations and minutes, because the status "
          "alone cannot\ntell a corner from a cut-off: this study's one real "
          "corner burned 415 iterations\nand its whole 30-minute budget, while "
          "the cells the machine SLEPT through gave up\nat 15-75 iterations "
          "and reported the identical `Maximum_WallTime_Exceeded`.\n")
    print("member".ljust(width) + "".join(r.ljust(col) for r in relaxes))
    for m in members:
        print(m.ljust(width) + "".join(grid[(m, rx)].ljust(col) for rx in relaxes))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--aircraft", default="vtail_rcv2")
        p.add_argument("--mission", default="endurance_sample.py")
        p.add_argument("--max-iter", type=int, default=1000)
        p.add_argument("--force", action="store_true",
                       help="re-measure cells that are already recorded")

    c = sub.add_parser("cell", help="run one member x relaxation")
    common(c)
    c.add_argument("--member", required=True)
    c.add_argument("--relax", required=True)
    c.add_argument("--timeout-min", type=float, default=30.0)

    d = sub.add_parser("drive", help="run the whole plan, resumably")
    common(d)
    d.add_argument("--timeout-min", type=float, default=30.0,
                   help="ceiling for a pricing solve (the run default)")
    d.add_argument("--baseline-timeout-min", type=float, default=15.0,
                   help="ceiling for a baseline reproduction — shorter on the "
                        "evidence of FINDINGS 14.5.7; a member the convergence "
                        "trace calls CUT OFF is re-run at the full ceiling")
    d.add_argument("--hours", type=float, default=10.0,
                   help="stop starting new cells past this many hours")
    d.add_argument("--bisect-steps", type=int, default=2)
    d.add_argument("--flatness", action=argparse.BooleanOptionalAction, default=True,
                   help="also price the flatness sweep's spans (stage F, last)")

    r = sub.add_parser("report", help="print the matrix measured so far")
    common(r)

    ms = sub.add_parser(
        "misses",
        help="which constraint blocks each failing cell, and which blocks most",
    )
    common(ms)

    sc = sub.add_parser(
        "screen",
        help="which prop the battery's greedy chain would adopt (no NLP)",
    )
    common(sc)

    args = ap.parse_args()
    os.chdir(REPO)
    if args.cmd == "cell":
        run_cell(args)
    elif args.cmd == "drive":
        drive(args)
    elif args.cmd == "screen":
        screen(args)
    elif args.cmd == "misses":
        misses(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
