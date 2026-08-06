# HANDOFF — Plane Optimizer (updated 2026-08-06, seventeenth session)

> ## THE SPAN CAP IS BACK AT 2.0 m (user decision, 2026-08-04)
>
> The 3 m experiment ran, the curve turned over at **2.497 m interior**, and the
> cap **stays at 2.0 m anyway** — it is a BUILD decision (transport, storage,
> hand-launch, print bed) and this model prices none of that. What is different
> from before the experiment is that the price is now MEASURED: **~6.3 min** at
> the incumbent prop, **~8.5 min** at the 12x10 the 2.5 m run adopted. The
> reasoning lives in `VTailSample.span_cap_m`'s comment.
>
> **So the 150.53 min champion is no longer in the sample's feasible set** — it
> is a 2.497 m aeroplane. `aircraft/vtail_span300/` is KEPT and marked RETIRED
> (its name now derives from the base so it cannot drift into claiming a version
> it does not share); re-opening the question is one command.
>
> **That battery has now run.** The guard-checked 2.0 m champion is
> **142.087 min** (`runs/20260805T000721-endurance_sample-vtail_sample_v1-7`),
> 12x10 prop, winglet rejected, mesh check converged at -0.46%, NLP-vs-re-eval
> gap 2.2e-5. Both things this section said to watch came out as predicted: the
> winglet was rejected again at 2.0 m (it costs 0.917 min), and the prop screen
> still picks the 12x10.
>
> **The -0.16% this section predicted did NOT appear, and that is not a bug.**
> The prediction was that the vortex-core fix would drag 142.09 down to ~141.9.
> The measured champion is 142.087 against the pre-fix 142.086 — no movement at
> all. The fix *is* applied (all four `asb.LiftingLine` call sites pass
> `LL_VORTEX_CORE_RADIUS`) and its effect is plainly visible elsewhere in the
> same run: the flatness sweep at 2.0 m moved **120.1217 -> 119.9342, exactly
> -0.156%**. The difference is the winglet. The core artefact was a
> near-coincident-filament effect concentrated on high-cant winglet panels; the
> flatness and multistart solves carry live winglet design variables, and the
> CHAMPION does not, because the winglet study rejects it. The -0.16% was
> extrapolated from a nominal configuration that keeps its winglet, so it never
> applied to this champion. Do not read the unchanged number as the fix having
> silently failed to apply — that was this session's first hypothesis and it was
> wrong.

**Champion of record: 142.087 min at the 2.0 m cap** —
`runs/20260805T000721-endurance_sample-vtail_sample_v1-7`, guard-checked. The
150.53 figure below is retained as the answer to the span question, not as a
design.

> **Read that run's sensitivities from a re-run, not from its own artifact.**
> The flatness curve and the whole re-solve battery in that run describe the
> INCUMBENT-prop, winglet-carrying aircraft at ~119.9 min, not the 142.09 min
> design being reported, because those phases ran before the studies had
> finished choosing the design. Fixed in this session (see below), so the next
> battery's numbers are the champion's — but that run's are not.

The thirteenth session closed every open issue the twelfth session left, and **five of them
turned out to be measurement defects rather than physics** — three found by
auditing artifacts, and two more found by RUNNING, including one inside the
optimizer's own model that a solve was actively exploiting (FINDINGS §16 and
§18). The champion above is the first one produced with all of them fixed and
with two independent guards agreeing it is real.

**The model moved, so every objective moved with it.** The regularized vortex
core shifts results by ~0.15% (the 2.0 m nominal: 120.12168 -> 119.93422). Any
comparison against a pre-2026-08-01 number carries that, and flatness figures are
not comparable at all — the sweep now samples a different set of spans.

> **The 275 mm root-chord cap is now the sample aircraft's** (user decision), so
> that champion run is no longer a variant — it is the sample. Both experiment
> packages (`aircraft/vtail_chord275/`, `aircraft/vtail_span180/`) are deleted;
> their reasoning lives in `VTailSample.c_root_max_m`'s comment and FINDINGS §15.

## NEW this session (seventeenth, 2026-08-06): the first rcv2 battery ran, and it is the evidence

> ## ONE DECISION IS WAITING FOR YOU, AND IT IS THE ONE THIS BATTERY EXISTED TO SETTLE
>
> **The free-station measurement now exists and it has fired.** On the champion:
> **all 10 placed items sit on their FORWARD stop, and 7 of the 10 are boxed in
> on both sides.** The three that are not — battery (201 mm of room aft), buzzer
> (43.8 mm), esc (16.5 mm) — are held forward by the OBJECTIVE, not by a row.
>
> Forward-most derived packing would therefore reproduce this layout exactly.
> What it would give up is the pricing of that choice. `EQUIPMENT_PLAN.md` said
> "measured, then deleted"; the measuring is done and the deleting is yours.
>
> Two of the ten are held by rows a lane-end check would have missed, which is
> why the naive version of this test would have been wrong: `gps_compass` by its
> 100 mm RF separation from the SiK, `airspeed_board` by the shelf being exactly
> full.

**The battery: `runs/20260806T031736-endurance_sample-vtail_sample_v1-7_rcv2`,
417.5 min, champion 120.52 min, AUW 2.119 kg.** Ten of 22 members failed, all
`Maximum_WallTime_Exceeded`, and **287.7 of the 417.5 minutes (69%) went to
members that produced nothing** — the same shape as the 2026-07-29 finding that
87% of a 405-minute run bought nothing. Three studies returned NO verdict (tail
type, both candidates; fuselage topology; wing dihedral) and the flatness sweep
reported **2 of its 6 spans**.

**Why they fail, settled with the instrument rather than argued.**
`tools/degeneracy.py` on `printed_mass_x1.10`: **3 active rows, condition number
2.49, smallest singular value 0.41.** LICQ holds comfortably — *there is no
degeneracy*, the same verdict §14.5.8 reached and for the same reason. What is
there instead is **18 rows violated at once, total 0.42**, dominated by lift
equilibrium (0.268) and the static-margin floor (0.047), then spar stress
(0.024) and the nose-holds-the-motor row (0.018). These are **over-constrained
corners**. The `inf_du` blow-up to 1e18 is the symptom of grinding against one,
not the cause, and §14.5.7 already measured that more clock does not convert it.

> **`c_root` is back ON its cap, and the battery is now pinned FORWARD.** Both
> are reversals of what "WHAT IS STILL OPEN" records for the 2026-08-05 sample
> champion (`c_root` 0.251 off the cap, `x_battery` at its AFT limit). On rcv2
> `c_root` is at 0.275 in 12 of 13 converged members and the battery is hard
> against its `bay_floor` lane front — the manifest put the chord starvation of
> FINDINGS §15 back, and flipped which way the balance knob is stuck. **The
> remedy is a cap, and a cap is a user decision**: raise chord or span, widen the
> SM window, or carry less kit. Nothing here should move one on its own.

**What was fixed (all committed, 437 tests green).**

- **A decision rode on a measurement `active_bounds` could never make.** The
  plan's test read declared BOXES; a placement variable's box is the wide
  `PLACEMENT_BOX` backstop and its real bounds are symbolic lane rows, so it was
  silent on all ten and always would have been. `equipment.placement_activity`
  measures slack PER DIRECTION — "at a row" and "determined by the rows" are
  different claims — and the report renders it.
- **A champion that meets its stability window was reported as missing it.**
  `sm_in_range: False`, SM 0.0629 against [0.08, 0.15], for a design that meets
  0.0800 at the speed it was solved for. The NLP enforces the SM window and it
  is what sets cruise speed here (9.709 m/s over a 9.5 m/s floor); the
  re-evaluation's sweep filter carries the wind floor, gust margin,
  advance-ratio cap and throw limit but NOT the SM window, so it reads the
  margin at a different speed. Eleven runs hid this because the NLP optimum sat
  ON `v_min`, exactly where the sweep's peak is. Same split explains
  `nlp_vs_reeval_gap` going 2e-05 -> **-0.433** (all of it 0.084 W of `P_elec`,
  which back-solves `P_avionics` to 3.008 W against the model's 3.0).
  **Reporting only** — `constraints.sm_read_at` names both speeds and why.
  Which point is "best" is a decision, not a fix.
- **A failure recorded no dual side**, so "stuck" and "cut off" were
  indistinguishable. `solve._convergence_trace` records `inf_du`, the plateau
  and a three-way reading. Validated against all nine of this run's failures
  with zero false positives on the fourteen that converged.
- **The ordering packing row was raw metres** (0.047 -> 1.05 at the initial
  point). The two CONTAINMENT rows were tried the same way and measured WORSE
  (0.18 -> 60-75, because a 200 mm clearance over a 3 mm margin is 67 and not
  1), so they stay raw and say why. Regression confirmed on the re-run:
  `multistart__nominal` returns 104.5651, identical to the pre-change run.
- **`tools/degeneracy.py` could only look at `vtail_sample`** — now
  `--aircraft` and `--set attr=value`, default unchanged.

> **Do not edit model source while a battery is running.** Constraint labels
> capture line NUMBERS at build time and read the source TEXT from disk at
> report time, so ~50 added lines in `solve.py` made the last few checkpoints
> print `solve.py:1000 opti = asb.Opti()` for the lift row. Results are
> unaffected (the process holds the old bytecode); only the labels lie, and
> they can be decoded against the pre-edit file.

**A re-run is in flight** under fingerprint `8e5d4a32f187` with identical
settings, started 2026-08-06 ~04:05. It is expected to lose the same ~10 members
— the fixes make the run report honestly, they do not move any cap.

## NEW in the sixteenth session (2026-08-05): equipment is a MANIFEST now

The user supplied `Planes/RC/RC v2/ELECTRONICS_SPEC.xlsx` and asked for every
part in it to be placed by the optimizer. That turned out to be less a feature
request than a hole report.

**Equipment was seven lumped point masses at literal stations, and no run this
project has ever written said where any of them went.** `esc_wiring` sat at
0.3932 of the pod length and `fc_gps_rx` at 0.5128 — fractions read off the
frozen 585 mm pod, which stopped meaning anything the moment section 7 made the
loft parametric. And `run.json` recorded `{name: mass}`, throwing away the half
of each `PointMass` that says where it is, even though the CG is computed from
exactly that number. **Both are fixed for every aircraft**: `masses.components`
now carries mass AND station, and so do `report.html` and the build document's
mass budget (which is therefore a weigh-and-balance sheet now).

**`planeopt.equipment` is the mechanism; `aircraft/vtail_rcv2/` is the first
aircraft to use it.** 19 airborne parts and 4 ground items, each with its own
mass on two bases, installed envelope, packing lane, fore/aft order and the
requirement verbatim. MODEL_DETAILS section 10 and `docs/EQUIPMENT_PLAN.md`
carry the design; the four decisions were the user's (2026-08-05): a free
station per item, the optional kit fitted and priced by a study, the **max**
mass basis, and a new package rather than a change to `vtail_sample`.

**`vtail_sample` and its 142.087 min champion are untouched.** The only edit to
it is a pure refactor — the four lumped packaging rows moved into an overridable
`packaging_constraints`, pinned by `tests/test_equipment.py` as still being six
rows. The fingerprint moves (any source change does), so the next sample battery
starts a fresh checkpoint subdirectory; the numbers do not.

### Three findings from transcribing the sheet

- **Its stated max-weight cap is 55 g light.** The totals row says "≈ 895 cap";
  its own Max-wt column sums to **950 g**. `vtail_rcv2` solves on the max basis,
  so that 55 g is the gap between the aeroplane the sheet claims and the one it
  specifies. Both numbers are pinned in tests — correct the spreadsheet and the
  test is what says the model must move with it.
- **The BOM was written for a PUSHER and this aeroplane is a PULLER.** Every
  placement note assumes the DESIGN_SPEC tail-pusher layout: nose bay free for
  the companion computer, "pusher prop = everything forward is clean" for the
  pitot. The pusher was priced twice and lost by 9.5-10.7 min, so the nose is
  full of motor. Handled without assuming anything away — the nose bay is
  modelled and used under a pusher, and under a puller the Pi and its BEC take
  the fallback **the BOM itself names** ("beside FC tray") while the pitot takes
  the outer wing LE, which the BOM lists first anyway.
- **The 68 mm pod section is within a millimetre of not holding its own
  electronics.** ESC (8 mm, left wall) + FC (36 mm, shelf) + SiK air unit
  (10.7 mm, right wall) + 6 mm of build play = 60.7 mm against 61.0 mm of
  interior width. That is now a constraint row, and it is the first thing in
  this project that ties a parts list to `pod_wh`.

### Two things reported rather than enforced, on purpose

- **The tail group is over its 120 g budget** — 154.5 g at the fixed design,
  126.5 g of which is the printed V-tail. Writing that as a constraint would not
  discipline the design, it would delete the aeroplane, and what it would really
  be constraining is the printed-surface mass model, whose constants are
  UNCALIBRATED until `tools/fit_profile.py` runs on slicer data. So
  `masses.equipment.tail_group` states it with its own verdict.
- **`priced_options`, a new framework hook**: candidates measured by a full
  paired re-optimization and NEVER adopted. `discrete_options` adopts whatever
  wins, which is wrong when the alternative gives up something the model has no
  term for — dropping the companion computer is strictly lighter and would be
  adopted and reported as an improvement. Same posture `span_cap_m` takes toward
  the print bed.

### What to watch on the first `vtail_rcv2` battery

- **`active_bounds` on the ten placement variables.** They were the user's call
  against a flat-manifold recommendation; station reaches the objective only
  through nose ballast, so the gradient is real but small. **If they all pin at
  their lane ends, the freedom bought nothing** and the lanes should collapse to
  derived forward-packing — measured, then deleted, exactly as the 1.8 d_eq
  boat-tail floor is being handled.
- **The objective will be well below 142.087 min and that is not a regression.**
  Equipment goes from a lumped 858 g to 995 g (max basis, prop included). It is
  a heavier aeroplane on purpose, and `masses.equipment.closure` reports what
  the example-part build would weigh and balance at instead.
- **Whether the aft-bay width row binds.** If `pod_wh` runs to a bound to make
  room for the electronics, the parts list is now driving the fuselage section,
  which is new and worth knowing.

## FIXED in the fifteenth session (2026-08-05)

The 2.0 m battery ran and converged cleanly, and auditing its artifact turned up
**seven things the run was wrong about — none of them in its numbers, all of them
in its claims.** That is the same shape as the thirteenth session's findings and
worth stating plainly: a converged battery with every guard green can still
describe an aeroplane other than the one it built.

- **The sensitivity phases described a superseded design.** The flatness sweep
  and the re-solve battery ran immediately after the multistart, BEFORE the
  discrete studies and the winglet study had finished choosing the design. So
  the artifact's span-flatness curve and all four ±10% sensitivities belong to a
  119.93 min aircraft on the incumbent 11x6 prop carrying a winglet, while the
  champion reported alongside them is a 142.09 min aircraft on a 12x10 with no
  winglet. Every member converged and nothing said the two were different
  aeroplanes. **Both phases now run after the winglet study**, and the +20 g
  shadow-price bump rides the battery so the REPORTED trade rate is the final
  design's too (the multistart bump survives, unreported, because
  `screen_discrete` needs a shadow price before the studies run). Pinned by
  `tests/test_phase_order.py`.
- **The headline number was limited by `v_min`, and said so nowhere.** The
  champion is 142.09 min at 9.5 m/s; the sweep's own optimum is 143.01 min at
  9.0, excluded by the minimum-speed requirement. `diagnostics.v_min_price` now
  names the excluded peak and prices the requirement, with a note and a report
  section — "the best this aeroplane can do" and "the best it may do at or above
  9.5 m/s" are different sentences and only the second was ever true.
- **A solver giving up was recorded as proven infeasibility.** V = 8.0 m/s was
  reported `infeasible` on the strength of *"the iteration is not making good
  progress"* — a message about the root-find's step, at a speed 0.28 m/s above
  computed stall where a trimmed solution may well exist. Sweep points now carry
  a `cause`, and `trim_not_converged` is reported as UNKNOWN rather than as a
  limit of the aeroplane.
- **The static margin changes sign inside its own regression window.** Reported
  SM 0.0800 sitting on its floor, with local dCm/dCL of +0.187, +0.138, then
  **-0.022 at the trim alpha itself**. This is the known dominant fidelity limit
  of the SM estimator — and a known limit that nothing announces is
  indistinguishable from a clean result to everyone downstream. Now a
  `sm_sign_consistent` constraint check, a log warning, a note, and a report
  paragraph that explains the FAIL rather than leaving it bare.
- **A fully resumed phase was indistinguishable from a skipped one.** Multistart
  and the flatness sweep both reported 0.0 minutes; both had in fact been solved
  in full the evening before and came off disk. The fingerprint guard means the
  physics matches, so the resume was legitimate — but "fresh battery" and
  "re-ran the global search" are different claims and the artifact could not
  tell them apart. `diagnostics.phase_resumed` now reports "N of M from
  checkpoint" per phase, with a note when a whole phase came off disk.
- **The per-solve RAM figure was folklore and was optimistic.** `13.0` GB
  against a measured 14.48 GB peak. `budget_to_parallel` DIVIDES by this, so the
  error direction costs a battery to the OOM killer; now 14.5, and the prose in
  `memory.py`, `cli.py`, `geometry.py` and `solve.py` agrees with it.
- **The vortex-core prediction in this file was wrong** — see the correction at
  the top. Recorded because the wrong inference it invites (that the fix silently
  failed to apply) costs an afternoon to rule out.
- **The fuselage drag model could not see afterbody SHAPE, and two things it
  could not see were load-bearing.** Tier 1 of the fuselage-drag plan is built:
  boat-tail separation charged as an effective base, a fineness ceiling shipped
  with it, and the end cap derived from the boom socket it actually is. Plus, at
  the user's request, the rows that stop the optimizer shrinking the pod below
  its own motor — **the champion's nose has half the length it needs for the
  can.** Both move every objective; the FUSELAGE DRAG FIDELITY section below is
  the full account, including where the build departed from the plan.

## FIXED in the fourteenth session (2026-08-04)

Nothing in the model moved; this was a decision-and-hygiene session. The audit of
everything committed since the last run found the code and the run artifacts
clean — 257 passing, `run.json` reporting mesh check converged, both VLM
configurations reliable, stall clear, NLP-vs-re-eval gap 0.0000 — and three
defects in the write-up itself:

- **`docs/HANDOFF.md` carried a 103-line VERBATIM DUPLICATE.** The 2026-08-01
  write-up commit inserted its new section along with a second copy of the two
  sections above it, so "FIXED this session" and "WHAT IS STILL OPEN" each
  appeared twice, identical. Removed. Worth naming because the duplicate was
  *correct* text — nothing read wrong, it just read twice, which is precisely the
  kind of thing a reader skims past and a diff hides.
- **A completed action was still written as the next one.** The aborted first
  attempt's section said "Re-running it is the next action" and "the run has to
  be redone" after it had been redone. It is now marked superseded, and says
  which of the things it told the reader to watch actually happened.
- **Issue 0b's active-bound table was silently the PREVIOUS champion's.** It is
  now labelled as the chord275 champion's, and points at FINDINGS §19.4 for the
  2.5 m one — three rows differ, which is itself the lesson: a bound list is a
  property of one solve, not of the aeroplane.

## FIXED in the thirteenth session (2026-08-01)

- **`aero.vlm_induced_check` was reporting an inviscid wing that made thrust**
  (issue 0a). `k_induced = -0.5035` at the champion, and the raw sweep — which no
  run had ever printed — showed `CD = -0.54` at α=2°. **It was the VLM MESH, not
  the fit.** AeroSandbox's default spanwise `cosspace` bunches panels against
  every wing-section boundary; on this wing's four unequal sections that leaves a
  near-singular AIC. Uniform spanwise panels take the champion to `k = +0.0267`,
  `e = 1.27`, and a winglet that finally *reduces* induced drag (−9.6%).
  **But one mesh is still not enough** — individual meshes blow up sporadically
  on high-cant geometries and look physical when they do — so the check now runs
  a **three-mesh ensemble, reports the consensus, and flags configurations whose
  meshes disagree** rather than shipping a number. FINDINGS §16.1 has the chain.
  The chronic slightly-negative `cd0_inviscid` **is benign fit noise**, as the
  issue suspected; the sweep uses 6 alphas now instead of 3.
- **`fixed` is already applied as a bound — that work item was already done**
  (issue 1's remaining half). `detect_simple_bounds=True`, added the session
  before for an unrelated reason, makes CasADi hoist `x == v` into `lbx`/`ubx`
  and *eliminate the variable*. Measured on the real model: fixing span at its
  own lower bound goes 36 variables → **35**, with equality and inequality row
  counts unchanged. The SVD that motivated the item predates the flag. Pinned by
  a test against CasADi's own `detect_simple_bounds_is_simple`, because the
  symptom if the flag is dropped is a diverging `inf_du` in the flatness sweep.
- **The winglet solves never cost 2.7 GB** (issue 0c). `peak_rss_gb` was a
  process high-water mark that only rises, so every member after the heaviest
  one inherited its number. The 11.7 → 14.45 GB step is the **tail-type study**
  (35 design variables and a separate fin surface, against 32); the winglet
  solves are the LIGHTEST in the run at 27. The in-process path now resets the
  mark between members, and where it cannot the member says so
  (`peak_rss_is_batch_watermark`). Also: 0c's "~15 GB WSL cap" was stale —
  `.wslconfig` has granted 26 GB since 2026-07-24, so the margin is ~10 GB.
- **Active bounds are reported instead of reconstructed by hand** (issue 0b).
  Every solve records `active_bounds`, the progress log names them, and the
  report marks each pinned design variable. The champion sat on eight and the
  session discussed three, because the box lives in the aircraft's
  `design_variables` and no artifact ever saw it. Pricing which one to relax
  still needs runs — an active bound tells you nothing about its value until you
  move it.
- **M5.3 two-stage discrete studies — BUILT** (issue 3). `solve.screen_discrete`
  ranks candidates at the champion's operating point with no NLP at all, so the
  candidate set can be the catalogue and the run still pays for four solves.
  Validated against the 2026-07-31 battery, whose answer is known: it ranks 65
  candidates in **0.5 s**, puts the same prop first that eight full re-solves
  adopted, and prices it at **141.56 min against their 141.43**. Mass is charged
  at the run's own shadow price — without that a bigger disc arrives weightless.
  `PROP_CANDIDATES` is now a RULE over the shipped catalogue (every measured
  folding table inside the declared diameter limit, **66** of them, was 8), and
  the incumbent key moved `cam_11x6` -> `ancf_11x6` for the same propeller.
  FINDINGS §17.
- **The flatness sweep samples the optimum's neighbourhood** (issue 0f, deferred
  twice). `[0.85 x champion span, cap]` instead of a constant 1.5 m floor.
  **Flatness figures are no longer comparable with runs before 2026-08-01** —
  that is the cost, and it is why it was deferred; at a 3 m cap the old range
  would have spent most of the sweep on spans 50% below the optimum.
- **`--warm-start` was fixed AND measured, and still does not pay** (issue 5).
  It now asks IPOPT for a warm start rather than only seeding values — without
  `warm_start_init_point` the default `bound_push`/`bound_frac` shove the
  starting point 1% off every bound before the first iteration, and this
  champion sits on eight of them. Measured with the previous champion's own
  design vector as the seed, which is the most favourable case there is:
  **cold 5.35 min, seed-only 6.78 (+27%), seed + options 5.58 (+4%)** — all
  returning 120.12168. It is a provenance tool, not a speed one, and it now says
  so in the log. FINDINGS §16.5.
- **Pusher retired as a candidate** (user decision): pullers only. Priced twice,
  lost twice — at 275 mm it converges properly and still loses by 9.5 min at the
  same SM floor (110.66 vs 120.12). The mount attribute and the pusher model are
  untouched; putting `"pusher"` back in the list re-opens the question.
- **User decisions taken** (issue 0d): `FLATNESS_TIMEOUT_MIN` **12 → 20**, and
  the 275 mm chord cap promoted into `VTailSample` with both variant packages
  deleted.

- **The in-loop lifting-line returned negative drag at high winglet cant, and a
  solve exploited it** — found by running the 3 m battery, not by review. The
  winglet had four panels (AeroSandbox's default is per SECTION); it now has
  three stations, which is the converged answer for four more panels a side.
  Every champion is now re-checked at 16 panels/section
  (`aero.mesh_convergence_check`) and the run says so if the in-loop drag is
  negative or more than 10% off. **FINDINGS §18** — read it before trusting any
  objective from a geometry with a strongly canted surface.

Suite is **251 passing** (was 214), plus one `slow`-marked end-to-end VLM test.

The aircraft is **`vtail_sample_v1.7`** — the version moves with the chord cap
because it names the run directory, and two aircraft with different feasible sets
must not answer to the same name.

## WHAT IS STILL OPEN

**Issue 2 — static-margin FIDELITY — and it cannot be closed in this app.** The
two-estimator artefact is long gone; what remains is that `sm_local_slopes` goes
negative at the cruise alpha, i.e. Cm(CL) is nonlinear enough over +-2 deg that
"the" static margin depends on the window it is measured over. A regression slope
is a defensible summary of that and still a summary. **flow5 (or equivalent)
should own the stability verdict before anything is built** — an external tool,
not a code change, and it gates BUILDING rather than running.

> Since 2026-08-05 the RUN says this about itself: `sm_sign_consistent` fails,
> the log warns, and the report explains it beside the margin. That does not
> close the issue — it stops it being something a reader has to already know.

**Issue 0b's second half** — which of the seven active bounds is worth relaxing —
is now a question with a printed work list rather than a hidden one, and it needs
solves rather than edits. Start with `x_battery`: it, `ballast_kg = 0` and SM
exactly on its floor together say the design is CG-limited, which the whole
span-vs-chord discussion missed. `le_shear = 1.0` and `washout_tip = 0.0` are
departures from DESIGN_SPEC that have never been questioned.

> The 2026-08-05 champion sharpens this: **`c_root` is no longer on its cap**
> (0.251 m against the 0.275 m limit), so the chord starvation that FINDINGS §15
> diagnosed is genuinely relieved — while `x_battery` IS pinned at its aft limit
> with SM exactly on 0.0800. The binding pair is now battery travel and the SM
> floor, and nothing else. That is the next bound worth relaxing, and unlike the
> chord cap it is a mounting question rather than a print-bed one.
>
> > **BOTH HALVES OF THAT REVERSE ON `vtail_rcv2` (2026-08-06).** `c_root` is
> > back at 0.275 in 12 of 13 converged members, so the chord starvation is
> > back — the manifest's equipment put it there — and `x_battery` is pinned
> > FORWARD against its `bay_floor` lane front rather than aft against its box.
> > The paragraph above is still true of `vtail_sample`; it is not true of the
> > aeroplane the RC v2 BOM describes, and the ten failed members of that
> > battery are over-constrained corners with lift equilibrium and the SM floor
> > as their two dominant misses. See the seventeenth-session section.

**Issue 4 (2026-08-06) — the V-tail is sized by a declared number, and the yaw
axis is available to replace it. SCOPED, NOT BUILT.** The user asked why the
V-tail is so large. It is not aerodynamics: **`Vv` lands on 0.03000 — the
declared `v_tail_volume_min` — to five decimals in both the 2026-08-05 and
2026-08-06 champions.** Lifting line has no yaw axis, so nothing pushes back on
tail size except that constant, and the optimizer parks exactly on it. The tail
grew this run (span 0.422 -> 0.475 m, arm 0.942 -> 1.081 m) only because the
floor is normalised by wing size and the wing grew 17.9% to carry the manifest;
as a FRACTION of the wing the tail actually got leaner, 9.7% -> 9.1%.

**`asb.VortexLatticeMethod` can replace it and is fully differentiable.**
Measured 2026-08-06 with plain `cas.MX.sym` inputs:

    VLM  d(Cn)/d(t_span)     = +0.028797     live
    VLM  d(Cn)/d(t_dihedral) = +0.000501     live
    VLM  d(CL)/d(span)       = +0.035371  vs  LiftingLine +0.035867  (1.4%)

`OperatingPoint` already takes `beta` (and p/q/r), `Cn`/`CY` come back as MX,
and VLM builds ~8x FASTER than the LiftingLine already in the loop (0.3 s
against 4.5 s). The mechanism is small: run VLM at beta = +-eps, form
`Cnbeta = dCn/dbeta`, and constrain that instead of `vv`.

> **A methodology warning, because it cost an hour here.**
> `cas.jacobian(expr, opti.x)` returns nnz = 0 for AeroSandbox `Opti`
> expressions — `opti.x` is not purely symbolic — and it does so for a trivial
> `3*v**2` as readily as for a VLM. It reads exactly like "this model is not
> differentiable" and it is an artefact of the test. Probe with `cas.MX.sym`
> inputs, and sanity-check the probe on a trivial expression first.

Four things make this a fidelity upgrade rather than a quick win, in rough order
of how much they should worry you:

1. **VLM is lifting surfaces only, so a VLM-only `Cnbeta` is OPTIMISTIC** — it
   omits the pod's destabilising yaw contribution, which on this fat-nosed pod
   is not small. That fails in the UNSAFE direction (tail too small), so the
   slender-body fuselage term belongs in the same change, not a follow-up.
2. **It adds a second aero model to the NLP**, probably two runs (+-beta), to a
   loop where **10 of 22 members already die on the 30-minute cap**. This
   session showed how sensitive that is: a one-line constraint rescale cost a
   member outright. **Fix the over-constrained corners first.**
3. **The floor stays a declared number** — `Cnbeta_min ~ 0.04-0.10 /rad` is
   class practice just as 0.030 is. What is gained is that it acts on real
   computed geometry (dihedral, arm, area, sweep and their interaction) rather
   than the closed-form `S*sin^2(dihedral)` proxy. Do not sell it as the model
   learning what stability it needs.
4. **Static stability only.** Dutch roll and spiral want `Clbeta`, `Clp`, `Cnr`
   and inertias. This narrows the section 3.4 gap; it does not close it, and
   "flow5 and flight test own the rest" still holds.

Expect tail size to move 10-20% in EITHER direction. The user's Cnbeta floor is
wanted before the constraint is written.

**Issue 3 (2026-08-05) — the fuselage drag model could not see shape, and the
champion was exploiting that. TIER 1 IS NOW BUILT** — see the next section for
what shipped and what it changed. What remains open is the *measurement*: the
`pod_tail ≥ 1.8·d_eq` floor is deliberately kept for one battery, and the next
run is what decides whether it is deleted as a no-op or whether the constants
need revisiting.

## FUSELAGE DRAG FIDELITY — Tier 1 BUILT 2026-08-05

> **Status: IMPLEMENTED** against `docs/FUSELAGE_DRAG_PLAN.md` (2026-08-05).
> The four judgement calls were decided by the user that day (effective-base
> model, θ_sep = 12°, fineness cap f ≤ 8, floor kept one battery then deleted as
> a measured no-op); the plan states the full math, the seams, expected
> magnitudes and the rollout, and the implementation notes below record where
> the build **departed from the plan and why**. The physics lives in
> `fuselage.afterbody_terms` and is documented in MODEL_DETAILS §7.3.
> Everything after "### 1. Why it matters more than it looks" remains as the
> original investigation record.
>
> ### > THIS MOVES EVERY OBJECTIVE. COMPARISONS CARRY IT. <
>
> Exactly like the vortex-core fix: the `r_cap` geometry change plus the new
> term shift every objective, and **flatness figures are not comparable across
> it at all.** The first run that carries this change must be flagged the same
> way, and FINDINGS gets its entry AFTER that battery, not before. **Do not
> compare the next champion's minutes against 142.087 without naming this
> change as a cause.** At the current champion's design vector the term charges
> +34 % on body drag and +2.0 % on total drag; the geometry fix alone adds 1.2 %
> wetted area and 1.2 g before any drag is charged.
>
> ### What to read the next battery for
>
> The rollout is deliberately measure-then-move (plan §7): with an uncalibrated
> constant and no floor, the first battery's boat-tail would be set entirely by
> a number nobody has validated. So `pod_tail ≥ 1.8·d_eq` ships **untouched**,
> and the next battery answers three questions with machinery that already
> exists:
>
> - `active_bounds` / the constraint's slack — **is the floor inactive now?**
>   If yes, delete it in the following change as a measured no-op and state the
>   slack in the commit. If it is still pinned, the correlation is too weak:
>   revisit the constants, do **not** delete the floor.
> - `diagnostics.afterbody` — did θ_max settle near the 12° threshold? The
>   predicted response is a longer boat-tail, θ_max → 12–14°, landing near
>   f ≈ 7.2 — inside the f ≤ 8 ceiling and off the floor.
> - the champion delta — within shouting distance of the −2 to −3 min the plan
>   estimated?
>
> ### Where the build departed from the plan
>
> Three places, all recorded because each one is a decision a reader would
> otherwise have to re-derive from the diff:
>
> 1. **`r_cap = boom_od / WIDTH`, not `/ d_eq`.** The plan's formula makes the
>    cap's *equivalent* diameter equal the boom OD — but the cap face then works
>    out **10.5 × 13.7 mm at the champion, and a round 12 mm tube does not pass
>    through a 10.5 mm hole.** It would have made the fraction self-consistent
>    in the d_eq convention while leaving in place the exact physical fault §3
>    exists to close. Sized on the narrow dimension the cap is 12.0 × 15.5 mm.
>    Costs ~6 % of the charge (θ_max 18.5° → 18.0°, base area 3.15e-4 →
>    2.97e-4 m²), so the plan's §6 estimates still hold to within that.
> 2. **The fineness ceiling is pod-boom ONLY.** Applied to `integrated` it would
>    not bound that candidate, it would delete it — that body runs to the tail
>    block, so its length is set by `tail_arm` and it sits at **f = 14.7** at the
>    declared defaults (18.1 at the champion's vector). The only way to satisfy
>    f ≤ 8 there is a maximally fat pod on a minimum tail arm, so the topology
>    study's priced alternative would quietly become a garbage design that still
>    converged. **The needle exploit is therefore still open for `integrated`** —
>    the champion diagnostics report fineness for both topologies so a run that
>    finds it says so, but nothing stops it.
> 3. **A NaN pole was found and closed that the plan did not anticipate.** At
>    `r_cap = 1` the closure `1 − r_cap` is exactly zero, ρ is infinite, and
>    `smooth_floor(1 − ∞)` is `0.5·(−∞ + ∞)` = NaN; separately, flooring the
>    discriminant to exactly zero gives the sqrt above it an infinite slope, so
>    the *guard against NaN values* was itself a source of NaN **gradients**.
>    Both are unreachable through today's bounds and one edit away from
>    reachable — freeing `r_cap` is on this file's own list of cheap widenings.
>    Found by the symbolic-safety test, not by review.
>
> ### Shipped alongside, at the user's request (2026-08-05)
>
> **The motor has to fit inside the nose.** Not part of the drag plan; raised
> while reviewing it, and a live defect of the same kind — the optimizer had been
> shrinking the pod section for runs and **the champion's nose offers 25.8 mm of
> can-width room for a 51 mm can.** MODEL_DETAILS §7.2 has the formulation. Two
> rows, puller only, no geometry change: the loft stays the outer mould line
> (pod plus the nosecone that completes it) and the rows only claim that the
> cylinder fits inside it, ahead of the bay. Expect the next champion's `pod_xs`
> to come back up from 0.794 toward ~1.0, where the existing `pod_nose ≥ 1.0·d_eq`
> floor nearly satisfies it on its own.
>
> **This one is not comparable-across either, and it binds harder than the drag
> term does.** A pod that cannot hold its own motor was never a cheaper
> aeroplane, so the minutes it was buying were not real.
>
> **And it dragged out a second defect, in the MASS model.** Asking where the
> bulkhead is means asking where the motor is, and the answer was a literal:
> `nose_tip + 0.02`, written when the pod was a frozen 585 mm prism and left
> alone when the pod became a loft the optimizer shrinks. At the 2026-08-05
> champion it places a 42 mm motor **20 mm behind a tip where the pod is 39.9 mm
> wide** — a station the motor cannot occupy. The can's CG is really **41 mm
> further aft**, which on a 190 g motor+prop group is **+4.3 mm of aircraft CG**,
> measured. That matters more than its size suggests: this design is CG-limited,
> with `x_battery` pinned at its aft limit and SM sitting exactly on its floor,
> and the correction moves CG in the direction it has been starved of. Mass does
> not move; only the station. Both the mass model and the packaging row now read
> `nose_split`, so there is one motor station instead of two.
>
> **The nosecone is now a named part.** The loft is the outer mould line — pod
> plus the fairing that completes it — and no artifact said which was which, so
> the builder got a pointed body with no cut station and no opening diameter.
> The split is derived rather than chosen (the one station where the interior
> first clears the can, i.e. the motor-fit constraint read backwards), and it
> appears in the CAD brief and on the manufacturing sheet. At the champion:
> **36 mm of nosecone, a 49 × 63 mm bulkhead with a 42 mm opening, 26 mm of motor
> bay for a 51 mm can.** No mass moves — the pod mass model integrates the whole
> loft's wetted area, so the fairing was always paid for.
>
> Still one continuous body in the 3D model and the STEP/CSV export. Splitting it
> there would mean `fuselage_lofts()[0]` no longer being the whole pod, which the
> mass model indexes — so it is a deliberate next step, not a silent one.

### 1. Why it matters more than it looks

Body drag as a share of total, measured on the 2026-08-05 champion's own speed
sweep — same airframe, current model, nothing re-solved:

| V (m/s) | CL | CD_bodies | CD_total | body share |
| --- | --- | --- | --- | --- |
| 8.5 | 0.98 | 0.00219 | 0.05446 | **4.0%** |
| 9.5 *(champion)* | 0.78 | 0.00214 | 0.03712 | **5.8%** |
| 12.0 | 0.49 | 0.00204 | 0.02179 | **9.4%** |
| 16.5 | 0.26 | 0.00192 | 0.01452 | **13.2%** |

`CD_bodies` barely moves — **-12% across a 2x speed range, all of it the
`Re^-0.2` on skin friction**. The entire effect is induced drag collapsing out
from under it. So the endurance intuition ("mass decides, fuselage shape is
noise") is a statement about the OPERATING POINT, not about the model: at a
top-speed design point the ranking inverts, weight nearly stops mattering, and
what is left is wetted area and form.

Do NOT cite the 2026-07-26 `speed_sample` run for this — it predates the
vortex-core fix, the prop model and the mesh guards. The table above is current.

### 2. The actual limitation: a four-number channel

The complete information path from fuselage geometry to the objective is
`aero.body_cd0` plus the Munk term, and between them they consume exactly four
quantities per body:

- `wetted_area_m2`
- `length_m` (only as `Re` -> `Cf = 0.074/Re^0.2`)
- `form_factor` (a function of `L/d_eq` ALONE — `fuselage.body_dict`)
- `volume_m3` (Munk pitching moment only, not drag)

**Any two fuselages agreeing on those four are identical to the optimizer, to
the last digit.** A well-faired body and a badly separated one of equal wetted
area, length, equivalent diameter and volume score the same.

The direct consequence, and the reason this section exists before any geometry
work: **do not widen the fuselage parameterization until this is fixed.** Adding
spline control points or free cross-sections today would add design variables
the objective is provably blind to — a degenerate optimum on a flat manifold,
which IPOPT handles badly, plus more CasADi graph on a solve already peaking
near 14.5 GB, and no better aeroplane. The parameterization is not the binding
constraint. The drag model is.

### 3. What the parameterization currently is (inventory, so nobody re-derives it)

It is a REAL loft, not a drag table: `fuselage.loft()` builds an `asb.Fuselage`
from 16 superellipse stations and the NLP reads that loft's own
`area_wetted()` / `volume()` integrals symbolically. The optimizer SIZES the
family; it does not RESHAPE it.

Free (4 shape DOF + 1 placement): `pod_nose`, `pod_bay`, `pod_tail` (pod_boom
only — integrated derives the cone from `tail_arm`), `pod_xs`, and
`pod_bay_end` (axial placement).

Fixed: superellipse exponent (4.0), end-cap fraction `r_cap` (0.12), station
counts (7/7), the nose elliptical arc, the boat-tail cubic Hermite, and — note —
**the width:height ratio, locked**: `pod_xs` scales BOTH from
`POD_XS_SPEC = (0.068, 0.088)`, so the pod cannot be made wider and flatter.

Also note `fuselage_topology: ["pod_boom", "integrated"]` is already a discrete
study priced every run, so the aircraft is *not* stuck on pod-and-boom — but
both topologies use the same 5-parameter family.

Once the physics can see shape, the cheap widenings are three scalars: unlock
the w:h ratio, free the superellipse exponent, free `r_cap`. Splines come much
later, if ever.

> **THE FIRST OF THOSE THREE IS DONE (2026-08-05, user decision).** `pod_wh` is a
> design variable — the width:height ratio — with `r_cap` already symbolic.
> Only the superellipse exponent is still fixed.
>
> **`pod_xs` and `pod_wh` are orthogonal by construction:** `w·h` is the spec
> product times `pod_xs²` whatever the ratio, so **`d_eq` depends on `pod_xs`
> alone.** That is deliberate rather than tidy — the two proportion floors, the
> fineness ceiling and the entire afterbody term are written against `d_eq`, and
> a ratio that moved it would silently re-scale six constraints while claiming to
> change only shape. `pod_wh = 68/88` is the default, so **every number this
> project has recorded is the `pod_wh = 0.7727` slice of the new family**, exactly.
>
> **The objective can see it, which is the whole precondition.** At fixed `d_eq`
> a superellipse has least perimeter when square, so the loft's own wetted-area
> integral prices eccentricity: measured at the champion, **Swet 0.0688 m² square
> against 0.0712 at the 1.55 bound, +3.5%.** And it pulls the OTHER way through
> the afterbody term — squaring widens the narrow dimension, so `r_cap` shrinks,
> the boat-tail closes harder and the base charge rises (2.97e-4 → 3.15e-4).
> A real trade, not a slide to a bound.
>
> **What it buys immediately** is the cheap currency for the motor-fit row. That
> row was going to be paid for with `pod_xs` — growing the whole pod and its
> wetted area with it — and squaring the section instead takes the motor bay
> from **25.8 mm to 37.0 mm without touching `d_eq` at all.**
>
> **Width is no longer the narrow dimension.** Three places quietly relied on it
> — the boom socket, the bulkhead station and the motor row — and all three now
> take a SMOOTH min of width and height (`p["d_min"]`), because `min` is a branch
> on a design-variable value. It under-reports by tau/2 = 50 µm, i.e. toward the
> stricter constraint and the slightly larger socket, which is the safe direction
> for a hole that has to admit a tube. Pinned by a mirror test: a 68×88 pod and
> an 88×68 pod must agree on every derived quantity.
>
> Bounds `POD_WH_LIMITS = (0.65, 1.55)`, a model-validity bound in the
> `fineness_max` idiom, sourced from the model's own convention error — closure
> angles use the d_eq-equivalent convention, which understates the steeper
> principal plane by `sqrt(max(w/h, h/w))`: 14% at the spec section and **24% at
> these limits**.

### 4. The live defect

Computed from the champion's own Hermite boat-tail
(`r(u) = 1 - (1-r_cap)(3u^2 - 2u^3)`, max slope at `u = 0.5`):

| station | local closure half-angle |
| --- | --- |
| u = 0.25 | 15.4° |
| u = 0.50 | **20.1°** |
| u = 0.75 | 15.4° |

Separation onset for an axisymmetric afterbody is around **12-15°** half-angle.
The champion runs ~20° (≈40° included) through the middle of its boat-tail and
`body_cd0` charges **nothing** for it. *(Charged since 2026-08-05; the angle
reads 18.0° once the end cap is the boom socket it should always have been.)*

And the reason is visible in the design vector: **`pod_tail` = 110.6 mm sits
EXACTLY on its floor of `1.8 x d_eq` = 110.6 mm.** The optimizer shortens the
boat-tail until a hard-coded geometric floor stops it, and that floor is a
*proxy for the physics that is missing*. Give the model a real afterbody term
and the floor should become removable — which is the satisfying version of this
work, not a bolted-on penalty.

Two more gaps found while scoping — **both closed 2026-08-05, see the status
block at the top of this section**:

- **There is no base-drag term anywhere in the buildup.** Not small-and-ignored;
  absent.
- **There is no fineness cap anywhere.** The Hoerner form factor in use,
  `FF = 1 + 60/f^3 + f/400`, bottoms out at **f = 16.38**; the champion sits at
  f = 6.20. Real minimum-drag fineness for a body of revolution is ~6-7. Point a
  top-speed objective at this and the model will pay to stretch the pod toward a
  needle — the same failure shape as FINDINGS §18, where the optimizer found a
  corner in which the MODEL rather than the aeroplane produced the win.

### 5. Tier 1 — the work item

In-loop algebraic afterbody terms plus a fineness cap. Rough estimate one day of
code; the correlation decision is the long pole, not the implementation.

**Seams (both already exist).** `fuselage.body_dict()` computes the terms — it
already owns the fineness -> FF derivation, so afterbody physics belongs beside
it — and `aero.body_cd0()` consumes them by reading new dict keys.

**The closure angle is closed-form for this family**, so no geometry query and
no new design variables are needed:

```
theta_max = atan[ (d_eq/2) * 1.5 * (1 - r_cap) / tail_len ]
```

`body_dict` does not currently receive `tail_len` or `r_cap` (they are
`loft()` arguments) — they will have to be passed or the afterbody helper
called alongside.

**Constraints the implementer must respect:**

- **Symbolic safety.** `fuselage.py` imports `aerosandbox.numpy` and is safe.
  **`aero.py` imports PLAIN `numpy`** — putting new symbolic arithmetic there is
  a trap; check before writing. Use `geometry.smooth_floor` for the
  `max(0, theta - theta_sep)` hinge, never a bare `max`.
- **The `dv=None` frozen baseline must not move** (validation continuity). It
  returns hard-coded dicts; additive keys with safe defaults leave it still.
  `tests/test_fuselage.py:13` pins `wetted_area_m2 == 0.183` and will catch a
  regression.
- **Base area needs occlusion handling** — in pod_boom the boom emerges from the
  cap. While checking this a **geometric inconsistency surfaced: the boom is
  12 mm OD and the base is `r_cap * d_eq` = 7.4 mm, so the boom is LARGER than
  the cap it sockets into.** Resolve that before charging base drag against
  either number.
- **Ship the fineness cap in the same change**, or the exploit merely moves from
  the boat-tail to the needle.
- **It will move every objective**, exactly like the vortex-core fix — flatness
  figures will not be comparable across it, and HANDOFF/FINDINGS need the same
  "comparisons carry this" note.

**Unresolved judgement calls — decide these, do not assume them:**

1. **The boat-tail correlation and its constants** (separation threshold, growth
   law). The defensible posture is the one already used for `MOUNT_EFFECTS` and
   the 1.08 interference factor: *declared data, labelled uncalibrated,
   adjustable data not code*. A scoping sanity-check using a
   `(theta - 12°)^2` form suggested roughly +8% on body drag at the champion —
   real but not dominant, and enough to create the gradient that lifts
   `pod_tail` off its floor. **That was an order-of-magnitude check, not a
   recommendation.**
2. **Whether max local angle is the right separation criterion**, or whether the
   drag should be integrated over the afterbody. Max-angle is analytic and
   cheap; an integral is more honest.
3. **The base drag coefficient.** Suggest matching AeroSandbox's own
   `fuselage_base_drag_coefficient(mach)` at low Mach, so that Tier 2's
   cross-check is comparing like with like.
4. **The fineness cap value** — must come from a source, NOT from the FF curve's
   own minimum, which is the artefact being guarded against.

### 6. Tiers 2 and 3, for context

**Tier 2 — numeric cross-check guard (a day or two).** Follows the architecture
already in place: `aero.mesh_convergence_check` and `aero.vlm_induced_check` are
both "cheap in-loop model, expensive numeric second opinion at the champion
point, flagged in the artifact". Run `asb.AeroBuildup` on a fuselage-only
airplane and compare. Numeric-only, so no symbolic constraints.

Be honest about what it buys: **asb 4.2.10's fuselage model HAS a base-drag term
(`Cd_base(M) * area_base * q`) the current buildup lacks entirely, and has NO
boat-tail or separation model at all** (zero source hits for `boattail` /
`separation`). It cross-checks wetted-area and base bookkeeping. It says nothing
about closure angle. Easy to oversell.

**Tier 3 — a real pressure solution (weeks, and not in-loop).** A source-panel
method gives a pressure distribution but is inviscid: it shows the adverse
gradient, not the separation, without boundary-layer coupling. The better
version is external and gates BUILDING rather than running — the same posture
this project already took for stability, where flow5 owns the verdict (issue 2
above).

## THE 3 m RUN — DONE, and the span curve finally turns over

`runs/20260801T043954-endurance_sample-vtail_sample_v1-7_span300`, 127 min,
**champion 150.53 min at span 2.4970 m, AUW 1.932 kg, L/D 25.1**, prop
`ancf_12x10`, pod-boom, V-tail, smooth dihedral curve, **winglet retained**.
FINDINGS §19 has the full reading; the four things that matter:

1. **Span is INTERIOR for the first time** — 2.497 m against a 3.0 m cap, three
   multistarts identical, and a flatness sweep that converged **6 of 6** and drew
   both sides of the curve. 3.0 m *costs* 4.2 min. The 2.0 m cap costs ~6.3 min.
   **And the optimum is flat to +-180 mm**, so the buildability call has room.
2. **The prop was worth four times the span**: +24.33 min for `ancf_12x10` over
   the incumbent, found by M5.3's screen ranking 65 candidates with no NLP — and
   the four full re-solves reproduced the screen's ordering exactly. Caveat: the
   champion cruises at **19.3% throttle**, where the chain model is least
   trustworthy. Ranking solid, absolute minutes uncalibrated.
3. **The winglet is retained for the first time** (+0.65 min), and both new
   guards corroborate it — mesh check converged at -2.8%, VLM ensemble 3-of-3
   reliable with k 0.0184 against 0.0228. **But `wl_cant` is pinned on its 55 deg
   LOWER bound**: the design wants the panel flatter, i.e. it wants SPAN, and a
   low-cant winglet is the only door left with the projected-span cap binding.
   Price the same panel as span before adopting it.
4. **`spar_od_center` is pinned at its 14 mm maximum** — the centre spar wants to
   be fatter, so part of this answer is the tube you can buy rather than the
   aerodynamics. It is the same shape as the `c_root` story in §15, and it is the
   next bound to move.

**Everything the guards can check, checked.** NLP-vs-re-eval gap 0.0000, stall
clear, SM exactly on its floor, mesh check converged, both VLM configurations
reliable, peak RSS 14.64 GB (the tail-type study, correctly attributed).

## THE 3 m RUN'S FIRST ATTEMPT, AND WHAT IT FOUND IN TWENTY MINUTES

> **Superseded by the section above** — this is the ABORTED first attempt, kept
> because the defect it found is the reason the model moved. The re-run it calls
> for is `runs/20260801T043954-…`, which is done.

The battery against `aircraft/vtail_span300/` (`span_cap_m` = 3.0 m, user ask)
**was stopped at its second flatness member and its checkpoints discarded.** It
had already produced two results, and they are opposite in kind:

**1. The span question is answered, and it is the first honest answer.** Span
landed **INTERIOR at 2.4925 m** — three multistarts identical to four decimals,
126.36 min against 120.12 at the 2.0 m cap. Span has sat on its cap in every run
this project has ever done, so this is the first time the curve has been allowed
to turn over. `c_root` went interior too (0.2174 against the 275 mm cap), which
supports §15's reading that chord was compensating for span it could not have.
The 2.0 m cap costs **~6.2 min**, well above the 1-1.5 min §15.8 extrapolated
from a slope measured against a wall.

**2. The in-loop aero model returns NEGATIVE DRAG, and the optimizer found it.**
The flatness member at 3.0 m reported 222 min, 0.0275 N of total drag and an L/D
of 889, because a 52 mm winglet canted 86 degrees contributed about -0.93 N.
**FINDINGS §18** has the chain.

The cause is `vortex_core_radius`, which AeroSandbox defaults to **1e-8 m** — a
filament's induced velocity goes as 1/r, so ten nanometres of smoothing is none
at all, and a control point that lands a micron from a filament dominates the
solution. It is now **1e-4 m** (`aero.LL_VORTEX_CORE_RADIUS`), which fixes the
sign, agrees with a 16-panel mesh to ~1-2%, and is still far below a real vortex
core.

**Refining the mesh was tried first and is recorded as the REJECTED fix.** A
third winglet station corrected the sign — and then the next solve died with
`Invalid_Number_Detected`, and the perturbed start reached 222.12 min again on a
different geometry (span 2.62, cant 78 deg). More panels on a small canted
surface is more chances of the near-coincident filaments that cause this:
**it moved the artefact rather than removing it.**

Both artefacts land on exactly 222.12 min and 0.02754 N — that is this
powertrain's IDLE-POWER CEILING, what endurance becomes when drag goes to zero.
A solve reporting it has stopped modelling an aeroplane, which makes it a useful
number to recognise.

Guarded either way by `aero.mesh_convergence_check`: every champion is re-run at
16 panels/section, and the run is flagged in `run.json`, the log and the report
if the in-loop drag is negative or off by more than 10%. Plus a declared
`lift_to_drag_max = 45` enforced in the NLP — a model-validity ceiling in the
same idiom as speed_sample's `aspect_ratio_min`, set far above anything this
airframe reaches (both champions trim near 25), so **a solve landing on it is a
defect report rather than an optimum**. Written as a drag floor rather than an
L/D ceiling, because the natural form is satisfied by negative drag.

**Verified on the solve that found it.** The start that reached 222.12 min under
both the original model and the rejected station fix now converges to
**126.20350 at span 2.4751 — identical to the nominal to five decimals**. The
2.0 m regression moves -0.16% (119.93422) and the 3 m one -0.12%, which is the
size of a mesh correction, and both move toward the fine-mesh answer.

The champion at 2.49 m is mesh-converged (0.700 / 0.715 / 0.724 across
resolutions) and was never contaminated — but the run had to be redone, because
its checkpoints were solved under the old mesh.

**It was redone** — `runs/20260801T043954-…`, the section above. Both things this
paragraph said to watch happened: `spar_od_center` stayed pinned at its 14 mm
maximum, so part of that answer is the tube you can buy rather than the
aerodynamics; and the prop screen ran in a real battery for the first time and
was worth four times the span.

> **The three "infeasible corners" were a CHORD-STARVED WING, not infeasible.**
> `c_root` was pinned on its 245 mm print-bed cap in every solve that ever
> converged. At 275 mm, `motor_mount = pusher` converges in 4.6 min (110.66),
> `printed_mass_x1.10` in 5.6 min (115.24), and flatness spans 1.8 m (116.73)
> and 1.7 m (111.28) for the first time ever. All land on SM **exactly 0.0800** —
> a binding constraint that CAN be met, not an impossible one.
>
> **SM is normalised by MAC, so a wing denied chord reports its shortfall as a
> STABILITY failure.** That is the transferable lesson, and it is why a whole
> session (§14.5) diagnosed "static-margin limited" and stopped there.

Consequences: the pusher verdict is finally like-for-like — **puller 120.12 vs
pusher 110.66, both at SM 0.0800** (§14.5.8 could only compare puller at 0.08
against pusher at a relaxed 0.05). And **raising the chord cap is worth almost
nothing at the champion** — 5 seconds — while being the difference between three
studies being answerable or not. FINDINGS §15 has the chain; §14.5.8 and §14.5.9
carry RETIRED banners pointing at it.

**Two other fixes shipped, both in the flatness sweep** (FINDINGS §14.5.11-13):

- The 2026-07-30 infeasibility short-circuit **did nothing** — it gates on
  `Infeasible_Problem_Detected` and this model has only ever returned
  `Maximum_WallTime_Exceeded`. 130.6 min, zero skips. A feasibility-probe fix was
  built, measured, and **stripped** (no verdict at 5 or 20 min).
- What reclaims the time is `FLATNESS_TIMEOUT_MIN = 12.0`. **Read §15.4 for the
  corrected justification** — the original "no solve lands between 5.3 and 30
  min" was false when written (`tail_type = conventional` converges in 21.5 min).
  What survives: every converged FLATNESS member took 4.6-6.0 min. See issue 0d.

Run time **318.5 -> 188.6 min** with MORE information: the flatness sweep went
140.2 -> 50.0 min and 2 -> 4 converged spans.

**Read §14.5.11 before writing another test that stands in for a solver.** The
old `test_flatness_sweep.py` re-implemented the sweep loop inside the test and
fed the copy a status the real solver never produces — which is why a 130-minute
no-op shipped green. Suite is now **214 passing**.

---

Previously (2026-07-30, eleventh session):

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

## FIXED in the eleventh session (2026-07-30)

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
  `max_cpu_time`: a 14.5 GB solve on a 25 GB machine can swap, and it is the
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
  command continues instead of restarting, and the process exits so all ~14.5 GB
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

> **Issues 0a-0d were found by AUDITING the 2026-07-31 chord275 run's artifacts,
> not from its log — the log was 51 clean lines with no warning, no NaN and no
> traceback. A quiet run is not evidence of a correct one.** Run under audit:
> `runs/20260731T152208-endurance_sample-vtail_sample_v1-6_chord275`.
>
> **All of 0a-0e are now closed** (2026-07-31, thirteenth session) — kept below in
> short form because three of the five were resolved by finding the MEASUREMENT
> wrong rather than the aircraft, and that is the transferable part. FINDINGS §16
> carries the evidence.

### 0a. RESOLVED — the VLM cross-check was meshing, not fitting

`k_induced = -0.5035` was a near-singular AIC caused by AeroSandbox's default
spanwise `cosspace` bunching panels at wing-section boundaries. Uniform spanwise
panels fix the champion (`k = +0.0267`, `e = 1.27`, winglet −9.6% on induced
drag); a three-mesh ensemble with a `reliable` flag handles the sporadic
blow-ups that survive on high-cant geometries. `cd0_inviscid` slightly negative
was, as suspected, benign fit residual. **FINDINGS §16.1.**

The transferable lesson: the number was wrong in every run since the first, in
an artifact nobody cross-read against physics, and the check that finally caught
it was "an inviscid solver cannot produce this sign".

### 0b. PARTLY RESOLVED — the bounds are now reported; pricing them still needs runs

Every solve records `active_bounds`, the log names them, the report marks them.
What is NOT done is the part that needs solves: **which of them is worth
relaxing.** The table below is the **2026-07-31 chord275 champion's** list, at the
2.0 m cap. For the 2.5 m champion's eight, read **FINDINGS §19.4** instead — three
rows moved (`span` and `c_root` went interior, `wl_cant` and `t_dihedral` arrived),
which is itself the point: a bound list is a property of one solve, not of the
aeroplane.

| variable | value | bound | reading |
|---|---|---|---|
| `span` | 2.0000 | cap | known; §15.8 estimates 2.0 -> 2.2 m at ~1-1.5 min |
| `x_battery` | 0.4000 | max aft | **CG wants to go further aft than the bay allows** — with `ballast_kg` at 0 and SM exactly on its floor |
| `spar_od_center` | 0.0140 | max | centre spar wants to be FATTER |
| `spar_wall_outer` | 0.0005 | min | outer spar wants a THINNER wall (manufacturability floor) |
| `cs_frac` | 0.4000 | max | max control-surface fraction |
| `le_shear` | 1.0000 | max | **straight TRAILING edge — DESIGN_SPEC section 2 specifies a straight LE** |
| `washout_tip` | 0.0000 | max | **no washout — DESIGN_SPEC specifies 2 deg at the tip** |

`le_shear` and `washout_tip` are real departures from the spec sheet and neither
has ever been questioned. `x_battery` + `ballast_kg` + SM together say the design
is CG-limited in a way the span/chord discussion completely missed. `c_root` has
left this list — it is now interior at the 275 mm cap.

**The lesson from §15 applies to every row: an active bound tells you nothing
about its value until you move it.** `c_root` looked like it was strangling the
design and was worth five seconds.

### 0c. RESOLVED — nothing cost 2.7 GB; the measurement only rose

`peak_rss_gb` was a process high-water mark, so every member after the heaviest
inherited its number. The step is the tail-type study (35 design variables and a
fin surface, against 32), and the winglet solves are the run's LIGHTEST at 27.
Per-solve marks are now reset between members. The "~15 GB cap" premise was also
stale: `.wslconfig` has granted 26 GB since 2026-07-24. **FINDINGS §16.3.**

### 0d. DECIDED (user, 2026-07-31)

- **`FLATNESS_TIMEOUT_MIN` 12 -> 20.** The exposure is asymmetric: a wrongly
  timed-out member silently drops a span from the curve the sweep exists to
  draw, while the cost of being generous is bounded and visible (~16 min/run at
  the two members that currently fail). The one solve known to converge past 12
  min took 21.5.
- **275 mm chord cap promoted** into `VTailSample`, `aircraft/vtail_chord275/`
  and `aircraft/vtail_span180/` deleted.

### 0e. RESOLVED — the tree is committed

### 0f. RESOLVED — the sweep samples the optimum's neighbourhood

`[0.85 x champion span, cap]`, tied to the incumbent rather than to a constant
inherited from a retired cap. **Flatness figures from earlier runs are not
comparable**, which is the cost that had this deferred twice. FINDINGS §17.1.
The original text follows for the reasoning.

#### (original) The flatness sweep samples the wrong range

The member cap makes four bad samples cheap. It does not make them useful.

`linspace(1.5, cap, 6)` dates from a 2.2 m cap with an interior optimum. The
optimum now sits **on** the cap, so four of the six spans are 10–25% below it, in
a region §14.5.9 showed contains no aircraft — and the sweep's whole question,
"how flat is this optimum?", is about its *neighbourhood*. 1.5 m is not in the
neighbourhood of a 2.0 m optimum.

Tying the range to the champion's span (say `cap` down to `0.85 × cap`) would put
all six samples where the answer means something, and would then also make the
infeasibility cascade genuinely dead code rather than merely inert. Deferred
because it changes what the sweep *reports*, not just what it costs, and the
comparison against every previous run's flatness figure goes with it.

**Downgraded 2026-07-31, and unchanged by the thirteenth session:** at the
275 mm chord cap **4 of 6 spans converge**, so
the sweep is informative again and the curve has a visible knee exactly where
`c_root` hits its cap (-0.79 min/100mm above it, -5.45 below). Re-ranging is no
longer urgent. But note what the lower half now measures: with `c_root` pinned at
1.7 m and 1.8 m, **those two points are a property of the print bed, not of the
aerodynamics**, and would move again if the cap moved.

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

1. ~~**Apply `fixed` as a bound, not an equality row**~~ — **ALREADY DONE, and it
   was done by `detect_simple_bounds=True`** (2026-07-31 finding). CasADi hoists
   `x == v` on a bounded `x` into `lbx`/`ubx` and eliminates the variable, so
   there is no second row to be dependent with. Measured on the real model: span
   fixed at its own lower bound goes 36 variables -> 35, rows unchanged. The SVD
   above predates the flag. FINDINGS §16.2; pinned by
   `tests/test_solve_diagnostics.py::test_fixing_a_variable_adds_no_constraint_row`.
2. ~~**Don't sample a sweep exactly on a bound**~~ — moot for the same reason.
   `linspace(1.5, …)` on span's own lower bound is now one bound, not two
   constraints.

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
| `printed_mass_x1.10` | timeout, 198 iters | **CONVERGED, 5.3 min**, 112.81 min, SM exactly 0.050000 |
| flatness `span = 1.5 m` | timeout, 199 iters | **`Infeasible_Problem_Detected`**, 131 iters |

**Two of the three are STATIC-MARGIN limited**: pusher and printed_mass converge
in ~5 minutes once the floor moves and land exactly on whatever floor they get,
which is what a binding constraint looks like. `span = 1.5 m` is the odd one
out — still infeasible at 0.05, so something beyond stability is missing there,
and that is the one corner still worth a look.

`motor_mount` is therefore **settled**: puller wins on merit (119.89 at SM 0.08
vs pusher's 106.55 at a *relaxed* 0.05), and FINDINGS §10's adoption stands.

**Now shipped so this never needs a bespoke script again:** a failed member
records the constraints it missed, each labelled with the source line that made
it, under `violations` in `run.json`. Plus:

    uv run python tools/degeneracy.py --mount pusher --iters 150
    uv run python tools/parse_trace.py <ipopt.log>

**The flatness sweep no longer grinds on empty spans** (2026-07-30). It runs
DOWNWARD from the cap and stops descending once a member returns a PROOF of
infeasibility, marking the smaller spans `Skipped_Below_Infeasible_Span`.

Both halves are load-bearing. Downward, because feasibility in span is an
interval `[s_min, cap]` on this model — shrinking span at fixed area drives CL up
and makes stall, gust and stability harder, never easier — so an infeasible
member licenses an inference about SMALLER spans only. Sweeping upward, as it
did, licenses nothing: 1.5 m being infeasible says nothing about 1.6 m. And only
on `Infeasible_Problem_Detected`, because a **timeout certifies nothing** and
cascading one would silently discard spans that are merely slow.

That assumption is stated rather than hidden, and `tests/test_flatness_sweep.py`
pins all three properties including the timeout case.

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

### 3. DONE — M5.3 two-stage discrete studies (2026-08-01)

Built, and validated against a battery whose answer was already known: 65
candidates ranked in 0.5 s, same winner as eight full re-solves, priced to within
0.13 min of them. `PROP_CANDIDATES` is now derived from the catalogue (66
measured folding tables) instead of hand-listed at 8. FINDINGS §17. Original
motivation follows.

#### (original) M5.3 two-stage discrete studies — now clearly worth building

The cheap screen predicted the 11x10's full re-solve to within **1 min**
(screen 134.5, re-solve 133.5). That is the evidence this was waiting on: a
screen through `propulsion.solve()` at the incumbent operating point is a
reliable shortlister, so a study can search hundreds of candidates and
full-re-solve only the top N. EXECUTION_PLAN section 6 has the design.

### 4. ~~Prop shortlist capped at 11 in~~ — DONE (2026-07-30)

The shortlist now spans **11 to 14 in** (8 candidates), and the two blockers are
resolved:

- **Diameter-dependent mass.** `motor_prop` was a flat 190 g point mass, so a
  bigger disc arrived weightless — free thrust on the longest lever the airframe
  has. Split into `MOTOR_MASS_KG` (145 g, prop-independent) plus
  `prop_assembly_mass_kg()`, which scales as D^2.4 from a 45 g reference at
  11 in. **Reproduces the frozen 190 g exactly at 11 in**, so no champion solved
  before today moves; 14 in now costs 225 g, i.e. +35 g of nose weight that the
  bigger disc has to earn back against a 7.76 min/100 g shadow price.
- **The "ground clearance" blocker was mis-framed.** For a FOLDING prop on a
  belly-landing airframe the blades lie back along the fuselage when the motor
  stops — that is what a folder is for — so a stationary tip strike is not the
  binding case. What actually limits diameter is handling and nose structure, a
  builder's judgement, so it is now DECLARED as `prop_diameter_max_in = 14.0`
  (the `placard_speed_ms` posture) and **enforced in `powertrain()`**: a
  candidate past it raises rather than quietly winning a study.

The candidate list is derived from `PROP_CANDIDATES` rather than restated in
`discrete_options`, because two hand-maintained lists of the same thing drift and
the one that drifts silently is the one the study runs.

Unverified until a battery runs: the screen ranked 12x10 at 143.1 and 14x9 at
141.7 against 11x10's 134.5, but that screen did NOT charge prop mass. Expect the
real gain to be smaller than the screen suggests.

### 5. RESOLVED — warm start was fixed properly, and it is still a wash

The IPOPT options are wired now (`WARM_START_OPTIONS`), which recovers most of
what the seed-only path was losing — and cold is still fastest: 5.35 vs 5.58 vs
6.78 min, all returning the same objective to eight significant figures. Use the
flag for provenance, not speed; `solve` logs that. FINDINGS §16.5. Original
below.

#### (original) Warm start is a wash — do not bother, or fix it properly

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
- ~~**CF boom is invisible in the viz twin**~~ — DONE (2026-07-30). It has a
  loft now (`fuselage.boom_loft`), spanning pod tail cap to tail block, so the
  three-view and interactive model no longer show a pod and a tail floating
  apart. Viz only: `parasite_bodies` takes the pod from `_pod_loft` directly
  instead of indexing the drawable list, so drag cannot double-count, and a test
  pins that.

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
  instead of a hard-coded figure. Overshooting free RAM warns rather than clamps
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
  solve time and RAM peak are unchanged from v3.
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
  CLI** (`python -m planeopt ...`, or the exe itself when frozen): a 14.5 GB
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

- **RAM:** one NLP solve peaks ~14.5 GB (measured 14.48, 2026-08-05). Under the default 15 GB WSL
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

- ~~VLM winglet cross-check degenerated at the high-dihedral champion~~ — FIXED
  2026-07-31 (FINDINGS §16.1). It was the MESH, not the fit: uniform spanwise
  panels plus a three-mesh consensus, 6 alphas, and a `reliable` flag on every
  configuration. `e_proj > 1` was never a bug (e is against PROJECTED span).
- All absolute minutes are uncalibrated (construction + propulsion);
  rankings and active constraint sets are the trustworthy outputs.
- Chain efficiency ±10% swings the objective ±10 min — dominant uncertainty.
- `structure_extras`/`fixed_equipment` in the sample still carry a few spec
  station constants (servo positions etc.) — fine for the fixture, but keep
  them out of framework code.
- Session memory files exist under the Claude project dir and mirror much of
  this; this file is the canonical handoff.
