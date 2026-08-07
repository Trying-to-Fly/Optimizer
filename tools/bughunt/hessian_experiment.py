"""Stage 5 — what is the exact Hessian costing this solver?

A 39-variable NLP takes 5.2 s per IPOPT iteration and peaks at 10.18 GB, of
which the CasADi graph is 0.81 GB (FINDINGS §23.4). A dense 39x39 Hessian is
12 KB, so the gigabytes are not linear algebra on the KKT system — they are the
SECOND DERIVATIVE of a full LiftingLine solve embedded symbolically, four times
over. `opti.solve()` sets no `hessian_approximation`, so IPOPT is computing that
exactly, and nothing in this project has ever asked what it costs.

L-BFGS drops the second-derivative graph entirely and pays in iteration count.
Whether that trade is worth taking here is an empirical question, so this
measures it rather than arguing it.

Paired, and the pairing is the point (same posture as §25.2's spar experiment):
ONE solve per arm, same aircraft, same mission, same default inits, run back to
back on the same machine. Direction and the change in cost are what this can
establish. Magnitude from one solve per arm is NOT a precision figure, and if
the two arms land on different objectives they may not be in the same basin.

THE BASELINE ARM IS ALSO THE FREED-SPAR-BOUND CHECK. `exact_hessian` is a real
converged solve of `vtail_sample` at stock settings, which is exactly the
experiment the bug hunt had queued separately: today's uncommitted change raised
`spar_od_center` 14 -> 20 mm and `spar_od_outer` 12 -> 20 mm and added a
symbolic section-fit row, and §25.2 predicts BOTH ODs leave the active set with
`spar_wall_center`/`spar_wall_outer` binding in their place. A truncated solve
cannot test that — an active set is a property of a converged one — so the
control this comparison already required is the answer to it. Reported below as
`spar bounds`.

RUN 2026-08-07, and the answer was no: L-BFGS saved 3.34 GB and did not converge
inside the 30 min cap, against a baseline that converged in 17.38 min. Do not
adopt `limited-memory`. Result in `docs/studies/hessian_stage5.json`, read in
FINDINGS §29; re-run only to answer the questions §29.1 leaves open.

Usage:  uv run python tools/bughunt/hessian_experiment.py [out.json]
"""
import json
import sys
import time
from pathlib import Path

import planeopt  # noqa: F401 — must precede numpy (README: BLAS pinning)
from planeopt import cli, memory, solve

import aerosandbox as asb

ac, _ = cli.load_aircraft(Path("aircraft/vtail_sample"))
ms, _ = cli.load_mission(Path("missions/endurance_sample.py"))

_real_solve = asb.Opti.solve

#: Iteration count of every `Opti.solve` completed in the current arm.
#:
#: Captured HERE because the success path cannot report it afterwards:
#: `_solve_nlp` returns `_pack(sol)`, which carries no solver statistics, and
#: only the FAILURE path attaches `iter_count` (through `SolveFailure`). The
#: 2026-08-06 run proved the consequence — the arm that CONVERGED reported
#: `"iter_count": null` while the arm that timed out reported 871, so the
#: experiment recorded iterations only when it did not get an answer. That is
#: exactly backwards for a trade whose entire claim is that L-BFGS drops the
#: second-derivative graph and PAYS IN ITERATION COUNT.
#:
#: A list rather than one value, because the patch below applies to every
#: `Opti.solve` in the process. `_solve_nlp` builds a single NLP today, so this
#: should hold exactly one entry — `opti_solve_calls` reports how many there
#: actually were rather than assuming.
_ITER_COUNTS: list[int | None] = []


def _with_options(extra: dict):
    """Merge extra IPOPT options into every `opti.solve` in this process.

    Patched at the Opti rather than added to `solve.py` on purpose: an
    undeclared global that changes solver behaviour is exactly the kind of knob
    this project keeps finding it has been misled by, and an experiment does not
    justify creating one. If L-BFGS wins, it becomes a declared default with the
    measurement behind it — not a hook someone can set by accident.
    """
    def patched(self, *a, **kw):
        kw["options"] = {**(kw.get("options") or {}), **extra}
        sol = _real_solve(self, *a, **kw)
        try:
            _ITER_COUNTS.append((self.debug.stats() or {}).get("iter_count"))
        except Exception:  # noqa: BLE001 — a measurement may not fail the arm
            _ITER_COUNTS.append(None)
        return sol

    asb.Opti.solve = patched


def arm(label: str, extra: dict) -> dict:
    _with_options(extra)
    _ITER_COUNTS.clear()
    memory.reset_peak_rss()
    t0 = time.monotonic()
    failed = None
    try:
        r = solve._solve_nlp(ac, ms)
    except Exception as e:  # noqa: BLE001 — a failed arm is a result, not a crash
        r, failed = {}, f"{type(e).__name__}: {e}"
        status = getattr(e, "return_status", None)
        # The failure carries its own count and it is the authority here: the
        # solve raised, so it never returned through the patch above.
        iters = getattr(e, "iter_count", None)
    else:
        status = "Solve_Succeeded"
        iters = max((n for n in _ITER_COUNTS if n is not None), default=None)
    out = {
        "arm": label,
        "options": extra,
        "minutes": round((time.monotonic() - t0) / 60.0, 2),
        "peak_gb": round(memory.peak_rss_gb(), 2),
        "status": status,
        "iter_count": iters,
        "opti_solve_calls": len(_ITER_COUNTS),
        "failed": failed,
        "objective_value": r.get("objective_value"),
        "auw_kg": r.get("auw_kg"),
        "drag_n": r.get("drag_n"),
        "V_ms": r.get("V_ms"),
        "static_margin": r.get("static_margin"),
        "active_bounds": sorted(b["variable"] for b in r.get("active_bounds", [])),
        "dv": r.get("dv"),
    }
    print(json.dumps({k: v for k, v in out.items() if k != "dv"}, indent=2), flush=True)
    return out


results = [
    # Baseline FIRST, so a machine that degrades over the pair degrades the
    # challenger rather than flattering it.
    arm("exact_hessian", {}),
    arm("limited_memory", {"ipopt.hessian_approximation": "limited-memory"}),
]

Path(sys.argv[1] if len(sys.argv) > 1 else "stage5.json").write_text(
    json.dumps(results, indent=2)
)

a, b = results
print("\n=== paired result")
for key in ("minutes", "peak_gb", "iter_count", "objective_value", "auw_kg", "drag_n"):
    print(f"  {key:18} {a.get(key)!r:>24}  ->  {b.get(key)!r}")
if a.get("objective_value") and b.get("objective_value"):
    d = b["objective_value"] - a["objective_value"]
    print(f"  objective delta    {d:+.4f} "
          f"({100 * d / a['objective_value']:+.3f}% — same design or a different basin?)")
print(f"  active set         {a['active_bounds']}\n"
      f"                  -> {b['active_bounds']}")

# --- the freed spar bounds, on the converged baseline arm (FINDINGS §25.2) ---
# The prediction is specific enough to be wrong: both ODs interior, both walls
# binding. Anything else is a finding — if an OD is STILL pinned it is now
# pinned against 20 mm rather than 14, which would mean the section-fit row is
# not the thing holding it and §25.1's diagnosis is incomplete.
print("\n=== spar bounds (baseline arm, converged)")
if a.get("dv"):
    active = set(a["active_bounds"])
    for name in ("spar_od_center", "spar_od_outer",
                 "spar_wall_center", "spar_wall_outer"):
        mark = "ACTIVE" if name in active else "interior"
        print(f"  {name:20} {1000 * a['dv'][name]:7.3f} mm   {mark}")
    ods = {"spar_od_center", "spar_od_outer"} & active
    walls = {"spar_wall_center", "spar_wall_outer"} & active
    print(f"  §25.2 predicted: ODs interior, walls binding — "
          f"ODs active: {sorted(ods) or 'none'}; walls active: {sorted(walls) or 'none'}")
else:
    print(f"  baseline arm did not converge ({a['failed']}) — nothing to read")

