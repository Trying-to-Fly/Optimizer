# Pricing the caps behind the rcv2 corners

> **STATUS: running 2026-08-07, lid open on AC.** Stages A, B and C are complete
> and every lever is priced; stage F (the flatness spans) is in progress. Raw
> data: `docs/studies/rcv2_cap_pricing/cells.jsonl`, one JSON line per cell.
>
> **This machine sleeps, and that invalidated four cells before it was caught
> (§4). Anything measured here with the lid shut is not evidence.**

## 0. The three results

1. **Every corner the battery lost converges here in 2-5 minutes** — all six
   members, including the three studies that returned no verdict and the exact
   member `degeneracy.py` was run on. Stage A cost ~19 minutes of solving for
   what cost that battery 287.7 minutes of nothing.
2. **Two levers matter and neither is a modelling decision**: dropping the
   optional payload is worth +7.907 min and 200 mm of span is worth +5.170 min.
   Everything else is under a minute, and raising the chord cap ALONE is not a
   remedy at all — it walks into a harder row (§5).
3. **Four cells "failed" because the laptop was asleep**, not because of a
   constraint. IPOPT's guard is a WALL clock and a suspended process is charged
   for its suspension (§4). Re-measured awake, three of the four converge; the
   fourth (`c_root_0.300`) is the study's one genuine corner.

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
| kit dropped | 02:51-02:54 | wall-time | slept 02:26-… |

Perfect separation, and the 31-, 48- and 43-minute gaps BETWEEN those cells are
the machine asleep between them. Re-measured awake, **`span_cap_2.2` converges in
2.97 minutes** — so that verdict was purely the artifact.

`solve._convergence_trace` called all three *"still converging when the clock
stopped — the one case where a larger `--solve-timeout-min` may actually pay"*,
which is exactly right, and on its own would have sent the next reader to raise
a cap that was never the problem.

**`caffeinate -i` is necessary and not sufficient.** It blocks idle sleep. It
does NOT block **clamshell sleep** — closing the lid at 09:07 put the machine to
sleep on battery anyway, and the kit cell (09:26-09:33, against `Maintenance
Sleep` from 09:17:56 to a DarkWake at 09:33:19) was a second victim. Re-measured
with the lid open it converges in 9.41 min, so it too was purely the artifact.

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

## 5. Stage B — what every lever is actually worth

Measured awake, on the nominal design (105.818 baseline).

| relaxation | result | vs baseline |
|---|---|---|
| payload dropped (`airframe_only`, −192 g) | **113.725**, converged 9.41 min | **+7.907 min** |
| `span_cap` 2.0 → 2.2 m | **110.989**, converged 2.97 min | **+5.170 min** |
| `fineness_max` 8.0 → 9.0 | 106.895, converged 2.95 min | +1.077 min |
| SM floor 0.08 → 0.05 | 106.669, converged 4.31 min | +0.851 min |
| `boat_tail_min_d_eq` 1.8 → 1.5 | 106.270, converged 3.72 min | +0.452 min |
| `c_root` 0.275 → 0.300 m | **no design** — 415 iters, full 30.92 min | — |
| *+20 g reference bump* | 104.400 | −1.418 → **−0.0709 min/g** |

**The two that matter are the payload and the span**, and both are decisions this
model cannot make: the payload is why the aeroplane exists (`priced, never
adopted`, and the call on main is that it is fitted), and the 2.0 m cap prices
transport, storage, hand-launch and the print bed, none of which is in the model.

The three pod/stability levers are real but small — about a minute each, and
under half a minute for the boat tail.

**The 20 g shadow price does not extrapolate to the payload step.** −0.0709 min/g
predicts +13.6 min for 192 g; the measurement is +7.9. That is the re-optimization
the local derivative cannot see, and it is the reason `screen_discrete` is a
shortlister rather than a verdict.

**The chord cap is binding only BECAUSE span is capped.** At 2.2 m the design
comes off both — neither `span` nor `c_root` is pinned any more, only
`ballast_kg` and `cs_frac`. Dropping the payload does the same thing. So `c_root`
is never the lever: it is a symptom of whichever of the other two is holding.

**The static-margin floor binds but is nearly worthless to relax**: giving up
0.03 — over a third of the required 0.08 — buys 51 seconds.

**Raising the chord cap alone is not a remedy.** It is the one genuine corner
this study found: a plateau short of feasible (`inf_pr` progress over the last 25
iterations, −2×10⁻⁶), dominated by

    aircraft.py:1138  usable_nose / motor["length"] >= 1.0   short by 5.14e-02

nearly 8× the next row (lift equilibrium). At a 300 mm root chord the nose can
no longer be made long enough to hold the motor.

### What that row actually is, at the champion

`usable_nose` is not "how long the nose is". From `nose_split`:

    r_req       = can_width / d_min
    behind      = sqrt(1 - r_req^2)
    usable_nose = pod_nose * behind

so the length available for the motor **collapses to zero as the pod section
approaches the can's diameter**, however long the nose is. Evaluated on the
champion's own design vector (no solve — this is arithmetic):

| | |
|---|---|
| pod section | `pod_xs` **0.874**, d_eq 67.64 mm — SMALLER than the 77.4 mm spec |
| section shape | `pod_wh` **1.0017** — square to four decimal places |
| narrow dimension | height, 67.58 mm; can needs 49.00 mm, `r_req` 0.7252 |
| nose | `pod_nose` 74.07 mm, of which the cone eats 23.07 |
| **usable nose** | **51.00 mm against a 51.00 mm can — slack −0.00 mm** |

**The square section is not a coincidence, it is the optimum.** `pod_xs` sizes
the section and `pod_wh` shapes it, orthogonally: `w*h = d_eq^2` whatever the
ratio. At constant area a square MAXIMISES the narrow dimension, which is the
one the motor can has to pass through — so the optimizer has already found the
best shape this row can be given, and the design sits exactly on the row anyway.

Sensitivities at that point, per +5%:

| | usable nose |
|---|---|
| `pod_xs` (section size) | **+2.57 mm** |
| `pod_nose` (nose length) | +2.55 mm |
| `pod_wh` (section shape) | **−1.42 mm** |

`pod_wh` going the WRONG way is the trap: past 1.0 the height becomes the narrow
dimension and shrinks. Anyone reaching for "widen the pod" should widen `pod_xs`,
not `pod_wh`.

So the pod is squeezed DOWN by drag and held UP by the motor can, with its shape
already optimal — which is why the two length levers (§5) buy about a minute
each and no more.

**That row is the one to work on, and it is not in HANDOFF's list of four.** The
2026-08-07 battery reached the same conclusion independently: **five of its six
failures name `aircraft.py:1138` as their closest miss**, by 1.4 to 3.3 mm of
usable nose. Two machines, two routes, same row. `POD_LENGTH_RELAXATIONS` in
`tools/price_caps.py` is where that lead is being followed.

## 5b. Stage F — a hard span floor, and a proof that was one iteration away

| span | result |
|---|---|
| 2.00 m | 105.818 (re-derives `nominal` exactly) |
| 1.94 m | 104.336 |
| 1.88 m | 99.517 |
| 1.82 m | **no design** — 176 iters, full budget, *"dual blow-up: stuck"* |
| 1.76 m | **no design** — 183 iters, full budget, *"dual blow-up: stuck"* |
| 1.70 m | **`Infeasible_Problem_Detected`** — proved |

So three of the battery's four lost spans come back, one is a genuine corner,
and the sweep is **not flat on the low side**: the first 60 mm below the cap
costs 1.48 min, the second costs 4.82, and below ~1.85 m there is no aeroplane.
The dominant miss is lift equilibrium throughout, and it grows monotonically as
span shrinks (4.68e-02 at 1.82, 5.31e-02 at 1.76) — which is the direct evidence
for the interval-feasibility assumption `flatness_sweep`'s downward cascade
rests on, and which had been an argument rather than a measurement.

### The cascade is not dead code — it has never been given eight seconds

`flatness_sweep`'s docstring records that the infeasibility gate has never once
fired: *"on THIS model that proof has never arrived… every failure ever
recorded, in every run, is `Maximum_WallTime_Exceeded`, so the 2026-07-31 sweep
spent 130.6 minutes on four spans and skipped none."*

The same member, same tree, same configuration, at two budgets:

| budget | outcome | after |
|---|---|---|
| 15 min | `Maximum_WallTime_Exceeded` | 16.04 min, **192 iterations** |
| 30 min | **`Infeasible_Problem_Detected`** | 16.16 min, **193 iterations** |

**One iteration.** The certificate was ~8 seconds past where the budget cut it
off, and the convergence trace had said so in words — *"still converging when the
clock stopped, the one case where a larger `--solve-timeout-min` may actually
pay"*. It is the one case, and it paid.

`FLATNESS_TIMEOUT_MIN` is 20 minutes and this member wanted 16.2, so the shipped
sweep would have got the proof here. What it would NOT have got is the two
neighbours above (1.82, 1.76 both grind their whole budget and read STUCK), and
the cascade only skips spans BELOW a proof — so the proof arriving at the BOTTOM
of the range saves nothing. **The value is in the budget being long enough at the
first infeasible span, not at the last.** On this sweep that is 1.82 m, and it
did not certify in 16 minutes.

### Measured, and it says leave the constant alone

The obvious next move was to raise `FLATNESS_TIMEOUT_MIN`. **That was proposed
here three hours before it was measured, and the measurement kills it.** Same
member, 1.82 m — the FIRST infeasible span, the only one where a proof would
actually pay:

| budget | outcome | iterations |
|---|---|---|
| 15 min | wall-time | 176 |
| 60 min | wall-time | **677** |

Four times the clock, no certificate, and the dual side blew up doing it:
`inf_du` reached **3.6e+16** and `inf_pr` went BACKWARDS over the last 25
iterations (−0.134). The trace's verdict changed accordingly — *"dual blow-up:
the multipliers diverged while the primal side sat still. Stuck, not slow — more
clock buys nothing"* — which is §14.5.7's finding reproduced on a different
member of a different aircraft.

So the 1.70 m proof was **luck of that geometry**, not something a longer budget
generally buys. `FLATNESS_TIMEOUT_MIN` stays at 20: raising it would spend real
minutes on every sweep chasing a certificate that does not arrive where it would
be worth anything.

One thing did change at 60 minutes: the dominant violation flipped from lift
equilibrium to **`usable_nose / motor["length"] >= 1.0`, by 1.21e-01**. That is
the third independent appearance of that row — the chord-cap corner (§5), the
2026-08-07 battery's five-of-six failures, and now the deepest flatness corner.

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
| stage F | 5 of 6 flatness spans unmeasured |
| the greedy chain | §6.2 — cheap, not done |
| `usable_nose` | §5 — the row that actually blocks this aeroplane |
