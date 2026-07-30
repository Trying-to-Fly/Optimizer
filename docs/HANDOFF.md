# HANDOFF — Plane Optimizer (updated 2026-07-30, eleventh session)

**Champion still 134.5 min** (`runs/20260729T203143-...`) — no physics changed.
This was a **solver-robustness** session and it ended with an answer:

> **The three solves that have failed every run since M4.8 are INFEASIBLE
> CORNERS, not solver defects.** `motor_mount = pusher` cannot meet the 0.08
> static-margin floor; `span = 1.5 m` contains no aircraft at all. Four real
> defects were found and fixed on the way there, and every one of them was
> *masking* this rather than causing it.

Practical consequences: **puller is now vindicated on merit**, not retained by
default — pusher returns 106.55 min even with the stability window relaxed to
0.05, against puller's 119.89 at 0.08. And **do not raise
`SOLVE_TIMEOUT_MIN`**; the 60-minute pusher run proved more clock buys nothing.

FINDINGS §14.5 carries the full chain, including three intermediate diagnoses
that were tested and refuted — read those before re-deriving them.

## FIXED this session

- **The model was being evaluated outside its own variable bounds.**
  `detect_simple_bounds` was at CasADi's default `False`, so every declared
  bound was an ordinary constraint row — and an interior-point method may
  violate constraints on the way to a solution. Row 72 of `g` (the row §13 saw
  going NaN) is `L == W`, the first row after 36×2 bound rows. Now `True`.
- **One real unguarded NaN, inside the box.** `fuselage.boom_body`'s exposed
  length is a difference of four design variables held positive only by the
  100 mm clearance constraint; where that is violated `aero.body_cd0` forms
  `(negative Re)**0.2`. 23 of 600 random in-box points produced a NaN; after
  `geometry.smooth_floor`, 0 of 1500. This is why the symptom lived in the
  PUSHER solve specifically — that mount hangs the motor off the boom tip and
  drives the optimizer against the short-boom bound.
- **Failure messages no longer truncate the diagnosis.** `str(e)[:120]` cut
  CasADi's assertion exactly before `return_status is '...'`. Failures now
  record `return_status` + `iter_count` — which is the only reason issue 1
  below could be reclassified at all.
- **Per-solve wall-clock cap** — `SOLVE_TIMEOUT_MIN = 30`, `--solve-timeout-min`,
  and a field in the GUI's New Run dialog. IPOPT's `max_wall_time`, not
  `max_cpu_time`: a 13 GB solve on a 25 GB machine can swap, and it is the
  clock we are protecting.
- **One static-margin estimator.** The NLP used 3 alphas and the re-evaluation 5;
  those are different quantities on a nonlinear Cm(CL) and differed by ~0.002.
  Plus `sm_in_range` compared an ACTIVE constraint exactly, so the NLP's own
  0.07999999 failed its own test — now a 1e-4 tolerance, the same convention
  `stall_ok` already used.
- **Constraint scaling.** Spar stress was compared in pascals and the Reynolds
  floors in Reynolds numbers, against rows of order 1e-2 elsewhere. Both are now
  dimensionless ratios. `inf_pr` at iteration 0: 5.16e+07 → 5.63. See issue 1.
- **Where the time went** is now in `run.json` (`diagnostics.phase_minutes`) and
  in the report, instead of being reconstructable only from the progress log.
- **Full UIUC ingest** (old issue 9): 661 prop tables ship, 218 of them measured,
  71 folding. Three data bugs found by doing it — see issue 6 below.
- **A failed member now names the constraint it missed.** `SolveFailure` carries
  the worst violations at the last iterate, each labelled with the source line
  that created it, into `run.json` under `violations`. Verified on the real
  model: 115 of 115 rows labelled. This is what turns "failed to converge" into
  "sm >= 0.08, short by 8.3e-03".
- **Pause and resume a battery** — `--checkpoint DIR` and `--pause-file FILE`,
  plus a Pause button in the GUI. Creating the pause file stops the run at the
  next member boundary; every finished member is on disk, so re-running the same
  command continues instead of restarting, and the process exits so all ~13 GB
  is released.

  **Member boundaries are a physical limit, not a shortcut.** A solve in flight
  is a CasADi graph plus IPOPT's barrier, filter and MUMPS state, none of it
  serialisable through CasADi — freeing the memory necessarily destroys the
  solve. The most that could be salvaged is the current iterate as a warm start,
  and warm starts are already measured as a wash on this model (issue 5). So the
  wait is at most one member (30 min) and it loses nothing, where an instant
  pause would free the same memory and throw the solve away.
- **Default test suite: ~20 min -> 61 s** (`slow` marker on the two end-to-end
  render tests). Full suite **190 tests**, green.

## OPEN ISSUES, highest value first

### 1. RESOLVED — the corners are infeasible (kept for the evidence trail)

This replaces the previous issues 2, 3 and 4. The three solves that have failed
every run were re-run with every fix above in place. **They all still fail, and
they fail identically:**

| solve | before | after |
|---|---|---|
| flatness `span = 1.5 m` | opaque assertion, up to 172 min | `Maximum_CpuTime_Exceeded` after **228 iterations**, 32.2 min |
| `motor_mount = pusher` | opaque assertion + 52 NaN warnings, ~50 min | `Maximum_CpuTime_Exceeded` after **222 iterations**, 31.9 min |
| `printed_mass_x1.10` | opaque assertion, three runs running | `Maximum_CpuTime_Exceeded` after **216 iterations**, 31.9 min |

Three independent perturbations, ~225 iterations each, and **never
`Infeasible_Problem_Detected`**. The NaN was real and is gone; it was not the
cause. So the iteration trace this called for was run — and it found two things.

**Half of it turned out to be scaling, and that half is now fixed.** IPOPT opened
the solve at `inf_pr = 5.16e+07`, because `spar_constraints` compared stress in
**pascals** (~1e8) against its allowable while `Cm == 0` and the Vv floor are
~1e-2 — a constraint vector spanning ten decades. Those rows are now
dimensionless (`stress/allowable <= 1`, `Re/Re_min >= 1`; same feasible set).
Measured: `inf_pr` at iteration 0 **5.16e+07 → 5.63**, iterations 228 → 194.
Worth having regardless — that row dominated *every* solve, not just the failing
ones. **Write new constraints dimensionless.**

Regression-gated: the nominal solve on the rescaled constraints returns
`Optimal Solution Found` in **16 iterations / 126 s**, objective **119.89 min**,
against the 2026-07-29 run's 119.89239 at the same configuration — the same
optimum to five significant figures, as it must be.

**The other half is a degenerate active set, and it is still open.** With the
primal side fixed the real signature shows:

| | baseline | rescaled |
|---|---|---|
| `inf_pr` at iter 0 | 5.16e+07 | **5.63** |
| `inf_du` at the end | 5.78e+01 | **8.08e+04** (peaks 1.76e+12) |
| `lg(mu)` | reaches −6.1, rebounds to +3.4 | never below −5.9, ends at 0.0 |
| median `alpha_pr`, last 60 | 2.5e-03 | **2.9e-04** |
| mean / max backtracks | 2.4 / 6 | **6.0 / 14** |

The iterates stay **feasible** (`inf_pr` ~1e-1) while **dual** infeasibility
diverges twelve decades and the line search collapses to α ≈ 1e-5. Bounded primal
residual with unbounded `inf_du` means the **Lagrange multipliers do not exist** —
the active constraint gradients have gone linearly dependent (LICQ failure).
There is nothing to converge to, which is also why the solver never calls it
infeasible: the design is feasible, it just cannot be certified optimal.

**That SVD was run, and it named the pair.** 60 iterations to reach the
degenerate region, then the singular values of the 7×36 active-row Jacobian:

    2.060e+00  1.000e+00  5.707e-01  2.278e-01  1.472e-01  5.223e-02  0.000e+00

Exactly rank-deficient, and the null direction has two contributors:

    +0.874 · g[0]    span's own LOWER BOUND          (slack exactly 0)
    -0.486 · g[72]   subject_to(dv["span"] == 1.5)   (the `fixed` dict)

`aircraft.py:370` declares `"span": (1.5, span_cap_m)`; the sweep is
`np.linspace(1.5, span_cap, 6)`. **The first member pins a design variable at its
own lower bound with an equality** — the same constraint twice. LICQ violated by
construction, multipliers non-unique, `inf_du` unbounded. Exactly the signature.

Worth fixing on its own:

1. **Apply `fixed` as a bound, not an equality row** — a held variable should get
   `lower_bound = upper_bound = value` (one constraint, not two). Needs `fixed`
   plumbed into `aircraft.design_variables` rather than applied afterwards in
   `_solve_nlp`. Framework-level: *any* `fixed` value landing on a declared
   bound hits this, not just span.
2. **Don't sample a sweep exactly on a bound** — `linspace(1.5, …)` exposed it.

**But that pair is NOT why the family fails — this was checked, not assumed.**
The same solve at `span = 1.55 m`, off every bound:

    Maximum_WallTime_Exceeded after 183 iterations (27.6 min)
    inf_pr  5.29e+00 -> 7.06e-02      inf_du  3.21e+00 -> 1.11e+15
    lg(mu) never below -5.9   alpha_pr median 8.6e-04   backtracks max 15

Worse dual divergence than at 1.5 m. So the exact-zero singular value is real but
incidental; the degeneracy is present across the short-span family, which is also
what `pusher` and `printed_mass_x1.10` (no `fixed` dict at all) already implied.

The "degenerate active set" reading is wrong as well — the same SVD at
`span = 1.55 m` found **one** active row (the `span == 1.55` equality itself), so
LICQ holds there, and `inf_du` still hits 1e15.

### ROOT CAUSE: the objective has a pole inside the search box

`mission/endurance.py` is `E_usable * 60 / (P_elec + P_avionics)`, so the
gradient goes as `1/p_total²` — and `P_elec` is tied to anything physical only
through `thrust == drag`, an **equality the solver is entitled to violate while
iterating**. Sampling 3000 points inside the declared variable box:

| | |
|---|---|
| `P_elec` range | **−109.3 W** to +867.3 W |
| `p_total ≤ 0` | **703 of 3000 (23.4% of the box)** |
| objective range | −2.6e+04 to **+5.5e+04 min** |
| ‖∇objective‖ near the pole | **2.4e+07** |

A quarter of the box sits past a singularity, and `p_total → 0⁺` sends endurance
to `+∞` — an unbounded ascent direction that is not an aircraft. That accounts
for all of it: `inf_du` spiking to 1e16 *and coming back* (huge gradient within a
watt of the pole, ordinary away from it — degeneracy would not recover), the line
search collapsing trying to cross it, feasibility never being the problem, and
the champion converging because it starts well away and stays there.

**FIXED.** `Objective` now carries an optional `nlp_surrogate` (always
minimized) beside its reporting `evaluator`, and `solve._solve_nlp` forms the
solver's objective through the single seam `nlp_expression()`. Endurance declares
`p_total`: for fixed usable energy, maximizing `E·60/p_total` is exactly
equivalent to minimizing `p_total` where `p_total > 0`. Reported values are
unchanged (nominal returns the same 119.89 min / 2.0000 m / 1834.9 g digits).
`tests/test_objectives.py` pins the monotone claim.

It worked — on the dual side, and only there:

| `span = 1.5 m` | with the pole | pole removed |
|---|---|---|
| `inf_du` at end | 8.08e+04 | **1.10e+01** |
| `lg(mu)` at end | 0.0 (stalled) | **−2.5** (descending) |
| median `alpha_pr` | 2.9e-04 | **1.5e-03**, max 1.0 |
| restoration iterations | 0 | **33** |
| `inf_pr` minimum | 9.12e-02 | 8.79e-02 |

### …and the remaining obstruction is PRIMAL — the original guess was right

With the dual side healthy, `inf_pr` floors (~0.09 short-span, ~7e-03 pusher) and
IPOPT drops into feasibility restoration. It cannot reach a feasible point. That
vindicates the 2026-07-29 "over-constrained corner" hypothesis, which was
invisible under two layers of numerical noise (a 5e7 scaling artefact and a
1e7-gradient pole) that had to be removed before it could be seen.

**And it is stuck, not slow.** Pusher looked like the best "needs more clock"
candidate; given 60 minutes it ran **474 iterations** (2.5x) and got no closer —
`inf_pr` min 6.73e-03 against 8.18e-03, `inf_du` drifting up to 1.35e+04, 29
restoration phases. **Do not raise `SOLVE_TIMEOUT_MIN`**; 30 min is right and the
cap is doing its job.

**ANSWERED.** At the pusher's last iterate the dominant violation is
`sm >= 0.08` sitting at 0.07170 (2.5x the next-largest), with a well-conditioned
active Jacobian (cond 14.7 — so no degeneracy). Relaxing the floor settles it:

| case | SM floor 0.08 | SM floor 0.05 |
|---|---|---|
| `motor_mount = pusher` | timeout at 25 AND 60 min | **CONVERGED, 5.7 min**, 106.55 min, SM exactly 0.050000 |
| flatness `span = 1.5 m` | timeout, 199 iters | **`Infeasible_Problem_Detected`**, 131 iters |

Pusher cannot make the mission's stability window; span 1.5 m holds no aircraft
even with that window opened. Both are answers, not bugs.

`motor_mount` is therefore **settled**: puller wins on merit (119.89 at SM 0.08
vs pusher's 106.55 at a *relaxed* 0.05), and FINDINGS §10's adoption stands.

**Now shipped so this never needs a bespoke script again:** a failed member
records the constraints it missed, each labelled with the source line that made
it, under `violations` in `run.json`. Plus:

    uv run python tools/degeneracy.py --mount pusher --iters 150
    uv run python tools/parse_trace.py <ipopt.log>

**The one open question is a design decision, not a defect:** the flatness sweep
samples `linspace(1.5, cap, 6)` and the low end is infeasible, so it spends
~30 min per member asking a question with no answer. Either start the sweep above
the feasible floor, or let a member that reports `Infeasible_Problem_Detected`
mark the rest of that tail infeasible and stop.

### 2. Static margin: the estimator is fixed, the FIDELITY is not

The two-estimator artefact is gone. What remains is real and unchanged:
`sm_local_slopes` goes NEGATIVE at the cruise alpha, i.e. Cm(CL) is nonlinear
enough over ±2° that "the" static margin depends on the window you measure it
over. A regression slope is a defensible summary of that, but it is a summary.

flow5 (or equivalent) should still own the stability verdict before anything is
built. Do not "fix" it by widening the mission window.

The build document now states the verdict outright — whether the CG target is
inside the window it derives — instead of printing two millimetre numbers and
leaving the reader to subtract.

### 3. M5.3 two-stage discrete studies — now clearly worth building

The cheap screen predicted the 11x10's full re-solve to within **1 min**
(screen 134.5, re-solve 133.5). That is the evidence this was waiting on: a
screen through `propulsion.solve()` at the incumbent operating point is a
reliable shortlister, so a study can search hundreds of candidates and
full-re-solve only the top N. EXECUTION_PLAN section 6 has the design.

### 4. Prop shortlist is still capped at 11 in, and the cap costs minutes

`motor_prop` is a flat 190 g point mass and prop ground clearance is unmodelled,
so neither is a function of diameter — which is why candidates are held to 11 in.
Larger measured folders screen materially better: **12x10 at 143.1 min**, 14x9 at
141.7, 13x11 at 139.9, against the adopted 11x10's 134.5. Removing the cap needs
a diameter-dependent motor+prop mass and a clearance rule, THEN a wider list.

### 5. Warm start is a wash — do not bother, or fix it properly

Solve times warm 3.9/6.1/9.1 min vs cold 4.6/5.5/9.9 the run before. No
meaningful gain, as predicted: IPOPT is an interior-point method and this
champion sits on many active bounds (span cap, c_root, cs_frac, SM floor, Vv
floor, both spar limits), so the solver pushes off the constraint boundary at
startup regardless of the seed. Either drop `--warm-start` from normal use or
investigate IPOPT's actual warm-start options (`mu_init`, `warm_start_init_point`,
bound_push/bound_frac) rather than only seeding primal values.

### 6. Smaller items

- **UIUC ingest is COMPLETE** (2026-07-30): all four volumes, 1750 files (4 dead
  links), 218 propellers fitted, 71 folding, 661 tables shipping in total. Every
  one of the 70 previously committed fits is byte-identical, and the sample
  aircraft's shortlist is an explicit list of 5 `uiuc_ancf_*` keys, so nothing
  in any solve moved. Three data bugs surfaced by doing it, all fixed:
  - **Volume 2 states some sizes in MILLIMETRES** ("130 mm X 70 mm"). The size
    regex required inches and failed silently, and because a size heading is
    carried forward until the next one, four propellers inherited a
    *neighbour's* diameter — which propagates into `re_coeff` (~ D²).
  - **`kpf` was labelled "Kyosho PF"**; the volume-2 page's own heading reads
    **"KP / Folding"**. A folding line was shipping as fixed. Four other
    prefixes (`ef`, `mi`, `mit`, `pl`, `vp`) had no mapping at all and came out
    as manufacturer `unknown` — which also makes `folding` unreachable, since
    it is keyed on (manufacturer, series). The ingester now WARNS on an
    unmapped prefix instead of shipping it quietly.
  - **`apcsp_9x6` and `gwsdd_9x5` were tested in BOTH volume 1 and volume 2**,
    and the fit file is named from the stem, so the second campaign silently
    overwrote the first. Keys are now deduplicated with a `_v<n>` suffix; the
    first volume to carry a stem keeps the plain key, so no existing key moved.
- **UIUC Reynolds is estimated**, not tabulated (`re_estimated: true`): c_75 is
  taken as 0.0638 x D, the ratio APC's own tables imply. The FIT is unaffected
  (a wrong constant is absorbed by the stored normalisation) but the REPORTED
  Reynolds is good to roughly +/-20%.
- **Volume 2 coverage is partial by construction.** The manifest only sees files
  matching `<prefix>_<D>x<P>_`, so blocks named otherwise (Crazyflie, DA40xx,
  NR640, Union, KP's non-size headings) are skipped entirely. 219 propellers of
  a larger database. Not corruption — every fitted prop's filename size
  reconciles with its recorded size — but not "the whole DB" either.
- **CF boom is invisible in the viz twin** (no loft), cosmetic, long-standing.

---

# Earlier: tenth session, first half (data ingest)

**Tenth session (2026-07-29) — measured folding-prop data, and a hurried stop.**
Session ended abruptly; read this section before touching anything.

## Test suite: green (158 passing)

The four tests that briefly failed on 2026-07-29 asserted the OLD prop design and
were updated to the new intent, not loosened:

- `test_incumbent_powertrain_is_unchanged` now pins the incumbent to
  `uiuc_ancf_11x6` at derate **1.00**, and says why the spec plane was ALLOWED to
  move: a measured folding table already contains the folding penalty, so the
  rigid-blade proxy derate on top charged it twice.
- `test_prop_candidates_differ_only_in_pitch` scales to the candidate count and
  now also asserts every candidate is `folding` AND `measured` — the blade-section
  confound that existed while the 11x6 rung was an APC sport blade is gone.
- `test_installation_effects_declared` expects 1.00 (puller) and 0.95 (pusher):
  with the blade derate at 1.00 what remains in that product IS the mount effect.
- `test_no_synthetic_tables_ship` accepts UIUC provenance. UIUC is wind-tunnel
  measurement, so it passes by being more trustworthy than APC's simulation
  output, not less. The thing the check exists to catch — the retired
  `apc_11x6_blend` pitch interpolation — is still caught.

## What landed

- **70 measured FOLDING propeller tables** from the UIUC Propeller Data Site,
  fitted through the same `CT(J,Re)` core as the APC tables
  (`tools/ingest_uiuc.py`). 513 tables ship now (443 APC + 70 UIUC). All 70 are
  complete — `files_used == files_total` on every one.
- **These are the props this aircraft was always modelling.** `PROP_CANDIDATES`
  named `aeronaut_cam_11x6_folding` and approximated it with an APC rigid table
  times a flat 0.95. It is now `uiuc_ancf_11x6`, measured, `blade_derate = 1.00` —
  the folding penalty is in the data, and the proxy derate on top charged it
  twice. **At the SAME nominal prop that swap is worth +9.4 min** (measured CAM
  11x7 = 127.7 min vs rigid-proxy 11x7 = 118.3 at the champion's operating point).
- `powertrain()` now takes **diameter and blade derate per candidate**.
- Shortlist widened to 5 measured CAM folders, 11x6 / 7 / 8 / 10 / 12. The screen
  at the champion's operating point puts **11x10 top at 134.5 min**, with 11x12
  falling back to 129.0 — matching AIAA 2020-2762's finding that CAM gains
  continue only to p/D ~0.8-1.0.
- Earlier in the session: straight tail TE, `--warm-start`, the build document.

## WHY THE SHORTLIST IS STILL CAPPED (open question — the user challenged this)

The user asked, fairly: "why are we capping the prop choice again?" Two caps,
both mine, both interim rather than principled:

1. **11 inch only.** The 190 g `motor_prop` point mass and the prop ground
   clearance both assume an 11 in prop, and NEITHER is modelled as a function of
   diameter. Larger folders screen materially better — **12x10 at 143.1 min**,
   14x9 at 141.7, 13x11 at 139.9 — so this cap is costing real minutes. Removing
   it needs `motor_prop` mass as a function of diameter plus a clearance rule,
   not just a longer candidate list.
2. **5 candidates.** Each discrete candidate is a full NLP re-solve (~5 min), so
   all 70 folding props would be ~6 h of solving for the prop study alone.

**The real fix for cap 2 is M5.3** (two-stage discrete studies, EXECUTION_PLAN
section 6): screen every candidate cheaply through `propulsion.solve()` at the
incumbent operating point, then full-re-solve only the top N. That turns 70
candidates into ~5 solves and makes the cap unnecessary. It is NOT built.

## ~~NOT DOWLOADED~~ — the rest of the UIUC database

> **RESOLVED 2026-07-30.** The full four-volume ingest is done — see the current
> session's issue 8. The table below is the state as it stood on 2026-07-29.

Only the folding families were fetched and fitted, at the user's request
(they had to leave mid-session).

| | props | data files |
|---|---|---|
| UIUC total | 219 | 1750 |
| **folding — fitted and shipped** | **70** | 548 |
| **non-folding — NOT fitted** | **149** | 1202 |

Missing families: APC Thin Electric x34, APC Sport x32, GWS Direct-Drive x14,
APC Slow Flyer x11, Graupner Super Nylon x10, Master Airscrew (plain) x9,
Master Airscrew Scimitar x8, GWS Slow Flyer x8, Kyosho x5+1, Master Airscrew
Electric x3, APC Free Flight x2.

`data/props/_uiuc_cache/` holds 1004 files (gitignored), so a lot of the
non-folding data is already on disk. To finish:

    uv run python tools/ingest_uiuc.py --fetch          # all volumes
    uv run python tools/ingest_uiuc.py --fetch --only-folding   # folding only

It resumes from cache and skips what is present. **Fetch politely** — 8
concurrent workers got this client TLS-blocked at the edge for ~40 minutes, on
both hostnames, with no HTTP fallback. The tool is now sequential and paced
(0.4 s) and does volume 3 first. The block cleared only when the user switched
VPN exit; it is not something to trigger again.

Worth knowing: the non-folding UIUC props would mostly DUPLICATE APC coverage —
but as wind-tunnel MEASUREMENT rather than APC's simulation output. That is a
fidelity upgrade for the fixed-blade candidates, not just more rows.

## Next run

Not started. It should be `--warm-start` from
`runs/20260729T092108-endurance_sample-vtail_sample_v1-6`, with the folding-only
shortlist above. Fix the 4 tests first.

---

# Earlier: HANDOFF as of 2026-07-29, ninth session

**Ninth session (2026-07-28) — the prop model, rebuilt.** Started as "summarise
the last run", became a correctness fix. Read `FINDINGS.md` §11 first; it is the
substance. Short version:

- **The 2026-07-27 run's +11 min was a prop swap, not wing v4.** `prop_choice`
  was freed as a discrete study the same day the wing changed; the study picked
  the 11×7 over the incumbent 11×6, and +10% chain efficiency at flat mass and
  flat L/D accounts for the entire gain. Wing v4 is still **unpriced**.
- **The prop fit was wrong where it mattered.** `CT(J)` over a hardcoded
  3000–10000 rpm window carried **6.9% efficiency error** in the sample plane's
  own cruise band. Replaced with **`CT(J,Re)` / `CP(J,Re)`** (MODEL_DETAILS
  §2.1.1) — Reynolds reconstructed from the operating point via one stored
  per-prop constant, so there is no window to choose and the model works for a
  5″ prop and a 22″ prop alike. Same band: **0.36%**. Numeric and CasADi paths
  verified identical; Jacobian finite across the table.
- **The whole APC catalogue ships: 443 fitted tables** (was 3, one of them
  synthetic). `tools/ingest_props.py --fetch` pulls the ~8 MB published archive
  and fits everything; the 67 MB of raw `.dat` stays out of git
  (`data/props/_apc_cache/`). New `planeopt props [match] [--detail]` lists them,
  and `planeopt info` now prints a count instead of 443 names.
- **`apc_11x6_blend` retired** (user decision): it was a pitch interpolation, the
  only non-measured candidate in the study that ranked it last. Real APC 11×6
  replaces it and has 11% more usable advance ratio than the blend predicted.
  New caveat, recorded in `PROP_CANDIDATES`: the real 11×6 is a thicker **sport**
  section, so blade section is now a confound against its thin-electric
  neighbours.
- **Deferred at user request (2026-07-28): motor + battery as tunable
  parameters** — logged as M6 in `EXECUTION_PLAN.md` §6, with the reason it is
  deferred (hardware already on hand) and the coupling that matters when it is
  not (Kv sets the rpm the prop must turn, so motor and prop want a *joint*
  study, not a sequential one).
- Tests: `tests/test_propulsion.py` new (Reynolds law, numeric==symbolic,
  finite Jacobian, monotonic CT, catalogue fit-quality bar);
  `tests/test_packaging.py` gained a no-synthetic-tables guard and a
  did-you-mean check.
- **Build document (`report/manufacturing.py`, new).** Every run now writes
  `manufacturing/BUILD.md` + CSVs: CG target and the allowable window, mass
  budget, surfaces, control-surface hinge lines, LE/TE polylines, and — via the
  aircraft's new `manufacturing(dv, auw_kg)` hook — spar stock, lengths and
  as-built stress/deflection margins, plus a cut list. `planeopt build` re-renders
  it. It fixed one thing on contact: `run.json` now records
  `constraints.static_margin_range`, without which the CG window cannot be
  derived from a run at all. Surfaces are read off the **airplane** rather than
  the run summary, which is what caught the next item.
- **Bug found and fixed: rebuilding a champion lost its discrete choices.**
  `planeopt build` rebuilt from the design vector alone, which silently gave the
  aircraft file's DEFAULT tail type, topology, mount, prop and winglet — so a
  regenerated build document grew a **winglet the champion had rejected**. The
  in-run path was always correct (it passes the analysed airplane). Fixed with
  `report/assemble.champion_config()` / `as_champion()`, and `run.json` now
  records `champion.discrete`; older runs are recovered from the study blocks.
  (Note for anyone reading an earlier draft of this file: the claim that
  `run.json` "omits the winglet" was WRONG — `n_wings: 2` is correct when the
  winglet study rejects it, which it does.)
- **Re-solved — see FINDINGS §12.** The 2026-07-29 battery (505.8 min, 2-wide)
  is the first champion under `CT(J,Re)`: **118.3 min**, same airframe as the
  2026-07-27 run to 0.1 g, so the −5.3 min is purely the fit that was flattering
  the prop. **The prop verdict survived losing the blend** — against the REAL
  11×6 the 11×7 still wins, by +9.7 min, so §11's confound did not change the
  conclusion. Winglet rejected again (−0.78), V-tail/pod-boom/smooth-curve all
  held. **Wing v4 is worth nothing measurable** — same L/D as the v3-era
  airframe; it is a better parameterization, not a better wing. FINDINGS §1–§10
  are still quoted under the old prop fit.
- **Two solves failed to converge** in that battery (`motor_mount: pusher`, and
  the `printed_mass_x1.10` re-solve) — both IPOPT assertions at the tight span
  cap, and the pusher failure means the mount was retained by DEFAULT, not by
  winning. The same `printed_mass_x1.10` member failed in M4.8. Worth a look.
- **Static margin crossed its floor for the third champion running** (0.0787 vs
  0.08, `sm_in_range: false`). That is now a standing estimator defect, not a
  one-off.

---

# Earlier: HANDOFF as of 2026-07-26, eighth session

**Eighth session (2026-07-26) — RAM budget + wing architecture v4.** Three
user asks, all implemented; NO champion run has been made yet, so every number
below is still the M4.8 champion's.

- **Memory budget (`src/planeopt/memory.py`, new).** `optimize
  --memory-budget-gb N` / a "Dedicate memory" control in the GUI's New Run
  form. The honest framing, which the docs and the UI both state: more RAM does
  NOT make a solve faster — a solve is single-core and memory-bound — it decides
  how many independent solves in a batch run side by side, i.e. it is a
  friendlier `--parallel`. Width = budget / measured per-solve peak. Runs now
  RECORD `diagnostics.peak_rss_gb`, and later budgets divide by that measurement
  instead of the folklore 13 GB. Overshooting free RAM warns rather than clamps
  (swap is real, peaks are transient, and a dial that silently refuses to move
  is worse than no dial); the hard ceiling is physical + swap. On this box
  (25 GB + 10 GB swap) the dial is effectively a 1-vs-2 switch — `planeopt
  info` now prints RAM, the measured peak, and the max achievable width.
  Stdlib only, no psutil: the frozen Windows build stays clean.
- **Wing architecture v4 (MODEL_DETAILS §9, rewritten).** Planform went
  SMOOTH, dihedral may go PIECEWISE — see §9 for the full rationale.
  `r1`/`r2`/`r3` and `center_width` are retired; `taper`, `fullness`,
  `le_shear` and `eta_break` replace them. A rectangular wing (λ=1) and a
  straight taper (a=1) are EXACT members — that was the user's explicit
  requirement. `le_shear` spans straight-LE / straight-c4 / straight-TE as one
  continuous variable instead of three discrete cases. New discrete study
  `wing_dihedral_form: [curve, polyhedral2]`, outer cant free to 60°, with the
  16 g/side joiner block charged back so the kink pays for itself.
- **Watch this in the next champion run:** v3 converged to `d_exp = 0` with
  spar-fit inactive, i.e. the dihedral *distribution* is a flat direction. A
  mild polyhedral will land on the same uniform answer; the result worth
  reading is the hard-canted one, where the mechanism is induced drag at the
  span cap (a blended winglet made of wing) rather than dihedral at all.
- **Airfoils are now reported** per surface in run.json, report.html and the
  design brief, read off the built airplane rather than the declared attribute
  (it is a discrete outer-loop candidate, so it can differ per run).
- Costs held flat on purpose: still 4 panels / 5 xsecs, so the CasADi graph,
  solve time and 13 GB peak are unchanged from v3.
- Tests: `tests/test_memory.py` (16) new, `tests/test_wingcurve.py` rewritten
  (24). Full fast suite 113 passing. A 384-corner sweep of the wing variable
  bounds confirms a NaN/Inf-free Jacobian in both dihedral forms.
- **Not done:** no optimize battery has been run on v4 — FINDINGS still
  describes v3 geometry. `aircraft/speed_sample/` (uncommitted, from the
  in-flight max-speed work) still carries its own v3-style wing and was
  deliberately left alone.

---

# Earlier: HANDOFF as of 2026-07-25, end of seventh session

**M5.1 desktop GUI — done (seventh session, same day as packaging).** User
decisions: a native PySide6 desktop app (not the web UI the plan sketched),
first slice = run browser + mission form, sequential queue.

- `planeopt gui` opens it; `src/planeopt/gui/` holds it. The Qt-free modules
  (`runindex`, `missionfile`, `jobs`) carry the logic and are tested headless
  (`tests/test_gui.py`, 16 tests) — widget layout is verified by running the
  app, not by asserting on pixels.
- Browsing reads run.json only. Runs execute as **subprocesses of the same
  CLI** (`python -m planeopt ...`, or the exe itself when frozen): a 13 GB
  solve that the OOM killer takes kills one job, not the GUI, and cancel is a
  kill rather than a cooperative interrupt.
- The mission is a real form because MissionSpec is pure data; it round-trips
  through actual `missions/*.py` files so runs stay reproducible and the
  `inputs/` snapshot keeps working. **The aircraft is a picker, not an
  editor** — see M5.2 in EXECUTION_PLAN §6 for what a real aircraft form
  would require.
- PySide6 is the optional `gui` extra (`uv sync --extra gui`), and
  `pyside6-essentials` deliberately — the `pyside6` meta-package drags in
  WebEngine/3D/Charts for nothing. `planeopt info` reports whether it resolved.
- Verified end to end in WSLg: queued an evaluation, streamed progress, the
  run landed in the list and auto-selected (91.5 min).
- **Packaged-app usability (found by the user trying to open the exe):** a
  console exe cannot be double-clicked into a GUI — Windows opens a console,
  Typer says "Missing command", the window vanishes, and it reads as "does not
  launch". The bundle now ships **two** executables from one Analysis
  (`entry.py` opens the GUI when the running exe's name ends in `-gui`):
  `planeopt.exe` (console CLI) and `planeopt-gui.exe` (windowed). Windowed
  builds have `sys.stderr is None`, so `_setup_logging` skips the handler.
- **Workspace resolution** (`gui/workspace.py`): the GUI used relative
  `aircraft/`/`missions/`/`runs/`, which are meaningless for a double-clicked
  exe — it opened empty and **New run… crashed with FileNotFoundError**. Order
  is now `--project` → remembered (QSettings) → cwd → the executable's folder;
  the build stages `aircraft/` and `missions/` beside the binaries so a
  double-click lands on a working project. `planeopt info` prints the resolved
  folder — ask for that line first if a packaged run list is empty. Verified
  from `C:\Windows`: resolves to `dist\planeopt`, 1 aircraft, 1 mission.


Orientation for a fresh agent picking up this project. Read this, then
`EXECUTION_PLAN.md` (milestones), `MODEL_DETAILS.md` (per-module equations —
§7 fuselage, §8 tail, §9 wing dihedral family), and `FINDINGS.md` (§9 is the
latest champion).

## 1. What this project is

General-purpose small-aircraft MDO app (AeroSandbox/IPOPT): co-optimize
geometry, mass, trim for mission-declared objectives. **Iron rule: the app is
general-purpose.** `aircraft/vtail_sample/` and `DESIGN_SPEC.md` are ONE test
fixture — nothing in `src/planeopt/` may assume its architecture, numbers, or
mission. New features enter as framework hooks + aircraft-declared data.

- Repo: `/mnt/c/Users/M0obo/Desktop/Planes/Plane Optimizer` (Windows mount —
  moved from ~/plane-optimizer at user request; that location is deleted).
- Remote: `https://github.com/Trying-to-Fly/Optimizer.git` (origin/main;
  push after every committed unit).
- `docs/` is canonical. `runs/` is gitignored artifacts.

## 2. Environment hazards (each one has already burned a session)

- **RAM:** one NLP solve peaks ~13 GB. Under the default 15 GB WSL
  allotment, NEVER run two heavy jobs (NLP solve, pytest suite)
  concurrently — the WSL OOM killer takes the whole session down.
  **2026-07-24:** `C:\Users\M0obo\.wslconfig` now grants WSL 26 GB +
  10 GB swap (host has 31.4 GB) — it takes effect only after
  `wsl --shutdown` from Windows (which kills any running session/solve, so
  do it between runs). Once active, `planeopt optimize --parallel 2` runs
  battery solves 2-wide (~halves wall time; solver is single-core, 1 of 16,
  so CPU is never the limit — RAM is). Verify the allotment with `free -g`
  before using `--parallel 2`; at 15 GB it WILL OOM.
  **Since the eighth session, prefer `--memory-budget-gb N`** (or the GUI's
  "Dedicate memory"): it derives the width from free RAM and from the per-solve
  peak previous runs actually measured, rather than asking you to do that
  arithmetic from a folklore figure. `planeopt info` prints all three numbers.
  `--parallel` still wins when given explicitly.
- **uv lock:** `uv run` hangs silently (futex on `.venv/.lock`) when two uv
  invocations overlap on this drvfs mount. Launch background runs with
  `.venv/bin/planeopt` / `.venv/bin/python` directly; while ANY background
  run is alive, never issue a `uv` command (use `.venv/bin/python -m pytest`).
- **Kills:** stop background tasks only via the harness (TaskStop), never
  pkill/group kills.
- **Timing on /mnt/c:** one NLP solve ~5–6 min; full champion battery
  ~100 min; `tests/test_run.py::test_m3_optimize_smoke` runs optimize() and
  cannot finish in 30 min — don't wait on it; the champion run covers that
  path. The other ~40 tests are fast (`.venv/bin/python -m pytest -q
  tests/test_configs.py tests/test_winglet.py tests/test_fuselage.py
  tests/test_shapereview.py tests/test_tail.py tests/test_wingcurve.py`).

## 3. How the user works (important)

Decisions are the user's. Map open modeling/design decisions, present
concrete options with trade-offs and one recommendation (AskUserQuestion
works well), get their call, THEN write docs and code to match. They answer
tersely and expect docs updated. Don't ask about things derivable from the
docs. They care that results look/are buildable (they rejected a boxy
fuselage on sight) and repeatedly stress: nothing arbitrary "fixed in stone" —
lengths, tails, booms are optimizable or enumerable; only genuine discrete
choices (tail type, topology) stay discrete, and even those get priced by
studies rather than assumed.

## 4. State as of this handoff

**Seventh session (2026-07-25) — packaging: the app builds and runs as a
Windows .exe.** No modeling changed; this session made the app distributable.

- **Distribution bug (was live, not hypothetical):** prop tables were resolved
  by repo-root path, so they were absent from any wheel or frozen build — the
  first `PropTable(...)` call would have failed for every installed user. They
  are now package data in `src/planeopt/data/props/` resolved via
  `importlib.resources`, with `PLANEOPT_PROPS_DIR` prepending a user directory
  (that is how an end user adds their own prop). `data/props/` keeps the raw
  APC `.dat` tables and fit plots as source material.
  **Rule:** anything read at run time lives under `src/planeopt/`;
  `tests/test_packaging.py` guards it.
- **Windows portability, all three found by running the thing:**
  `--parallel > 1` is rejected up front (`solve.check_parallel`) because
  workers inherit the aircraft across a fork and Windows has none; every
  artifact write now names UTF-8 explicitly (the report carries eta/Delta/arrow,
  which cp1252 cannot encode — it crashed at the *final* write of a run, and
  `tests/test_packaging.py` now fails any unencoded text I/O); and
  `cli.main` reconfigures stdout/stderr to UTF-8.
- **CasADi in a bundle — two traps, both documented in `packaging/README.md`:**
  (1) PyInstaller hoists `_casadi.pyd` to the bundle root while `collect_all`
  files the 97 DLLs under `casadi/`, so the spec places them at the root by
  hand; (2) plugin loading (`libcasadi_nlpsol_ipopt`, `..._interpolant_bspline`)
  needs the search path set through `casadi.GlobalOptions.setCasadiPath` —
  **the CASADIPATH env var does not work when set from Python on Windows**,
  because libcasadi's C runtime keeps its own copy of the environment made at
  process start (setting it in the shell before launch *does* work, which makes
  this maddening to diagnose). The fix lives in `planeopt/__init__.py` so it
  holds for the future GUI too. Symptom if it regresses: every sweep point
  infeasible.
- **Progress + diagnostics:** solves log through the `planeopt` logger (a
  battery used to print nothing for hours); `--quiet` suppresses. New
  `planeopt info` (install report — ask for it first in any bug report) and
  `--version`. An all-infeasible sweep now raises naming the causes instead of
  `max() iterable argument is empty`.
- **Verified end to end:** `dist/planeopt/planeopt.exe` (428 MB onedir, built
  by Windows Python 3.13 via `packaging/build_windows.ps1`) completes
  `planeopt run` on the sample and writes report.html + interactive_3d.html +
  figures — **numerically identical to the WSL run (91.5 min at 10.5 m/s)**.
  The build script's smoke test runs a full evaluation on purpose: startup
  success proves nothing, since both CasADi traps pass `--version` happily.
- **Not in the exe:** `--parallel > 1`, and STEP import (the `cad` extra is
  ~900 MB and is excluded; `planeopt info` says so). Aircraft and mission
  inputs are still user-authored Python modules even in the packaged build —
  form/GUI input is M5 and is the real gate on "general use".
- Hazard learned: `uv sync` without `--extra cad` silently *prunes* cadquery
  and skips the STEP test. Use `UV_HTTP_TIMEOUT=600 uv sync --extra cad`.
  `.venv-win/` is the Windows build venv and must never be shared with `.venv`.

**Sixth session (2026-07-24) — M4.8 done.** Committed and pushed:

- Span cap 2.2 → 2.0 m (user decision). Motor mount joined
  `discrete_options` (judged first) with declared installation effects
  (MODEL_DETAILS §2.4): pusher prop-in-wake derate 0.95 composed into
  `folding_derate`, puller pod-scrubbing ×1.10 on the pod form factor,
  motor PointMass rides the mount. Aircraft is `vtail_sample_v1.5`.
- **Champion (run `20260724T191453`, FINDINGS §10): PULLER adopted
  (+10.7 min), 112.5 min @ 2.0 m, AUW 1766 g.** V-tail/boom/no-winglet
  all re-confirmed under the puller; simple dihedral again (d_exp → 0).
  Flags: SM re-eval 0.0745 vs NLP 0.080 (estimator gap now crosses the
  window floor — flow5 gate before building); `printed_mass_x1.10`
  battery member failed to converge (first ever; re-run it).
- **Puller adopted as the permanent default** (user decision, same day):
  `motor_mount = "puller"` in the aircraft file (v1.6); the spec pusher
  stays a re-priced candidate every run; the dv=None fixture explicitly
  pins the spec pusher layout (M1 continuity — its powertrain derate is
  back to the original frozen 0.95, since a puller carries no install
  derate).
- **Parallel battery mode** (`optimize(..., parallel=N)` / CLI
  `--parallel`): independent solves per phase run N-wide via fork
  workers (`_solve_many`; per-candidate attrs snapshot at fork; OOM'd
  worker fails only its job). Default 1. §2's RAM rules updated:
  26 GB + 10 GB swap `.wslconfig` is WRITTEN but inactive until
  `wsl --shutdown` — verify with `free -g` before first `--parallel 2`.
- That run took 10 h 53 m sequentially (4 infeasible flatness burns at
  the tight cap + slow tight-cap convergence everywhere). Queued
  speedups: per-solve progress log line, iteration cap for study/flatness
  solves (fail in ~15 min, not 50), first `--parallel 2` battery.

**Fifth session (2026-07-24) — M4.7 done.** Committed and pushed:

- **Generic discrete studies**: `solve.optimize` enumerates any declared
  `discrete_options = {attr: [candidates]}` (fuselage topology + tail type
  both use it; run.json key `discrete_studies`; originals restored in the
  re-eval finally).
- **Tail phase** (MODEL_DETAILS §8): types vtail/conventional/ttail;
  per-dimension vars (t_span/t_c_root/t_taper/t_sweep, t_dihedral or
  fin_*, cs_frac 0.2–0.4); `tail_scale` retired; declared
  `pitch_control_name` threads through trim (no hardcoded "ruddervator");
  throw cap derived from hinge fraction (`trim_deflection_limit_deg` may be
  a callable of dv); declared `v_tail_volume_min = 0.030`; T-tail mount
  mass. Tail AC placed at tail_arm including sweep offset.
- **Wing arch v3** (MODEL_DETAILS §9, user decision): dihedral curve
  δ(η) = dihedral_tip·η^d_exp replaced per-panel d0–d3; straight-spar sag
  fit is a HARD constraint (0.70·t/c usable depth); per-break joiner mass
  deleted; continuous-cant study frees `tip_dihedral_max_deg` (renamed from
  d3_max_deg). CasADi gotcha: never evaluate η^q at η=0 symbolically (NaN
  in the exponent derivative) — z(0)=0 analytically.
- **Champion (run `20260724T052806`, FINDINGS §9): V-tail retained,
  109.3 min @ 2.2 m, AUW 1925 g.** Conventional −5.6, T-tail −8.5, boom
  re-adopted (+4.9), winglet re-rejected (−0.96). Wing converges to
  d_exp = 0 — SIMPLE dihedral (4.1° uniform) wins inside its own family;
  spar-fit inactive at the optimum. Vv floor pulled the V-angle to its 55°
  bound (steep-V handling costs unmodeled — treat the cap as a declared
  practice limit). Balance now via bay stretch (486 mm, battery at 102 mm,
  ballast 0); saddle constraint active (bay end exactly at 60% root chord)
  and visually verified in the three-view. Stall INACTIVE for the first
  time (7.81 vs 8.0) — gust margin sizes the wing. Pod fineness 10.7 is
  outside the shape review's 4–9 band (see FINDINGS §9 note).
- **STEP loader verified for real** (`uv sync --extra cad` done; needed
  `UV_HTTP_TIMEOUT=600`): fixed the station scan (tessellation vertex
  binning collapses on extrusions — now samples triangle-edge crossings at
  station boundaries). `test_step_loader_roundtrip` passes un-skipped.
- Tests: `tests/test_tail.py` (13) + `tests/test_wingcurve.py` (6) added;
  fast suite now `test_configs test_winglet test_fuselage test_shapereview
  test_tail test_wingcurve`. Aircraft is `vtail_sample_v1.4`.
- Known cosmetic gap: three-view/3D artifacts draw only lofted bodies, so
  the CF boom is invisible between pod and tail block.

Fourth-session state (all still true) through `d6f38cf`:

- **M0–M4.6 done.** M4.5 = projected-span cap (2.2 m) + winglet w/
  three-route on/off study (FINDINGS §7). M4.6 = fuselage phase: streamlined
  parametric loft (elliptical nose, Hermite boat-tail, proportion floors
  nose ≥ 1.0 d_eq / boat-tail ≥ 1.8 d_eq), packaging constraints from
  declared component envelopes, emergent boom (pod tail cap → tail block;
  mass + drag from that length), tail_arm freed to 0.40–1.20, topology study
  over a declared list (`fuselage_topologies`).
- **Champion (run `20260723T181336`, FINDINGS §8): 114.1 min @ 2.2 m** —
  fuselage freedom recovered the whole span-cap penalty. Pod pinned at every
  floor (54×70 mm section, nose 61 / bay 310 / boat-tail 111 mm, 482 mm).
  **CF boom adopted (+8.9 min over integrated).** Winglet re-rejected
  (−0.50 min). Multistart spread ~1e-9; NLP-vs-reeval gap ~1e-5.
  tail_arm 519 mm (old 0.55 bound had been binding); tail_scale pinned at
  its 0.70 floor → the tail parameterization is now the binding limitation.
- **CAD round-trip built** (MODEL_DETAILS §7.5): `planeopt brief <run> -a
  <aircraft>` renders `design_brief.md` (declared-data hook
  `design_brief(dv, shadow_per_g)`); `planeopt.cadimport.load_step` (.STEP,
  optional `cad` extra = cadquery, NOT yet installed); `planeopt.shapereview`
  rule checks (nose ≥ 1.0 d_eq, boat-tail ≤ 21°, fineness 4–9, Swet delta
  priced). Loft = recommendation engine; imported STEP = real design.
- Fuselage previews: `runs/fuselage_preview/interactive_3d.html` (champion
  pod + battery) and the run dir's `interactive_3d.html` (full aircraft).
- **Wing-saddle carry-through added AFTER the champion run** (user saw the
  wing floating above the shrunken pod — unbuildable): bay start ≤ LE −
  10 mm, bay end ≥ LE + 0.60·c_root (`pod_bay_end` is now a variable, not a
  fixed anchor), pod top derived as `SADDLE_EMBED − h/2` so it always embeds
  6 mm into the wing root plane (MODEL_DETAILS §7.2). **No champion run
  includes these yet** — the 114.1 min figure predates them; expect the next
  run a few minutes lower (the pod must lengthen to carry the wing). Per the
  user: do NOT rerun for this alone — the tail-phase champion run validates
  it.

## 5. Next work

The tail phase (was item A here) and the wing dihedral-curve rework are
DONE — see §4. Remaining, roughly in order of readiness:

- **BEFORE THE NEXT RUN — properly evaluate the propeller options (user ask,
  2026-07-29).** The 2026-07-29 champion adopted the 11x7E after pricing
  **3 of 443** shipped tables, all at one diameter: `PROP_CANDIDATES` /
  `discrete_options["prop_choice"]` in `aircraft/vtail_sample/aircraft.py` still
  lists only `cam_11x55 / cam_11x6 / cam_11x7` (pitch 5.5, 6, 7 in). That
  shortlist was written when three tables existed and was never widened when the
  catalogue landed.

  A free screen at the champion's operating point (9.5 m/s, 0.823 N) puts the
  adopted **11x7E at rank 119 of 441**:

  | rank | prop | dia | pitch | endurance |
  |---|---|---|---|---|
  | 1 | apc_14x14e | 14.0 | 14.0 | 145.9 min |
  | 2 | apc_11x13ep | **11.0** | 13.0 | 143.4 min |
  | 5 | apc_12x12e | 12.0 | 12.0 | 141.9 min |
  | **119** | **apc_11x7e (adopted)** | 11.0 | 7.0 | **118.3 min** |

  **The lever is PITCH, not diameter** — rank 2 is an 11 in prop, so ground
  clearance and the 190 g `motor_prop` point mass are untouched. This is the
  `J = 0.605` vs peak-eta `J = 0.538` diagnostic that has been in the report for
  two runs: the design has been asking for a coarser prop and the shortlist did
  not contain one.

  Do NOT simply paste 443 candidates into `discrete_options` — each is a full
  NLP re-solve (~5 min here), so that is ~37 h sequential / ~18 h at 2-wide.
  The intended fix is a **two-stage prop study**: screen the whole catalogue
  through `propulsion.solve()` at the incumbent operating point (seconds, no
  NLP), then full-re-solve the top N plus the incumbent. Not built yet.

  **ANSWERED 2026-07-29: the prop does NOT have to fold.** So the shortlist is
  the whole catalogue (~440), not the ~15 folding-family props, and the screen's
  leaders are all fair candidates.

  That answer creates a second job, because folding is currently ASSUMED rather
  than priced: `PROP_FOLDING_DERATE = 0.95` is applied unconditionally to every
  candidate in `powertrain()`. A fixed blade does not pay it, so leaving it on
  charges ~5% of shaft power to props that would not lose it — worth roughly 5%
  of endurance, which is the same order as the whole prop study. Follow
  `aircraft/speed_sample/aircraft.py`, which already has the right shape:
  `BLADE_DERATE = {"folding": 0.95, "fixed": 1.00}` priced as a discrete option
  rather than declared. Do this in the SAME pass as widening the shortlist — the
  two interact, and neither result is readable while the other is wrong.

  Build judgement the model does not see: a non-folding prop on a belly-landing
  airframe is a prop you break on landing. That is the user's call, not the
  optimizer's, and it is why the original shortlist was a folding family.

  Trust the direction, not yet the magnitude: the screen holds the airframe
  fixed, and the leaders sit at ~15% throttle (2.2 V of a 14.8 V bus) where the
  flat 0.95 ESC efficiency and the vendor motor constants are least trustworthy
  (MODEL_DETAILS 2.3). A re-solve would re-optimize around the coarser prop and
  probably widen the gap rather than close it.

- When the user delivers their SolidWorks .STEP: wire the imported-fuselage
  NLP mode — `ImportedShape.body_dict` feeds the existing bodies contract;
  two scale variables (length, cross-section) with Swet/volume fitted smooth
  over a small scale grid (volume scales exactly as sx·syz²; fit Swet);
  scales pinnable to 1. Run the shape review + report both in the run
  artifacts. Note the fineness-band tension first (FINDINGS §9): the
  champion pod is f = 10.7 vs the review's 4–9 band — decide with the user
  whether to widen the band or constrain fineness in the NLP.
- Small items worth folding into any next code session: draw the CF boom in
  the viz twin (cosmetic gap, §4); consider whether the 55° V-angle cap
  deserves a declared handling rationale in DESIGN docs.
- Optional warm-start flag (`--warm-start <run dir>` reading champion dv as
  inits) — only worth it for speed; multistart agreement is already perfect.
- Release polish, if the .exe is to go to anyone outside: no LICENSE file
  exists yet (a user decision); the binary is unsigned, so Windows SmartScreen
  will warn on first run; and no `optimize` battery has been run inside the
  frozen build (the smoke test covers `run`, i.e. the M1 pipeline and IPOPT —
  a full battery is hours and was not re-run for packaging alone).
- Queued far-field: XFOIL spot-check AG35 vs SD7037 (FINDINGS §6), user
  slicing parts → `tools/fit_profile.py` mass calibration, M5 GUI.

## 6. Known gaps / caveats to carry forward

- VLM winglet cross-check degenerated at the high-dihedral champion
  (negative inviscid CD0, e_proj > 1) — the 3-point quadratic fit needs more
  alphas or a better regressor before it's quantitative again.
- All absolute minutes are uncalibrated (construction + propulsion);
  rankings and active constraint sets are the trustworthy outputs.
- Chain efficiency ±10% swings the objective ±10 min — dominant uncertainty.
- `structure_extras`/`fixed_equipment` in the sample still carry a few spec
  station constants (servo positions etc.) — fine for the fixture, but keep
  them out of framework code.
- Session memory files exist under the Claude project dir and mirror much of
  this; this file is the canonical handoff.
