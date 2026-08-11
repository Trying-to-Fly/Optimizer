"""Is the static margin's sign flip the AIRFRAME, or LiftingLine's panel count?

FINDINGS §37.5-37.7 leave the rcv2 champion unbuildable for one reason, and it
is not the one it looks like. The two aerodynamic methods AGREE about the margin
— at 9.5 m/s LiftingLine says 0.0572 and the independent VLM says 0.0530 — and
the NLP's 0.0800 is simply read at a different cruise speed, on an aeroplane
whose margin runs from +0.089 at 10 m/s down through zero by 14.5.

What blocks every candidate is `sm_sign_consistent = False`. Points at 10.0,
10.5 and 11.0 m/s carry margins comfortably inside the declared [0.08, 0.15] and
are rejected anyway, because the LOCAL dCm/dCL changes sign inside the +/-2 deg
window the margin is regressed over. The only sign-consistent point in the sweep
is 14.5 m/s, where the margin is negative.

`aero.py` already wrote down the discriminating test:

    (a) Cm(alpha) really is that nonlinear on this airframe, or
    (b) LiftingLine's Cm is noisy at 4 panels per section.
    ... Agreement between the two is evidence the nonlinearity is the
    AIRFRAME's; disagreement points at the discretization.

and the VLM cross-check already disagrees with LiftingLine about the SHAPE:
smooth and monotone (+0.053, +0.056, +0.059, +0.062, `sign_consistent: True`)
where LiftingLine flips (+0.198, +0.0016, **-0.0153**, +0.0375). That points at
(b), and FINDINGS §18 is the precedent — a 4-panel artefact once produced an
L/D of 889.

This settles it directly rather than by inference: the SAME champion, the SAME
alpha window, at rising spanwise resolution. If the flip is discretization it
converges away and the margin settles; if it is the airframe it survives
refinement. Run at BOTH the reported endurance peak (9.5 m/s, below the floor)
and a point the window would accept (10.5 m/s), because the question worth
answering is whether an in-window point can be certified, not just whether the
reported one moves.

No NLP, no battery: this is a handful of LiftingLine evaluations against a
frozen design vector read from a run artifact.

Usage:
    .venv/bin/python tools/bughunt/sm_resolution_experiment.py <run_dir> [out.json]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import planeopt  # noqa: F401 — must precede numpy (README: BLAS pinning)
from planeopt import aero, cli, massmodel, solve

#: Default is whatever AeroSandbox picks (`spanwise_resolution=None`), which is
#: what every run to date has used. The rest bracket it upward; the question is
#: whether the answer stops moving.
RESOLUTIONS = (None, 8, 12, 16, 24)

#: The reported endurance peak, and a speed whose margin sits inside the
#: declared window. If the flip is an artefact, the second becomes certifiable.
SPEEDS = (9.5, 10.5)

#: THE CONTROL THE RESOLUTION SWEEP CANNOT PROVIDE, and the one that answered
#: this. `sm_local_slopes` are two-point differences over `SM_DIAGNOSTIC_OFFSETS`
#: — a 1 deg step. Refining panels cannot fix a difference quotient whose
#: numerator is small: at 9.5 m/s over a +/-1 deg window Cm moves by 0.0024
#: total. Varying the STEP at fixed panel count separates "Cm is genuinely
#: non-monotone" from "this difference is below the noise floor".
ALPHA_STEPS = (0.5, 1.0, 2.0)

#: Panel count for the step sweep: converged per the resolution sweep, so any
#: step sensitivity found there is not panel noise wearing a different hat.
STEP_SWEEP_RESOLUTION = 16


def evaluate(airplane, V, alpha0, x_cg, c_ref, bodies, res):
    t0 = time.monotonic()
    r = aero.static_margin(airplane, V, x_cg, c_ref, alpha0=alpha0,
                           bodies=bodies, spanwise_resolution=res)
    slopes = [s["sm_local"] for s in r["sm_local_slopes"]]
    return {
        "spanwise_resolution": res,
        "static_margin": r["static_margin"],
        "x_np_m": r["x_np_m"],
        "sm_local_slopes": slopes,
        # The pathology, stated the way the airworthiness rule states it: a
        # positive reported margin whose local slope goes negative somewhere in
        # the window it was regressed over.
        "sign_consistent": solve.sm_sign_flip(r) is None,
        "min_local_slope": min(slopes),
        "seconds": round(time.monotonic() - t0, 1),
    }


def main() -> None:
    # `--set attr=value` restores the discrete choices the battery adopted, which
    # the design vector does not carry. Values parse as JSON so `false`, numbers
    # and strings all work:  --set winglet=false --set prop_choice='"ancf_12x10"'
    positional, overrides, expecting = [], [], False
    for arg in sys.argv[1:]:
        if expecting:
            overrides.append(arg)
            expecting = False
        elif arg == "--set":
            expecting = True
        elif arg.startswith("--set="):
            overrides.append(arg.removeprefix("--set="))
        else:
            positional.append(arg)
    if expecting:
        raise SystemExit("--set needs attr=value")

    run_dir = Path(positional[0])
    out_path = Path(positional[1]) if len(positional) > 1 else Path(
        "docs/studies/sm_resolution/sm_resolution.json")
    run = json.loads((run_dir / "run.json").read_text())

    ac, _ = cli.load_aircraft(Path("aircraft/vtail_rcv2"))
    for item in overrides:
        attr, _, raw = item.partition("=")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        setattr(ac, attr, value)
        print(f"set {attr} = {value!r}", flush=True)

    dv = run["design_vector"]
    airplane = ac.geometry(dv)
    bodies = ac.parasite_bodies(dv)
    totals = massmodel.totals(massmodel.build(ac, airplane, dv)[0])

    # A `design_vector` carries the CONTINUOUS variables only. The discrete
    # choices a battery adopts — prop, tail type, fuselage topology, and whether
    # the winglet survived its study — live on the aircraft object, and
    # `load_aircraft` hands back the DECLARED defaults instead. Rebuilding from
    # dv alone therefore reconstructs a different aeroplane, silently.
    #
    # That is not hypothetical: FINDINGS §38.2's absolute margins were measured
    # this way and were wrong. The declared default is `winglet = True` and
    # `prop_choice = ancf_11x6`; the 2026-08-11 champion had the winglet
    # REJECTED and `ancf_12x10` adopted, so the rebuild carried 42 g of winglet
    # the champion does not have, 2.9 mm aft — worth 0.0123 of static margin,
    # against a window the design clears by 0.0038.
    #
    # Mass is the cheap tell, so it is checked rather than assumed. Anything
    # that moves the CG invalidates every number below it.
    for field, mine in (("auw_kg", totals["auw_kg"]), ("x_cg_m", totals["x_cg_m"])):
        theirs = (run.get("masses") or {}).get(field)
        if theirs is not None and abs(mine - theirs) > 1e-6:
            raise SystemExit(
                f"rebuilt aeroplane does not match the artifact: {field} "
                f"{mine:.6f} against {theirs:.6f}. The adopted discrete choices "
                "are missing — set them on the aircraft before measuring, or "
                "every static margin here is for a different aircraft."
            )
    # `c_ref` is the AIRPLANE's, not the aircraft definition's — same source
    # `solve` uses for the re-evaluation (`aero.static_margin(..., airplane.c_ref)`).
    x_cg, c_ref = totals["x_cg_m"], airplane.c_ref

    best = run["performance"]["best"]
    by_speed = {float(s["V_ms"]): s for s in run["performance"].get("sweep") or []
                if s.get("alpha_deg") is not None}

    study = {
        "run": run_dir.name,
        "x_cg_m": x_cg, "c_ref_m": c_ref,
        "static_margin_range": run["constraints"]["static_margin_range"],
        "reported": {"V_ms": best["V_ms"], "alpha_deg": best["alpha_deg"],
                     "static_margin": best.get("static_margin")},
        "points": {},
    }

    for V in SPEEDS:
        point = by_speed.get(V)
        if point is None:
            print(f"!! {V} m/s not in the sweep; skipping", flush=True)
            continue
        alpha0 = float(point["alpha_deg"])
        print(f"\n=== V = {V} m/s, trim alpha = {alpha0:.3f} deg", flush=True)
        rows = []
        for res in RESOLUTIONS:
            row = evaluate(airplane, V, alpha0, x_cg, c_ref, bodies, res)
            rows.append(row)
            slopes = "  ".join(f"{s:+.4f}" for s in row["sm_local_slopes"])
            print(f"  res={str(res):>5}  SM={row['static_margin']:+.5f}  "
                  f"sign_ok={str(row['sign_consistent']):>5}  "
                  f"slopes [{slopes}]  ({row['seconds']}s)", flush=True)
        steps = []
        for step in ALPHA_STEPS:
            alphas = [alpha0 + k * step for k in (-2, -1, 0, 1, 2)]
            got = {a: aero._run_ll(airplane, V, a, 0.0, x_cg,
                                   spanwise_resolution=STEP_SWEEP_RESOLUTION)
                   for a in alphas}
            cl = [float(got[a]["CL"]) for a in alphas]
            cm = [float(got[a]["Cm"]) for a in alphas]
            sl = [-(cm[i + 1] - cm[i]) / (cl[i + 1] - cl[i]) for i in range(4)]
            steps.append({"alpha_step_deg": step, "sm_local_slopes": sl,
                          "cm_span": max(cm) - min(cm),
                          "sign_consistent": all(s > 0 for s in sl)})
            print(f"  step={step:>4} deg  slopes ["
                  + "  ".join(f"{s:+.4f}" for s in sl)
                  + f"]  Cm spans {max(cm) - min(cm):.5f}", flush=True)
        study["points"][str(V)] = {"alpha_deg": alpha0, "rows": rows,
                                   "alpha_step_sweep": steps}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(solve._jsonable(study), indent=1) + "\n")
    print(f"\nwrote {out_path}")

    # The verdict, in the terms aero.py posed the question.
    for V, blk in study["points"].items():
        rows = blk["rows"]
        flips = [r["spanwise_resolution"] for r in rows if not r["sign_consistent"]]
        sms = [r["static_margin"] for r in rows]
        spread = max(sms) - min(sms)
        print(f"\nV={V}: margin {min(sms):+.5f}..{max(sms):+.5f} (spread {spread:.5f})")
        if not flips:
            # Since §38.6 `sm_sign_flip` requires the negative slope to exceed
            # its own uncertainty, so "no flip" now means "none that is
            # distinguishable from noise" — NOT that refinement removed one.
            # The raw slopes above still show negatives; read those for shape.
            print("  no SIGNIFICANT flip at any resolution (the bare slopes may "
                  "still go negative — they are inside their error bars)")
        elif len(flips) == len(rows):
            print("  sign flip survives every resolution — NOT panel noise")
        else:
            print(f"  flip present at {flips} and absent at the rest — "
                  "it CONVERGES AWAY, so the coarse mesh was the problem")
        steps = blk["alpha_step_sweep"]
        consistent = [s["alpha_step_deg"] for s in steps if s["sign_consistent"]]
        if consistent and len(consistent) < len(steps):
            print(f"  ...but it VANISHES at alpha steps {consistent} and appears at "
                  "the others: the local-slope check is a difference quotient below "
                  "its own noise floor, not a property of the aeroplane")


if __name__ == "__main__":
    main()
