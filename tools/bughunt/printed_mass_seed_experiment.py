"""Why does `printed_mass_x0.90` fail on this branch when main solves it fastest?

FINDINGS §36.4 is the open question this answers. That member is main's QUICKEST
— 4.51 and 4.60 minutes across two batteries, converging at 127.8829 — and it
fails on `casadi-speed-stability` in both warm-start configurations, getting
worse rather than better between them:

    main x2         4.51 / 4.60 min                    127.8829
    pre-fix        12.95 min   57 iters  inf_pr 0.0796  starved corner
    post-fix       16.59 min  102 iters  inf_pr 0.1115  starved corner

Failing WITH and WITHOUT `WARM_START_OPTIONS` rules the options out, which is
what makes this different from every other failure §35 and §36 catalogued. What
is left is the `inits` seed itself, or the champion behind it. Its closest miss
is the motor-fit row (`usable_nose / motor["length"] >= 1.0`), and the story that
fits — at -10% printed mass the optimum shrinks, and shrinking from the
champion's nose geometry drives into that wall — is plausible and unmeasured.
Plausible is what this file exists to replace.

    champion         cold, declared configuration; the seed source
    x090_cold        printed_scale 0.90, no seed — the control, and main's path
    x090_seeded      printed_scale 0.90 + `_hot_start_kwargs(champion)`

If `x090_cold` converges and `x090_seeded` does not, the seed is the cause and
the re-solve battery should not be seeding this member. If BOTH fail, the seed
is exonerated and the defect is somewhere else on the branch entirely — which
would be a bigger finding, since main solves this member in four and a half
minutes.

The control runs BEFORE the challenger, so a machine that degrades over the
sequence degrades the seeded arm rather than flattering it (same posture as
`warm_start_experiment.py` and §29's Hessian experiment).

WHAT THIS CANNOT SETTLE: the champion here is the DECLARED configuration, not
the battery's champion after its discrete studies have adopted a prop and a
tail. So a difference reproduces the mechanism, not the battery member exactly.
One solve per arm is direction, not a precision figure.

Usage:
    .venv/bin/python tools/bughunt/printed_mass_seed_experiment.py <arm> [state_dir]
    .venv/bin/python tools/bughunt/printed_mass_seed_experiment.py report [state_dir]
"""
import json
import sys
import time
from pathlib import Path

import planeopt  # noqa: F401 — must precede numpy (README: BLAS pinning)
from planeopt import cli, memory, solve

#: The -10% printed-mass arm of the re-solve battery, built in `solve.optimize`
#: as `{**battery_warm, "printed_scale": 0.90}`.
PRINTED_SCALE = 0.90

#: What the battery gives an optional member. A cold arm that converges inside
#: this proves the point without argument; one that needs longer is a different
#: finding and wants saying so.
TIMEOUT_MIN = solve.OPTIONAL_MEMBER_TIMEOUT_MIN

ARMS = ("champion", "x090_cold", "x090_seeded")


def arm_kwargs(arm: str, champion: dict | None) -> dict:
    """What `_solve_nlp` is called with for one arm. Pure, so it can be tested.

    `warm_start` is never sent: §36 removed it from `_hot_start_kwargs` and the
    seeded arm here is the CURRENT code path, not a historical one. The question
    is whether `inits` alone is what kills this member.
    """
    if arm == "champion":
        return {}
    kwargs: dict = {"printed_scale": PRINTED_SCALE, "timeout_min": TIMEOUT_MIN}
    if arm == "x090_seeded":
        kwargs |= solve._hot_start_kwargs(champion or {})
    return kwargs


def _machine() -> dict:
    total, available = memory.machine_ram()
    return {"ram_total_gb": round(total, 2),
            "ram_available_gb": round(available, 2),
            "swap_gb": round(memory.swap_gb(), 2)}


def run(arm: str, state: Path) -> dict:
    ac, _ = cli.load_aircraft(Path("aircraft/vtail_rcv2"))
    ms, _ = cli.load_mission(Path("missions/rcv2_endurance.py"))

    champion = None
    if arm == "x090_seeded":
        champion = json.loads((state / "champion.json").read_text())["result"]
    kwargs = arm_kwargs(arm, champion)

    before = _machine()
    memory.reset_peak_rss()
    t0 = time.monotonic()
    failed = None
    try:
        r = solve._solve_nlp(ac, ms, **kwargs)
    except Exception as e:  # noqa: BLE001 — a failed arm is a result, not a crash
        r, failed = {}, f"{type(e).__name__}: {e}"
        status = getattr(e, "return_status", None)
        iters = getattr(e, "iter_count", None)
    else:
        status, iters = r.get("return_status"), r.get("iter_count")

    out = {
        "arm": arm,
        "seeded": "inits" in kwargs,
        "printed_scale": kwargs.get("printed_scale", 1.0),
        "minutes": round((time.monotonic() - t0) / 60.0, 2),
        "peak_gb": round(memory.peak_rss_gb(), 2),
        "status": status,
        "iter_count": iters,
        "failed": failed,
        "objective_value": r.get("objective_value"),
        "V_ms": r.get("V_ms"),
        "auw_kg": r.get("auw_kg"),
        "convergence": r.get("convergence"),
        "machine_before": before,
        "machine_after": _machine(),
        "result": r,
    }
    (state / f"{arm}.json").write_text(json.dumps(solve._jsonable(out), indent=2))
    print(json.dumps(
        solve._jsonable({k: v for k, v in out.items() if k != "result"}), indent=2
    ), flush=True)
    return out


def report(state: Path) -> None:
    print(f"{'arm':14}{'min':>8}{'iters':>8}{'objective':>13}  status")
    for arm in ARMS:
        p = state / f"{arm}.json"
        if not p.is_file():
            print(f"{arm:14}{'(not run)':>8}")
            continue
        d = json.loads(p.read_text())
        obj = d.get("objective_value")
        print(f"{arm:14}{d['minutes']:8.2f}{str(d.get('iter_count')):>8}"
              f"{(f'{obj:.4f}' if obj else '--'):>13}  {d.get('status')}")
    cold = state / "x090_cold.json"
    seed = state / "x090_seeded.json"
    if cold.is_file() and seed.is_file():
        c, s = json.loads(cold.read_text()), json.loads(seed.read_text())
        cok, sok = c.get("objective_value") is not None, s.get("objective_value") is not None
        print()
        if cok and not sok:
            print("VERDICT: the SEED is the cause — cold converges, seeded does not.")
        elif cok and sok:
            print("VERDICT: seeding is not fatal here; both converge. Compare "
                  "iterations and objectives above.")
        elif not cok and not sok:
            print("VERDICT: the seed is EXONERATED — this member fails cold too, "
                  "so the defect is elsewhere on the branch. Main solves it in "
                  "4.51 min, which makes this the larger finding.")
        else:
            print("VERDICT: seeded converges and cold does not — the opposite of "
                  "the hypothesis, and worth a second pair before believing.")


def main() -> None:
    arm = sys.argv[1] if len(sys.argv) > 1 else "report"
    state = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/studies/printed_mass_seed")
    state.mkdir(parents=True, exist_ok=True)
    if arm == "report":
        report(state)
    elif arm in ARMS:
        run(arm, state)
    else:
        raise SystemExit(f"unknown arm {arm!r}; expected one of {ARMS} or 'report'")


if __name__ == "__main__":
    main()
