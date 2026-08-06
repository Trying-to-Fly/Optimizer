"""Name the linearly-dependent constraints behind a non-converging solve.

`inf_du` diverging while `inf_pr` stays small says the active constraint
gradients have gone linearly dependent, so no Lagrange multipliers exist and
there is nothing for IPOPT to converge to. This finds WHICH rows: run a short
solve to reach the degenerate region, take the last iterate, assemble the
Jacobian of the near-active rows, and read its smallest singular values. The
null-space direction names the duplicated rows, with source file and line.

    uv run python tools/degeneracy.py --span 1.5        # a flatness member
    uv run python tools/degeneracy.py --mount pusher    # a discrete-study member
    uv run python tools/degeneracy.py                   # the nominal solve

    # any aircraft package, and any discrete attribute a study sets:
    uv run python tools/degeneracy.py --aircraft vtail_rcv2 --set tail_type=ttail

Found this way (2026-07-30, FINDINGS §14.5.3): the flatness sweep's first member
pins `span` at its own declared lower bound with an equality, so `span >= 1.5`
and `span == 1.5` are both active — the same constraint twice.

Costs one ~60-iteration solve (~10 min, ~13 GB) plus a symbolic Jacobian.
"""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERE = REPO / "runs" / "_diagnostics"
HERE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "src"))

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--aircraft", default="vtail_sample",
                help="aircraft package under aircraft/ (default: vtail_sample)")
ap.add_argument("--span", type=float, help="hold span at this value (a flatness member)")
ap.add_argument("--mount", help="motor_mount to study, e.g. pusher")
ap.add_argument("--set", action="append", default=[], metavar="ATTR=VALUE",
                help="set a discrete attribute before solving, e.g. tail_type=ttail; "
                     "repeatable. This is how a DISCRETE-STUDY member is reproduced, "
                     "and the reason the tool is not tied to one aircraft: a "
                     "degeneracy is a property of a model, and every aircraft "
                     "package here builds a different one.")
ap.add_argument("--printed-scale", type=float, default=1.0)
ap.add_argument("--iters", type=int, default=60,
                help="how far to run before inspecting the iterate")
args = ap.parse_args()

import aerosandbox as asb  # noqa: E402
import casadi as cas  # noqa: E402
import numpy as np  # noqa: E402

from planeopt import solve as S  # noqa: E402
from planeopt.cli import load_aircraft, load_mission  # noqa: E402

aircraft, _ = load_aircraft(REPO / "aircraft" / args.aircraft)
mission, _ = load_mission(REPO / "missions" / "endurance_sample.py")
if args.mount:
    aircraft.motor_mount = args.mount
for assignment in args.set:
    attr, _, raw = assignment.partition("=")
    if not hasattr(aircraft, attr):
        raise SystemExit(f"{args.aircraft} has no attribute {attr!r}")
    # match the declared type, so `--set tail_type=ttail` and
    # `--set span_cap_m=2.5` both do the right thing without a type flag
    current = getattr(aircraft, attr)
    setattr(aircraft, attr, type(current)(raw) if isinstance(current, (int, float))
            and not isinstance(current, bool) else raw)

# --- constraint provenance ------------------------------------------------
# solve._solve_nlp already labels every row (solve._ConstraintLabels), so this
# reuses those rather than wrapping subject_to a second time. Two tracers on one
# Opti is not merely wasteful: the outer one records the INNER wrapper's source
# line for every constraint, which is how this tool briefly reported all 116
# rows as "solve.py:217 out = real(constraint, *a, **kw)".
held: dict = {}
_RealLabels = S._ConstraintLabels


class _Spy(_RealLabels):
    def __init__(self, opti):
        super().__init__(opti)
        held["labels"] = self


S._ConstraintLabels = _Spy

captured = {}
_real_solve = asb.Opti.solve


def patched(self, *a, **kw):
    captured["opti"] = self
    kw["verbose"] = False
    kw["max_iter"] = args.iters   # far enough in to be in the degenerate region
    kw["detect_simple_bounds"] = True
    kw["behavior_on_failure"] = "return_last"
    kw["options"] = {"ipopt.max_wall_time": 900.0}
    return _real_solve(self, *a, **kw)


asb.Opti.solve = patched

saved = os.dup(1)
fd = os.open(HERE / "degeneracy_solve.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
os.dup2(fd, 1)
try:
    S._solve_nlp(aircraft, mission,
                 fixed={"span": args.span} if args.span else None,
                 printed_scale=args.printed_scale)
except Exception as e:
    err = f"{type(e).__name__}: {str(e)[:120]}"
else:
    err = "(solve returned)"
finally:
    sys.stdout.flush()
    os.dup2(saved, 1)
    os.close(saved)
    os.close(fd)

out = open(HERE / "degeneracy_report.txt", "w", buffering=1)


def say(*a):
    print(*a, file=out)
    print(*a, file=sys.stderr, flush=True)


say(f"solve: {err}")
opti = captured["opti"]
x, g = opti.x, opti.g
n_x, n_g = x.shape[0], g.shape[0]

xs = np.array(opti.debug.value(x)).ravel()      # the LAST iterate
gv = np.array(cas.Function("g", [x], [g])(xs)).ravel()
lbg = np.array(opti.debug.value(opti.lbg)).ravel()
ubg = np.array(opti.debug.value(opti.ubg)).ravel()
J = np.array(cas.Function("J", [x], [cas.jacobian(g, x)])(xs))
say(f"n_x = {n_x}, n_g = {n_g}, last iterate finite: {np.isfinite(xs).all()}")

TOL = 1e-4
slack_lo = np.where(np.isfinite(lbg), gv - lbg, np.inf)   # >= 0 when satisfied
slack_hi = np.where(np.isfinite(ubg), ubg - gv, np.inf)   # >= 0 when satisfied
slack = np.minimum(np.abs(slack_lo), np.abs(slack_hi))
scale = np.maximum(1.0, np.abs(gv))
active = np.where(slack / scale < TOL)[0]


_labels = held["labels"].as_dict() if "labels" in held else {}


def where(row):
    return _labels.get(int(row), "(unlabelled)")


# --- PRIMAL first: what could the solver not satisfy? ---------------------
# A solve that ends with inf_pr on a floor is not a degeneracy story at all —
# it never reached the feasible set. Which rows are still violated says whether
# the corner is over-constrained, and by how much (FINDINGS §14.5.6).
violation = np.maximum(np.maximum(-slack_lo, -slack_hi), 0.0)
violated = np.where(violation > 1e-6)[0]
say(f"\nVIOLATED rows at the last iterate (> 1e-6): {len(violated)}"
    f"   total violation {violation.sum():.4e}   worst {violation.max():.4e}")
for r in violated[np.argsort(-violation[violated])][:15]:
    lo_s = "-inf" if not np.isfinite(lbg[r]) else f"{lbg[r]:.4g}"
    hi_s = "+inf" if not np.isfinite(ubg[r]) else f"{ubg[r]:.4g}"
    say(f"  g[{r:3d}]  value {gv[r]: .6e}  in [{lo_s}, {hi_s}]"
        f"  BY {violation[r]:.3e}   {where(r)}")
if len(violated) == 0:
    say("  (none — the last iterate is feasible, so this is a DUAL problem)")

say(f"\nactive rows at the last iterate (|slack|/scale < {TOL}): {len(active)}")
for r in active:
    say(f"  g[{r:3d}]  value {gv[r]: .6e}  slack {slack[r]:.2e}   {where(r)}")

if len(active) < 2:
    say("\ntoo few active rows for linear dependence to be the story here")
    raise SystemExit

A = J[active, :]
U, sv, Vt = np.linalg.svd(A)
say(f"\nsingular values of the active-row Jacobian ({A.shape[0]}x{A.shape[1]}):")
say("  " + "  ".join(f"{s:.3e}" for s in sv))
say(f"  condition number: {sv[0] / sv[-1]:.3e}" if sv[-1] > 0 else "  SINGULAR (exact zero)")

# rows participating in the smallest singular direction = the dependent set
for k in (1, 2, 3):
    if k > len(sv):
        break
    u = U[:, len(sv) - k]
    say(f"\n--- direction of the {k}{'st' if k==1 else 'nd' if k==2 else 'rd'}-smallest "
        f"singular value ({sv[-k]:.3e}); rows with weight > 0.15:")
    for i in np.argsort(-np.abs(u)):
        if abs(u[i]) < 0.15:
            break
        say(f"   weight {u[i]:+.3f}   g[{active[i]:3d}]   {where(active[i])}")
out.close()
