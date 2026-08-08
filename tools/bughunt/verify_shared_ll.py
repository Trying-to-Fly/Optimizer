"""Is ONE shared lifting-line Function equivalent to the FOUR inline graphs?

`solve.py` builds four LiftingLine graphs per member, and they are NOT four
copies of one thing:

    solve.py  trim run   -> airplane.with_control_deflections({pitch: defl})
    solve.py  3 SM runs  -> the UNDEFLECTED airplane, at alpha + SM_ALPHA_OFFSETS

Collapsing them into one `casadi.Function` is a large win on graph construction
— that is the change this exists to check — but it is only CORRECT if the
deflection stayed an INPUT to that function rather than being baked in or
dropped. Get that wrong and the static-margin row moves by ~0.17, which is 2.5x
the whole mission window, and the solve STILL CONVERGES and still reports a
margin inside its bounds. That is FINDINGS section 18's shape exactly: a plausible
aeroplane that is not the one you asked for.

WHAT THIS SETTLES, AND WHAT IT DOES NOT

Settles: numerical equivalence. Geometry is held NUMERIC and only alpha and the
deflection are symbolic, which is precisely the axis the refactor changes, so
the comparison is exact and costs seconds instead of a solve.

Does NOT settle: the speedup. With numeric geometry the four inline builds are
cheap numeric evaluations while the shared arm pays to build and compile a
symbolic graph, so the ratio here is meaningless and is not printed. In the real
member the geometry is symbolic too, which is what makes four builds expensive.
Time that in the NLP, not here.

Does NOT settle: that a converged champion is unchanged. Nothing truncated can.
Run both arms to convergence and compare objective, design vector and active set.

Usage:  uv run python tools/bughunt/verify_shared_ll.py [<run-dir>] [<aircraft-dir>]

Defaults to the newest run under `runs/` and `aircraft/vtail_sample`. The run is
read only for an operating point (V, alpha, deflection, x_cg, design vector) —
any converged or evaluated run will do.
"""
import json
import sys
from pathlib import Path

import planeopt  # noqa: F401  — must precede numpy (README: BLAS pinning)
import aerosandbox as asb
import casadi as cas

from planeopt import aero, cli

#: Machine precision with room for CasADi's own reassociation. The observed
#: worst row on `vtail_sample` is 1e-15; anything at 1e-12 is a different graph,
#: not rounding.
TOL = 1e-12

KEYS = ("CL", "Cm", "L", "D")


def newest_run(runs_root: Path) -> Path:
    runs = sorted(
        (p for p in runs_root.iterdir() if p.is_dir() and (p / "run.json").is_file()),
        key=lambda p: p.name, reverse=True,
    )
    if not runs:
        sys.exit(f"no run with a run.json under {runs_root}")
    return runs[0]


run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_run(Path("runs"))
ac_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("aircraft/vtail_sample")

ac, _ = cli.load_aircraft(ac_dir)
data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
best = (data.get("performance") or {}).get("best") or {}

V = float(best["V_ms"])
ALPHA = float(best["alpha_deg"])
DEFL = float(best.get("deflection_deg") or 0.0)
X_CG = float((data.get("masses") or {})["x_cg_m"])
dv = data.get("design_vector") or None

airplane = ac.geometry(dv)
bodies = ac.parasite_bodies(dv)
S_REF, C_REF = float(airplane.s_ref), float(airplane.c_ref)
PITCH = getattr(ac, "pitch_control_name", "ruddervator")
OFFS = aero.SM_ALPHA_OFFSETS

print(f"operating point from {run_dir.name} on {ac_dir.name}")
print(f"  V={V:.4f} m/s  alpha={ALPHA:.4f} deg  deflection={DEFL:.4f} deg  x_cg={X_CG:.5f} m")
print(f"  SM window offsets {OFFS}, pitch control {PITCH!r}\n")


def ll(plane, alpha):
    """solve.py's construction verbatim — same core radius, same reference."""
    return asb.LiftingLine(
        airplane=plane,
        op_point=asb.OperatingPoint(velocity=V, alpha=alpha),
        xyz_ref=[X_CG, 0, 0],
        vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS,
    ).run()


def sm_of(sm_rows):
    """The static-margin constraint row, from three (CL, Cm) pairs."""
    return float(aero.static_margin_from_polar(
        [r["CL"] for r in sm_rows], [r["Cm"] for r in sm_rows],
        list(OFFS), bodies, S_REF, C_REF,
    ))


# --- A: four inline graphs, as solve.py does today -------------------------
a_rows = [{k: float(ll(airplane.with_control_deflections({PITCH: DEFL}), ALPHA)[k])
           for k in KEYS}]
a_rows += [{k: float(r[k]) for k in KEYS}
           for r in (ll(airplane, ALPHA + o) for o in OFFS)]

# --- B: ONE Function of (alpha, defl), called four times -------------------
alpha_s, defl_s = cas.MX.sym("alpha"), cas.MX.sym("defl")
sym = ll(airplane.with_control_deflections({PITCH: defl_s}), alpha_s)
F = cas.Function("ll", [alpha_s, defl_s], [sym[k] for k in KEYS])
b_rows = [dict(zip(KEYS, [float(v) for v in F(a, d)]))
          for a, d in [(ALPHA, DEFL)] + [(ALPHA + o, 0.0) for o in OFFS]]

# --- compare ---------------------------------------------------------------
labels = ["trim run (deflected)"] + [f"SM run alpha{o:+.1f} (clean)" for o in OFFS]
print(f"{'evaluation':<28}{'':<4}{'four inline':>18}{'one shared':>18}{'error':>11}")
worst = 0.0
for label, ra, rb in zip(labels, a_rows, b_rows):
    for k in KEYS:
        va, vb = ra[k], rb[k]
        # Mixed abs/rel: the trim run's Cm is ~1e-19 BY CONSTRUCTION (it is the
        # trimmed point), so a relative error against zero is meaningless and
        # reports a spurious 1e-4.
        err = abs(vb - va) / max(abs(va), 1.0)
        worst = max(worst, err)
        print(f"{label:<28}{k:<4}{va:>18.10f}{vb:>18.10f}{err:>11.2e}")

sm_a, sm_b = sm_of(a_rows[1:]), sm_of(b_rows[1:])
worst = max(worst, abs(sm_b - sm_a))
print(f"\n{'STATIC MARGIN constraint':<28}{'SM':<4}{sm_a:>18.10f}{sm_b:>18.10f}"
      f"{abs(sm_b - sm_a):>11.2e}")
print(f"{'TRIM residual':<28}{'Cm':<4}{a_rows[0]['Cm']:>18.10f}{b_rows[0]['Cm']:>18.10f}"
      f"{abs(b_rows[0]['Cm'] - a_rows[0]['Cm']):>11.2e}")

ok = worst < TOL
print(f"\nworst error: {worst:.3e}  (tolerance {TOL:.0e})")
print("VERDICT:", "EQUIVALENT — sharing the graph does not change the physics"
      if ok else "*** THEY DISAGREE — the shared function is not the same model ***")

# --- price the trap, through the shared function itself --------------------
leaked = [dict(zip(KEYS, [float(v) for v in F(ALPHA + o, DEFL)])) for o in OFFS]
sm_leaked = sm_of(leaked)
lo, hi = ((data.get("constraints") or {}).get("static_margin_range") or [0.08, 0.15])[:2]
window = float(hi) - float(lo)
print("\nWhat a deflection leak would cost, if the SM rows were called with the"
      "\ntrim deflection instead of zero:")
print(f"  SM correct {sm_a:+.6f}   SM leaked {sm_leaked:+.6f}   "
      f"delta {sm_leaked - sm_a:+.6f}")
print(f"  the mission window is {lo}..{hi} ({window:.3f} wide), so that is "
      f"{abs(sm_leaked - sm_a) / window * 100:.0f}% of it")
print("  both states CONVERGE, so nothing else in the pipeline reports this.")
print("\nAfter a real run, the same leak shows as `constraints.static_margin_gap`:"
      "\n  ~1e-7 normal   ~2e-3 a legitimate alpha difference   ~1e-1 the leak")

sys.exit(0 if ok else 1)
