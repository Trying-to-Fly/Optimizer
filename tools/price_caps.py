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
    # --- added 2026-08-07: the 20260807T061330 battery lost SIX members and
    # this list could express only three of them, so half the evidence could not
    # be re-run at all. The two below are plain attribute flips and a kwarg;
    # they were missing because the study was scoped from the 2026-08-06
    # battery's losses, and that one lost a different set.
    "winglet_off": {"set": {"winglet": False}},
    "winglet_continuous_cant": {
        # exactly what `solve.optimize`'s `_wl_prep` does for this member
        "set": {"winglet": False, "tip_dihedral_max_deg": 88.0},
    },
    "mass_bump": {"kw": {"extra_mass_kg": 0.020}},
    # `flatness_<span>` is accepted dynamically — the sweep's spans depend on the
    # champion's span, which is not known until the nominal member converges.
    # `multistart_perturbed_<n>` likewise, via `solve.multistart_inits`.
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
}


def member_spec(name: str, aircraft=None) -> dict:
    if name in MEMBERS:
        return MEMBERS[name]
    if name.startswith("flatness_"):
        return {"kw": {"fixed": {"span": float(name.removeprefix("flatness_"))}}}
    if name.startswith("multistart_perturbed_"):
        # Asked of `solve` rather than reimplemented here. The draws are seeded,
        # so replaying them locally would work today and desynchronize silently
        # the first time that block is edited — and the draw COUNT per start
        # depends on `aircraft.winglet`, so even the sequence is not a constant.
        from planeopt import solve as S

        index = int(name.removeprefix("multistart_perturbed_"))
        starts = S.multistart_inits(aircraft, index + 1)
        return {"kw": {"inits": starts[index]}}
    raise SystemExit(f"unknown member {name!r}")


def relax_spec(name: str) -> dict:
    if name in RELAXATIONS:
        return RELAXATIONS[name]
    if name.startswith("sm_floor_"):
        return {"sm_floor": float(name.removeprefix("sm_floor_"))}
    raise SystemExit(f"unknown relaxation {name!r}")


# --- the record ------------------------------------------------------------

def _head_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()


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

    mem, rel = member_spec(args.member, aircraft), relax_spec(args.relax)

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
        "commit": _head_commit(),
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
        # Recorded here too. Every other cell carries it and this one did not,
        # so the single row that says whether the design is AIRWORTHY was the
        # one row whose tree could not be identified.
        "commit": _head_commit(),
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
    width = max(len(m) for m in members) + 2
    print("objective (min) if converged, else the solver's verdict\n")
    print("member".ljust(width) + "".join(r.ljust(22) for r in relaxes))
    for m in members:
        row = m.ljust(width)
        for rx in relaxes:
            rec = cells.get(f"{m}|{rx}")
            if rec is None:
                cell = "-"
            elif rec.get("status") == "converged":
                cell = f"{rec['objective_value']:.2f} ({rec.get('solve_minutes')}m)"
            elif rec.get("status") == "truncated":
                cell = f"TRUNCATED@{rec.get('iter_count')}"
            elif rec.get("status") == "reevaluated":
                cell = str(rec.get("candidates_source"))
            else:
                cell = (rec.get("return_status") or rec.get("status") or "?")[:20]
            row += cell.ljust(22)
        print(row)
    _print_provenance(cells)


def _print_provenance(cells: dict[str, dict]) -> None:
    """Which TREE each number came from, and a warning when they differ.

    The matrix invites exactly one comparison — read a row, subtract, call the
    difference the price of a cap — and that subtraction is only valid within one
    tree. This project's standing warning is that a model change moves every
    objective with it (the vortex core moved the 2.0 m nominal 120.12168 ->
    119.93422; the afterbody term and the motor-fit rows moved everything again),
    so two cells measured either side of one are not comparable at all.

    On 2026-08-07 this file held cells from SIX commits and the report said
    nothing, printing them as one table. Cheap to state, and impossible to
    recover afterwards if a cell is read and acted on.
    """
    by_commit: dict[str, list[str]] = {}
    for key, rec in sorted(cells.items()):
        by_commit.setdefault(rec.get("commit") or "UNRECORDED", []).append(key)
    print()
    if len(by_commit) == 1:
        only = next(iter(by_commit))
        print(f"all cells measured at {only}")
        return
    print(f"!! {len(by_commit)} TREES IN THIS TABLE. A difference across two of "
          f"them is not a price")
    print("   until the trees are shown to be solution-preserving — a model change "
          "moves EVERY")
    print("   objective with it. Same tree: subtract freely. Different trees: check "
          "first, and")
    print("   the cheap check is whether a shared cell reproduces across them "
          "(`nominal|none`).")
    for commit, keys in sorted(by_commit.items(), key=lambda kv: -len(kv[1])):
        print(f"   {commit:12} {len(keys):>2} cell(s): {', '.join(keys)[:96]}")


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

    args = ap.parse_args()
    os.chdir(REPO)
    if args.cmd == "cell":
        run_cell(args)
    elif args.cmd == "drive":
        drive(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
