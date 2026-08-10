"""Does a champion-derived hot start pay for itself, and did the options matter?

FINDINGS §34.3 closed the seed defect and opened this. `_hot_start_kwargs` used
to carry `solver_seed`, and `_solve_nlp` gates `WARM_START_OPTIONS` on
`warm_start or hot_start_used` — so the seed was also the only thing switching
those options on for a battery member. Dropping the seed dropped the options
with it, silently, and left every hot start in the configuration
`WARM_START_OPTIONS` documents at +27% against cold: IPOPT's default
`bound_push` of 0.01 shoves the starting point off every bound before iteration
0, and the champion sits on eight of them, so the one thing the seed is worth
is discarded before the first iteration.

(`hot_start_used` and the seed machinery it came from were deleted once this
measurement was in; `_solve_nlp` now gates on `warm_start` alone. The arms below
still measure the right two configurations — `bump_inits_only` reproduces the
old behaviour by dropping the flag, which is what the old code did by accident.)

That predicts §34.3's own caveat — the corrected `mass_bump` took 11.93 min
against main's cold 7.41-7.78 — is the seed-only penalty rather than evidence
that champion-derived `inits` do not pay. This measures the difference instead
of arguing it.

Four arms, and the pairing is the point (same posture as §29's Hessian
experiment and §25.2's spar experiment): same aircraft, same mission, one solve
per arm, back to back on the same machine.

    champion                 cold, and the seed source for the two warm arms
    bump_cold                +20 g cold — the control the warm arms answer to
    bump_inits_only          `inits` alone: the branch as of cf9d5b6
    bump_inits_and_options   `inits` + WARM_START_OPTIONS: the fix

Order is deliberate. The control runs BEFORE both challengers, so a machine
that degrades over the sequence degrades the fix rather than flattering it.

ONE PROCESS PER ARM, which is not merely tidy. `memory.reset_peak_rss` cannot
clear the high-water mark on macOS — the mark only rises — so arms sharing a
process would each report the largest solve that ran before them. A fresh
process is the only way to get a per-arm peak here, and it also hands the whole
CasADi graph back to the OS between arms, which matters on a 16 GB laptop where
these members peak at 5.6-9.9 GB (§34.1).

Magnitude from one solve per arm is NOT a precision figure. Direction, and
whether all four land on the same design, are what this can establish.

Usage:
    uv run python tools/bughunt/warm_start_experiment.py <arm> [state_dir]
    uv run python tools/bughunt/warm_start_experiment.py report [state_dir]

`run_warm_start_experiment.sh` drives all four in order under `caffeinate`.
"""
import json
import sys
import time
from pathlib import Path

import planeopt  # noqa: F401 — must precede numpy (README: BLAS pinning)
from planeopt import cli, memory, solve

#: The +20 g shadow-price member, which is the one §34.3 measured and the one
#: every hot-started member of that battery failed as.
BUMP_KG = 0.020

ARMS = ("champion", "bump_cold", "bump_inits_only", "bump_inits_and_options")


def _machine() -> dict:
    """What the machine had to offer at the moment this arm started.

    Recorded per arm because a 16 GB laptop running members that peak near 10 GB
    can page, and paging lands in wall-clock. A reader comparing two arms needs
    to see whether they were offered the same machine — otherwise the timing
    column is measuring the SSD.
    """
    total, available = memory.machine_ram()
    return {
        "ram_total_gb": round(total, 2),
        "ram_available_gb": round(available, 2),
        "swap_gb": round(memory.swap_gb(), 2),
        "compressed_gb": round(memory.compressed_gb(), 2),
    }


def run(arm: str, state: Path) -> dict:
    ac, _ = cli.load_aircraft(Path("aircraft/vtail_rcv2"))
    ms, _ = cli.load_mission(Path("missions/rcv2_endurance.py"))

    kwargs: dict = {}
    if arm != "champion":
        kwargs["extra_mass_kg"] = BUMP_KG
    if arm in ("bump_inits_only", "bump_inits_and_options"):
        champion = json.loads((state / "champion.json").read_text())["result"]
        # The function under test builds both warm arms, so the experiment
        # cannot drift from what the battery actually does.
        kwargs |= solve._hot_start_kwargs(champion)
        if arm == "bump_inits_only":
            # Exactly cf9d5b6: the same physical seed, without the options that
            # let IPOPT keep it. This pop IS the change being measured.
            kwargs.pop("warm_start")

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
        status = r.get("return_status")
        iters = r.get("iter_count")

    out = {
        "arm": arm,
        "warm_start_options": bool(kwargs.get("warm_start")),
        "seeded": "inits" in kwargs,
        "extra_mass_kg": kwargs.get("extra_mass_kg", 0.0),
        "minutes": round((time.monotonic() - t0) / 60.0, 2),
        "peak_gb": round(memory.peak_rss_gb(), 2),
        "status": status,
        "iter_count": iters,
        "failed": failed,
        "objective_value": r.get("objective_value"),
        "auw_kg": r.get("auw_kg"),
        "V_ms": r.get("V_ms"),
        "static_margin": r.get("static_margin"),
        "active_bounds": sorted(b["variable"] for b in r.get("active_bounds", [])),
        "machine_before": before,
        "machine_after": _machine(),
        # kept out of the printed summary, needed by the warm arms
        "result": {k: v for k, v in r.items() if k != "_solver_seed"},
    }
    (state / f"{arm}.json").write_text(json.dumps(solve._jsonable(out), indent=2))
    print(json.dumps(
        solve._jsonable({k: v for k, v in out.items() if k != "result"}), indent=2
    ), flush=True)
    return out


def report(state: Path) -> None:
    arms = {}
    for name in ARMS:
        path = state / f"{name}.json"
        if path.exists():
            arms[name] = json.loads(path.read_text())

    print(f"\n{'arm':<24} {'min':>7} {'iters':>7} {'peak GB':>8}  status")
    for name, a in arms.items():
        print(f"{name:<24} {a['minutes']:>7.2f} {str(a['iter_count']):>7} "
              f"{a['peak_gb']:>8.2f}  {a['status']}")

    control = arms.get("bump_cold")
    if not control or control.get("failed"):
        print("\nNo cold control — nothing to compare against.")
        return
    base = control["minutes"]
    print(f"\nAgainst the cold control ({base:.2f} min):")
    for name in ("bump_inits_only", "bump_inits_and_options"):
        a = arms.get(name)
        if not a:
            continue
        if a.get("failed"):
            print(f"  {name:<24} FAILED — {a['failed']}")
            continue
        print(f"  {name:<24} {a['minutes']:>7.2f} min  "
              f"{(a['minutes'] / base - 1.0) * 100:+6.1f}%")

    # A speed comparison between arms that landed on different designs is not a
    # comparison. §34.3's own evidence for the seed fix was reproducing main's
    # objective EXACTLY, and the 2026-07-31 warm-start measurement leant on all
    # three arms agreeing to eight significant figures.
    objectives = {
        n: a["objective_value"] for n, a in arms.items()
        if n != "champion" and not a.get("failed") and a["objective_value"] is not None
    }
    if len(objectives) > 1:
        spread = max(objectives.values()) - min(objectives.values())
        print(f"\nObjective spread across the +{BUMP_KG * 1000:.0f} g arms: {spread:.3e}")
        for n, v in objectives.items():
            print(f"  {n:<24} {v!r}")
        if spread > 1e-4:
            print("  ^ these arms did NOT land on the same design; the timings "
                  "above are not comparable.")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "report"
    where = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/studies/warm_start")
    where.mkdir(parents=True, exist_ok=True)
    if what == "report":
        report(where)
    elif what in ARMS:
        run(what, where)
    else:
        sys.exit(f"unknown arm {what!r}; expected one of {', '.join(ARMS)} or 'report'")
