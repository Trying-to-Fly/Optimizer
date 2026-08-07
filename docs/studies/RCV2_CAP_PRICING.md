# Pricing the caps behind the rcv2 corners

> **STATUS: stopped 2026-08-07 09:40 local, not running.** Stages A, B and C are
> measured; stage F got one of six spans. Raw data:
> `docs/studies/rcv2_cap_pricing/cells.jsonl`, one JSON line per cell.
>
> **This machine sleeps, and that invalidated four cells before it was caught
> (§4). Anything measured here with the lid shut is not evidence.**

## 0. The three results

1. **Every corner the battery lost converges here in 2-5 minutes** — all six
   members, including the three studies that returned no verdict and the exact
   member `degeneracy.py` was run on. Stage A cost ~19 minutes of solving for
   what cost that battery 287.7 minutes of nothing.
2. **Of the four caps HANDOFF named, only the span cap is worth anything**, and
   raising the chord cap ALONE is not a remedy at all — it walks into a harder
   row (§5).
3. **Four cells "failed" because the laptop was asleep**, not because of a
   constraint. IPOPT's guard is a WALL clock and a suspended process is charged
   for its suspension (§4).

## 1. Why

The `20260806T031736` rcv2 battery spent **287.7 of its 417.5 minutes (69%)** on
ten members that produced nothing, all `Maximum_WallTime_Exceeded`. Three
studies returned no verdict (tail type, both candidates; fuselage topology; wing
dihedral) and the flatness sweep reported 2 of its 6 spans.

`tools/degeneracy.py` settled what those members are: **not degenerate** (cond
2.49, LICQ holds) but **over-constrained corners** — 18 rows violated at once.
FINDINGS §14.5.7 measured that more clock does not convert one. HANDOFF names
the remedy — raise chord, raise span, widen the SM window, or carry less kit —
and says it is the user's decision. **None of the four had a price.**

## 2. Stage A — the corners do not reproduce

Current tree, 15-minute budget, one solve per process, each member in the
configuration it declares.

| member | battery | here | min | SM | AUW kg |
|---|---|---|---|---|---|
| `nominal` | converged | 105.818 | 2.64 | 0.0800 | 2.158 |
| `tail_conventional` | **no verdict** | **100.867** | 4.73 | 0.0800 | 2.229 |
| `tail_ttail` | **no verdict** | **98.118** | 3.50 | 0.0800 | 2.275 |
| `fuselage_integrated` | **no verdict** | **102.001** | 2.44 | 0.0800 | 2.232 |
| `dihedral_polyhedral2` | **no verdict** | **103.362** | 2.68 | 0.0800 | 2.221 |
| `printed_mass_x1.10` | **no verdict** | **96.504** | 2.74 | 0.0800 | 2.326 |

**All six land on the same five limits at once**: `span` on its 2.0 m cap,
`c_root` on its 0.275 m cap, `cs_frac` on its 0.4 bound, `ballast_kg` on zero,
and the static margin **exactly on its 0.0800 floor** — what a binding
constraint looks like (§14.5.8). The aeroplane IS in the corner the failures
were attributed to. It simply solves there.

`flatness_2.0` re-derives `nominal` exactly (105.818, 3.07 min), which is the
consistency check that member ought to pass and had never been asked to.

## 3. Stage C — the converged champion is airworthy, on two machines

`diagnostics.candidates_source` = **`legal`** here, twice (03:12 and 09:35), with
notes[0] the ordinary stall caveat rather than §28's fallback banner.

Independently, the 2026-08-07 battery
`runs/20260807T061330-rcv2_endurance-vtail_sample_v1-7_rcv2` reports
`candidates_source: "legal"`, `reported_point_violations` empty, trim −3.33°
against a 6.53° cap — **and reproduces this study's `nominal` at 105.8 against
105.818**.

So the §28 illegal champion was the **3-iteration truncation, not the aeroplane**.
A converged rcv2 champion does solve its own balance, which is what §28.4 said
was unknown.

## 4. Four failures were idle sleep, and the clock is a wall clock

`solve._solve_nlp` sets `ipopt.max_wall_time`, deliberately and correctly — it
protects the run's wall clock against a solve that starts swapping. But a
**suspended process is charged for its suspension**, so a member spanning a
sleep window is killed for time it never got to use.

| cell | ran (local) | verdict | machine |
|---|---|---|---|
| six baselines + `sm_floor_0.05` | 00:17-00:41 | **all converged** | awake |
| `c_root_0.300` | 01:12-01:18 | wall-time | slept 01:02-01:18 |
| `span_cap_2.2` | 02:06-02:08 | wall-time | slept 01:52-02:08 |
| `kit_core` | 02:51-02:54 | wall-time | slept 02:26-… |

Perfect separation, and the 31-, 48- and 43-minute gaps BETWEEN those cells are
the machine asleep between them. Re-measured awake, **`span_cap_2.2` converges in
2.97 minutes** — so that verdict was purely the artifact.

`solve._convergence_trace` called all three *"still converging when the clock
stopped — the one case where a larger `--solve-timeout-min` may actually pay"*,
which is exactly right, and on its own would have sent the next reader to raise
a cap that was never the problem.

**`caffeinate -i` is necessary and not sufficient.** It blocks idle sleep. It
does NOT block **clamshell sleep** — closing the lid at 09:07 put the machine to
sleep on battery anyway, and `kit_core` (09:26-09:33, against `Maintenance Sleep`
from 09:17:56 to a DarkWake at 09:33:19) is a second victim, still unmeasured.

### The signature, and how to check any run for it

**A member reporting `Maximum_WallTime_Exceeded` with `solve_minutes` far below
`--solve-timeout-min` did not run out of time — it was asleep.** A genuine corner
burns its whole budget and hundreds of iterations: §14.5.7's pusher did 187 then
474, and this study's one real corner did **415**. The sleeping cells died at 68,
25 and 15.

Both numbers are already in every `run.json`, so any past battery can be audited
without re-solving. The `20260806T031736` battery started at **03:17**,
unattended; if it ran on a Mac allowed to sleep, some of its ten losses are this
and not corners.

## 5. Stage B — what the four caps are actually worth

Measured awake, on the nominal design (105.818 baseline).

| relaxation | result | vs baseline |
|---|---|---|
| `span_cap` 2.0 → 2.2 m | **110.989**, converged 2.97 min | **+5.170 min** |
| SM floor 0.08 → 0.05 | 106.669, converged 4.31 min | +0.851 min |
| `c_root` 0.275 → 0.300 m | **no design** — 415 iters, full 30.92 min | — |
| kit `full` → `core` | not measured — slept | — |

**Span is the binding cap and the only one worth real minutes.** At 2.2 m the
design comes off BOTH caps — neither `span` nor `c_root` is pinned any more,
only `ballast_kg` and `cs_frac`. So the chord cap was binding *because* span was
capped, and 200 mm of span buys 5.17 minutes, six times what the whole
static-margin window is worth.

**The static-margin floor binds but is nearly worthless to relax**: giving up
0.03 — over a third of the required 0.08 — buys 51 seconds.

**Raising the chord cap alone is not a remedy.** It is the one genuine corner
this study found: a plateau short of feasible (`inf_pr` progress over the last 25
iterations, −2×10⁻⁶), dominated by

    aircraft.py:1138  usable_nose / motor["length"] >= 1.0   short by 5.14e-02

nearly 8× the next row (lift equilibrium). At a 300 mm root chord the nose can
no longer be made long enough to hold the motor.

**That row is the one to work on, and it is not in HANDOFF's list of four.** The
2026-08-07 battery reached the same conclusion independently: **five of its six
failures name `aircraft.py:1138` as their closest miss**, by 1.4 to 3.3 mm of
usable nose. Two machines, two routes, same row. `POD_LENGTH_RELAXATIONS` in
`tools/price_caps.py` is where that lead is being followed.

## 6. What the converged rows do NOT license

**Not "the caps are fine."** They license "these six members are not cap-blocked
on the current tree." Two differences from the battery remain unresolved:

1. **The battery ran on a tree since reverted.** It started 2026-08-06 03:17; the
   ordering-row rescale was reverted at 08:22 the same day (`1363ea8`). That
   rescale was solution-preserving and cost ~45% of solve time — on its own
   enough to push a converging member past a 30-minute budget, which is what it
   did to `winglet_study__continuous_cant`.
2. **The battery's studies run greedily**, so its `tail_conventional` carried the
   adopted prop and topology; these cells carry the declared baseline
   (`ancf_11x6`). Same label, different aeroplane. `solve.screen_discrete` ranks
   the prop catalogue with no NLP at all, so closing this is cheap — not done.

With §4 that makes **three** candidate explanations for the 69%, and none of them
is a cap.

## 7. Reproducing

`drive` must have the machine to itself — a cell peaks near 15 GB and so does a
battery. There is no lock that enforces it; check `ps` first. And it must have
the machine AWAKE: lid open, on AC, `caffeinate -i` (§4).

    caffeinate -i uv run python tools/price_caps.py drive
    caffeinate -i uv run python tools/price_caps.py cell --member tail_ttail --relax sm_floor_0.05

`report` reads `runs/_capprice/` (untracked, written by `drive`). The cells
committed with this study are under `docs/`, so reading THEM takes the override:

    PRICE_CAPS_OUT=docs/studies/rcv2_cap_pricing uv run python tools/price_caps.py report

## 8. Still open

| | |
|---|---|
| `kit_core` | slept through twice; the only one of the four caps still unpriced |
| stage F | 5 of 6 flatness spans unmeasured |
| the greedy chain | §6.2 — cheap, not done |
| `usable_nose` | §5 — the row that actually blocks this aeroplane |
