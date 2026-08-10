# Design Findings — sample aircraft (endurance mission)

What the optimizer has actually said about the DESIGN_SPEC.md plane so far.
All numbers from uncalibrated models (construction profile from ballparks,
propulsion from datasheets/proxy tables): **trust the rankings and the active
constraint set, not the absolute minutes** (see VALIDATION_ANCHORS.md).
Generated 2026-07-23, M3/M4 runs. Updated same day after the SM fix
(Munk fuselage term + regression derivative) and the span-cap raise to 3.0 m.

> **Stale geometry warning (2026-07-26).** Every champion below predates wing
> architecture **v4** (MODEL_DETAILS §9). Findings phrased in terms of `r1`–`r3`
> chord ratios, `center_width` or four equal-width panels describe a
> parameterization that no longer exists; `d_exp`/`dihedral_tip` still do, but
> now as one of two candidate dihedral forms. The *conclusions* (V-tail, boom,
> puller, no winglet, simple dihedral, active constraint sets) have not been
> re-tested under v4 — no optimize battery has been run on it yet. Treat the
> geometry description as historical and the rankings as pending re-confirmation.
>
> **Stale propulsion warning (2026-07-28).** Every number below also predates the
> `CT(J,Re)` prop model (MODEL_DETAILS §2.1.1) and the retirement of the
> synthetic `apc_11x6_blend`. The old single-variable fit over-stated prop
> efficiency by ~6% at the sample plane's operating point, so **absolute minutes
> below read a few percent high**; rankings survived every fit tested. See §11
> before quoting any delta that spans 2026-07-27 — one already turned out to be a
> prop swap wearing a wing's clothes.

## 1. The champion (architecture v2: generalized planform + critical-section stall)

**Span 2.84 m, and the flatness sweep now shows a true interior peak** (90 → 101 →
109 → 113 → 114.1 min at 2.75–2.84 m → 113.8 at 3.0). Champion: 1.16 m-wide center
panel, chord 181 → 140 mm with **no taper on the tip panel** (the critical-section
stall model holds tip chord for stall margin instead of leaning on washout, which
settles at just −0.4°), dihedral 7.7°/2.7°/0°/0° (inboard panels only — but the
dihedral *distribution* is a flat direction of the optimum; only the roll-stiffness
floor binds), tail arm 573 mm, spars 14×1.3 / 12×0.8 mm, ballast 0 g, cruise
9.5 m/s (wind floor active again), AUW 2034 g, 21.9 W → **114.1 min**.

Verification: multi-start 3/3 identical; **NLP vs numeric re-evaluation gap 0.0 min**
(all feasibility rules now shared); critical-section stall 7.79 ≤ 8.0 m/s with a
root-first (docile) stall pattern; tripped polars −9.7 min, ranking intact;
mass ±10% → ∓2.8 min, chain efficiency ±10% → ±10 min (still the dominant
uncertainty).

### Active constraint set

| Constraint | Status | Meaning |
|---|---|---|
| Static margin ≥ 8% | **active** | Tail sized by stability (scale 0.79, arm at its 550 mm floor). Now includes the Munk fuselage term. |
| Gust margin CL ≤ 0.7·CLmax | **active** | Sets cruise speed, not the wind floor. |
| Ballast ≥ 0 | **active at 0** | Battery at forward stop; the spec's 70 g nose lead is avoidable by layout. |
| Trim throw ≤ ±5.5° | **active** | The champion trims right at the ⅓-throw reserve — ruddervator authority is a real currency here. |
| Spar OD ≤ 14 mm (fit in the root section) | **active** | Optimizer wants max-diameter thin-wall; also: the spec's 10×8 center spar **fails** the 5 g / SF 2.0 root-stress check (~300 vs 200 MPa allowable). |
| Stall ≤ 8 m/s | active | The wing-area sizer (kept at 8.0 by decision, 2026-07-23). |

## 2. Airfoil study (discrete outer loop, full re-optimization per candidate)

| Airfoil | Endurance smooth (min) | Endurance tripped (min) | ΔCD tripped |
|---|---|---|---|
| **AG35** | **104.1** | **95.2** | 0.0054 |
| SD7037 (spec) | 99.4 | 89.6 | 0.0060 |
| E205 | 91.9 | 84.7 | 0.0043 |
| MH32 | 90.8 | 79.8 | 0.0060 |

**AG35 beats the spec's SD7037 by ~5% smooth and ~6% tripped, and the ranking
does not flip when laminar runs are lost** — a robust recommendation, not a
laminar-fragile one. Print-friendliness caveat: AG35 is thinner aft (~8.7% t/c,
thin TE) — check single-perimeter printability before adopting.

## 3. Endurance vs. wind-penetration Pareto (ε-constraint sweep)

| Min cruise speed | Endurance | Cruise power |
|---|---|---|
| 10 m/s | 99.4 min | 25.6 W |
| 11 m/s | 99.0 min | 25.7 W |
| 12 m/s | 84.5 min | 30.6 W |
| 13 m/s | 70.8 min | 37.1 W |
| ≥14 m/s | no converged solution (infeasible vs. non-converged not yet distinguished) |

Wind capability is free up to 11 m/s, then costs ~14 min per m/s. If the field
regularly sees >6–7 m/s wind, that's the trade to argue about.

## 4. Model-fidelity caveats attached to all of the above

- Cruise power sits at the **optimistic edge** of the real-aircraft bands
  (14 W/kg vs. measured 34 W/kg for a draggier Mini Talon; sailplane floor
  10–17 W/kg) — smooth polars, no prop-in-wake losses, vendor motor constants.
- **Static margin (fixed 2026-07-23, watch it anyway):** the model now carries a
  Munk slender-body fuselage term and estimates dCm/dCL by regression over a
  ±2° alpha window, because LiftingLine's local derivative oscillates with
  alpha (raw local slopes at the old champion: 0.12 → −0.01 → 0.06). Numeric
  cross-check at the new champion: SM 0.097 vs the NLP's 0.080 — same window,
  consistent. Residual caveats: the Munk term is a slender-body estimate for a
  fat pod, and LL's Cm noise is averaged, not eliminated — an external tool was
  to own the final stability verdict (that gate was removed 2026-08-06, §21;
  flight test now owns it). Remaining NLP-vs-re-eval gap ~4% is
  V-grid quantization plus this SM estimator difference.
- Tripped Δ(objective) ≈ −9 to −11 min across candidates: the design survives
  losing its laminar runs, but calibrating print-surface reality matters.
- Chain efficiency ~0.39–0.45 at cruise: the 900 kV motor is far from its happy
  point at 25 W. If hardware were ever revisited, a lower-Kv motor or bigger
  pack-voltage-to-load match is the single biggest endurance lever the fixed
  equipment list is hiding.

## 5. Scope decisions (2026-07-23, second session)

- **Planform generalization implemented** (architecture v2 of the sample
  aircraft): variable center-section width, 3 outer panels per side with
  independent dihedral and chord ratios (covers straight-with-dihedral,
  polyhedral/"curved glider", and near-elliptical families), washout variable,
  roll-moment-weighted effective-dihedral floor (≥2°) as the lateral-stability
  proxy, and the critical-section stall model that makes planform/washout
  results meaningful.
- **Winglets deferred, deliberately:** with span free at an interior optimum,
  plain span extension dominates winglets; and a credible winglet delta needs
  VLM-grade nonplanar induced-drag modeling (LiftingLine mishandles
  near-vertical surfaces). Revisit only as a span-capped mission study with a
  VLM cross-check.
- Early architecture-v2 signals: the critical-section stall model ends the
  runaway-taper incentive (the optimizer holds tip chord — r3 → 1.0 — instead
  of leaning on washout), and the dihedral *distribution* is a flat direction
  of the optimum (the floor binds, but where the degrees live barely moves the
  objective — treat any specific polyhedral shape as a choice, not a result).

## 6. Next calibration actions (highest value first)

1. Slice 2–3 wing sections at different chords → `tools/fit_profile.py` →
   calibrated construction profile (turns mass model from ballpark to data).
2. ~~Stall limit / span cap decisions~~ — decided 2026-07-23: stall stays
   8.0 m/s; span cap raised to 3.0 m, revealing the 2.59 m interior optimum.
   ~~Open follow-up: whether a 2.6 m wing is acceptable for transport/handling~~
   — decided 2026-07-23 (third session): projected span capped at 2.2 m (§7).
   Still open: whether the 14 mm spar-OD ceiling (root-section fit) is right.
3. XFOIL spot-check of AG35 vs SD7037 at Re 150–200k (one-off, per §3.1) before
   committing the airfoil switch.

## 7. Span cap + winglet study (2026-07-23, third session — M4.5)

Decision inputs: the 2.6–2.84 m champions were judged unrealistic to build and
handle; cap set at **2.2 m projected (front-view) span**, winglet-inclusive.
Model changes: arc-length panel placement (exact at high cant), `b_ref` =
projected span, explicit winglet as a separate Wing (length/cant/chord/taper/toe,
cant floored at 55° so it can't become a stall-model-invisible span extension),
sin·cos dihedral credit (a vertical panel earns none), winglet mass via its own
construction profile + 16 g tip joiners.

- **The cap costs ~7.4 min (−6.5%)**: 106.7 min at 2.2 m vs 114.1 at 2.84 m,
  and the flatness sweep still climbs into the cap (96.5 / 103.9 / 106.2 min at
  1.92 / 2.06 / 2.2 m) — span remains the binding constraint, as the shadow
  prices have said all along.
- **Winglets rejected at this cap, by three independent routes.** (1) Paired
  study: winglet-off re-optimization beats the winglet-on champion by 0.49 min
  (106.70 vs 106.21; the on-solve had already shrunk the winglet to its 50 mm
  lower bound). (2) VLM cross-check at the on-champion: k_induced is *higher*
  with the tiny winglet (0.0133 vs 0.0122) — at 50 mm it sits inside the tip
  vortex core and its toe costs side-force drag. (3) Continuous-cant study
  (outer panel freed to 88°): converges to d3 → 0° at exactly the winglet-off
  objective. The champion pipeline now auto-rejects the winglet when the off-
  solve wins (`winglet_rejected` in the run.json winglet_study block).
- Physics reading: at ~55 g printed+joiner mass and ~60–70k winglet-chord Re,
  the profile-drag + mass toll exceeds the induced saving a ≤2.2 m span budget
  can buy back. Winglets would re-enter only with a much tighter cap, a
  lighter/calibrated construction, or a mission flown at higher CL.
- Standing caveats: winglet sections have no per-station stall limit (toe
  bounded ±3° + Re floor instead); LL was conservative vs VLM on nonplanar
  benefit in the feasibility test, so the rejection is not an artifact of LL
  under-crediting — VLM rejects it too.

## 8. Fuselage phase (2026-07-23, fourth session — M4.6, streamlined loft)

Run `20260723T181336`. Freeing the fuselage (streamlined parametric loft,
emergent boom, tail_arm 0.40–1.20) recovered the entire span-cap penalty:
**114.1 min at 2.2 m projected** vs 106.7 with the frozen spec pod — the
same objective the old 2.84 m champion had, at 62 cm less span.

- **The pod shrinks to every floor at once**: cross-section 54×70 mm
  (battery-width packaging floor binding), nose 61 mm (= 1.0 d_eq proportion
  floor), boat-tail 111 mm (= 1.8 d_eq floor), bay 310 mm (battery CG
  window), 482 mm overall — a minimal streamlined envelope around the
  equipment, worth ~+6–7 min over the spec pod (55 g + wetted area).
- **CF boom decisively adopted**: the integrated printed-cone topology loses
  **8.9 min** (104.7 vs 113.6) — cone wetted area + stiffener mass beat the
  slim CF tube. The topology study prices this; the boom is a suggestion the
  study confirmed, not an assumption.
- **tail_arm 519 mm — the old 0.55 m lower bound had been binding.** With
  honest bounds the tail moves closer (shorter boom beats the longer arm;
  tail_scale sits at its 0.70 floor). Note for the tail phase: the scale
  floor is now the binding tail constraint — per-dimension tail variables
  should replace it.
- **Winglet re-rejected at the new champion** (−0.50 min paired study;
  continuous-cant d3 → 0° at exactly the winglet-off objective). VLM
  cross-check caveat: the 3-point quadratic fit degenerated at this
  high-dihedral geometry (negative inviscid CD0, e_proj > 1 artifacts) —
  treat it as qualitative this round; LL + the paired study carry the
  verdict.
- Dihedral redistribution: d0 at its 10° bound over the 1.16 m center panel,
  d1 10.8°, outer panels flat — the distribution remains a flat direction;
  the roll-stiffness floor binds, the shape is a choice.
- Verification: multistart spread ~1e-9, NLP-vs-reeval gap ~1e-5 min,
  flatness climbs monotonically into the cap (96.9 → 113.6 over 1.78–2.2 m;
  1.5/1.64 m infeasible), shadow price 7.7 min/100 g, chain-η ±10% still the
  dominant uncertainty (±10 min).
- Artifacts: `design_brief.md` (CAD round-trip step (a)) now generated per
  run; champion pod preview in `runs/fuselage_preview/`.

## 9. Tail phase + wing curve family (2026-07-24, fifth session — M4.7)

Run `20260724T052806`. First run with the wing-saddle carry-through, the
directional (vertical-tail-volume) floor, per-dimension tail variables, and
the wing dihedral-curve family all active. **Champion: V-tail retained,
109.3 min at 2.2 m projected, AUW 1925 g** (23.0 W at 9.5 m/s). The 4.8 min
drop from M4.6's 114.1 is the price of honesty, not a regression: the pod
must now physically carry the wing root, and the aircraft must actually
have yaw stability.

- **Tail-type study (new generic discrete mechanism): V-tail wins
  decisively.** Conventional −5.6 min, T-tail −8.5 min (its declared 20 g
  stab-on-fin mount is only a quarter of the gap — the fin+stab pair's
  wetted area, overheads, and the 60k Re floor on two small chords do the
  damage). The V-tail's shared-surface economy survives paying the sin²Γ
  vertical-volume tax.
- **The V-angle pinned at its 55° bound** — the Vv floor (0.030) is pulled
  by angle, not area, because angle is drag-free in-model. The steep-V
  costs that would push back (ruddervator mixing authority, yaw-roll
  coupling) are unmodeled, so the 55° cap is a declared practice limit
  doing real work: treat "how steep a V is acceptable" as a build/handling
  decision, not a model output. Tail: span 739 mm, chords 102→85 mm,
  sweep 2.6°, area 0.069 m² (spec: 0.083). Tail mean-chord Re sits exactly
  at its 60k floor.
- **Wing: the curve family converges to exactly d_exp = 0 — a simple
  4.1° uniform dihedral.** The fully curved wing loses inside its own
  continuous family (the effective-dihedral floor is met more cheaply by
  uniform angle than by tip-loaded curvature, which taxes projected span
  where it counts). The straight-spar fit constraint is inactive at the
  optimum (sag ≡ 0 at d_exp = 0): the buildable end won on aerodynamics
  alone. A fixed-span re-solve found a nearby local optimum 0.96 min lower
  at 7° uniform — the dihedral direction remains shallow; multistart
  earned its keep (spread among starts ~2e-7 around the champion).
- **CF boom re-adopted (+4.9 min over integrated)**; winglet re-rejected
  (−0.96 min paired; continuous-cant converges to the winglet-off objective
  to 1e-9 with no cant emergence). The VLM cross-check is non-degenerate
  this round and still credits the winglet's induced benefit (e_proj 1.20
  on vs 1.11 off) — the rejection is a mass + profile-drag + Re verdict at
  this span cap, not an induced-drag one. (VLM inviscid CD0 fits slightly
  negative; keep treating the fit as qualitative.)
- **Balance now comes from pod stretch, not lead**: the bay grew to 486 mm,
  putting the battery at station 102 mm with ballast exactly 0. Bay aft end
  pinned exactly at the 60%-root-chord saddle requirement (active), nose
  and boat-tail at their proportion floors, cross-section at the packaging
  floor (54×70 mm). Consequence: pod fineness is now 10.7, outside the
  shape review's declared 4–9 band — the review band and the optimizer
  disagree about long slim pods; revisit the band (Hoerner FF at f = 10.7
  is a benign 1.08) or accept review flags on app-generated pods.
- **Active set:** span cap, v_min 9.5 (wind floor), SM ≥ 8%, ballast ≥ 0,
  spar OD ≤ 14 mm, cs_frac at its 0.40 ceiling (hinge effectiveness is
  cheap authority; trim uses only 1.0° of the derived 6.1° cap), t_dihedral
  55°, tail Re 60k. Stall is now INACTIVE (7.81 vs 8.0 m/s) — the gust
  margin, not stall, sizes the wing at this cap (area 0.428 m², AR 11.3,
  loading 45 g/dm²).
- Verification: multistart spread 2e-7; NLP-vs-reeval gap 1e-5 min; SM
  re-eval 0.082 vs NLP 0.080; flatness climbs into the cap
  (102.5 / 106.7 / 108.3 at 1.92 / 2.06 / 2.2 m; ≤1.78 m infeasible this
  round). Re-solve battery: printed ±10% → +4.5/−5.3 min; chain η ±10% →
  ±9.6 min (still dominant); tripped polars −9.6 min, V-tail ranking
  intact. Shadow price 6.5 min / 100 g.
- Housekeeping: the three-view/3D artifacts draw only lofted bodies — the
  CF boom (a parasite body with no loft) is invisible between pod and tail;
  cosmetic, fix with a thin viz-twin loft when convenient.

## 10. Span 2.0 m + motor-mount study (2026-07-24, sixth session — M4.8)

Run `20260724T191453` (10 h 53 m — the last sequential battery; parallel
mode + progress logging land next). First run with the mount installation
effects modeled: the pusher now pays its prop-in-wake derate (0.95), the
puller pays pod scrubbing (×1.10) — so this run also produces the first
*honest* pusher number, and absolute minutes are not comparable to §9.

**Champion: PULLER adopted, +10.7 min over the pusher — 112.5 min at
2.0 m projected, AUW 1766 g** (22.3 W at 9.5 m/s). Better than the §9
champion despite losing 200 mm of span and gaining a drag penalty. The win
decomposes three ways, all pulling together:

- **Clean prop inflow**: the pusher's 0.95 wake derate is ~5% of chain
  power, gone.
- **Mass geography**: 190 g of motor at the nose replaces the old fight
  against a motor hanging 1.2 m aft. The bay collapses to its
  packaging/saddle minimum (pod 419 mm vs 658 mm; pod mass 162 g vs
  239 g), the battery sits at the bay front with ballast still 0, and the
  tail arm stretches to 774 mm — long arms are cheap now (35 g of boom)
  and buy SM + Vv with far less tail area (printed tail 84 g vs 113 g).
  Net AUW −159 g.
- **The scrubbing penalty lands on a shrunken pod**, so the ×1.10 costs
  little — the puller's penalty shrinks with exactly the pod the puller
  no longer needs.

Rest of the battery, all judged under the adopted puller:

- **V-tail wins again** (conventional −6.1, T-tail −8.1); V-angle at the
  55° cap again; tail sweep settles to 0 (with AC-consistent placement,
  sweep buys nothing — a flat direction, as designed).
- **Boom re-adopted** (integrated −6.4) even though it now carries only
  the tail. Winglet re-rejected (−1.19); continuous-cant converges to the
  champion exactly (no cant, d_exp → 0 — **simple dihedral confirmed
  again**, 4.1° uniform).
- Pusher-vs-puller at a glance: pusher@2.0 = 100.6 min honest baseline;
  flatness (pusher) climbs 98.3 → 100.6 over 1.9 → 2.0 m; 1.5–1.8 m all
  infeasible at this cap.
- Verification: multistart spread 7e-9; NLP-vs-reeval gap 1.6e-5;
  shadow price 7.6 min/100 g; tripped polars −12.1 min, rankings intact;
  chain η ±10% → −9.1/+8.9 min (dominant, as always).

Caveats and flags:

- **SM estimator gap now straddles the window floor**: NLP 0.080 (active)
  vs numeric re-eval 0.0745 → `sm_in_range: false` in the re-eval. Known
  ~0.006 estimator difference (Munk + regression vs re-eval window), but
  this is the first champion where it crosses the line — at the time this
  called for an external stability check before building (gate removed
  2026-08-06, §21).
- **`printed_mass_x1.10` re-solve FAILED to converge** (first battery
  member ever to fail; IPOPT assertion at the tight cap). The −10% and
  both η members are fine. Worth a re-run when the parallel battery lands.
- Puller practicalities the model does not see: prop/ground clearance and
  belly-landing behavior with a nose prop, folding-blade rest position
  against the pod, motor cooling (improves), FPV/camera field if ever
  relevant. Build judgment, not model output.
- The declared baseline in the aircraft file remains `pusher` (spec
  layout); the study adopts puller per run either way. Flip the default
  only if the user calls the puller adopted for good.

## 11. The 2026-07-27 run is not readable, and why (2026-07-28)

Run `20260727T075740` reported **123.5 min at the 2.0 m cap**, against the §10
puller champion's 112.5 min. That +11 min is **not** a wing-architecture-v4
result and must not be quoted as one.

`prop_choice` was freed as a discrete study on 2026-07-27 (`discrete_options`
in the aircraft file, dated that day), in the same run whose wing changed. The
study picked the **11×7**, not the incumbent 11×6 — identifiable after the fact
because `J_peak_eta` is a property of the table alone: 0.47295 in the v1.5
champion (`apc_11x6_blend`), 0.55556 in this one (`apc_11x7e`).

| | v1.5 champion | 2026-07-27 run | Δ |
|---|---|---|---|
| η_prop | 0.6058 | 0.6690 | **+10.4%** |
| η_chain | 0.3549 | 0.3908 | **+10.1%** |
| L/D | 20.84 | 21.09 | +1.2% |
| AUW | 1766.5 g | 1768.5 g | +2 g |
| P_elec | 22.26 W | 20.00 W | −10.2% |
| **Endurance** | 112.5 min | 123.5 min | **+9.8%** |

A +10% chain efficiency at flat mass and flat L/D produces the entire gain on
its own. **Wing v4 contributed ~1% of L/D — indistinguishable from noise.** The
v4 architecture remains unpriced.

A tempting wrong explanation, recorded so it is not re-derived: the 11×6 did
*not* "run out of table". At V = 9.5 m/s its `j_max` = 0.6074 corresponds to
3359 rpm, where it makes 0.373 N against the 0.823 N required — the bracket is
valid and it solves normally (the v1.5 champion ran it at J = 0.544 / 3749 rpm).
The 11×7 won on modelled efficiency, not by elimination.

### 11.1 …and the model it won under was wrong at the operating point

Investigating the above surfaced a bigger defect. The fits were `CT(J)` alone
over a hardcoded RPM window of 3000–10000, which averages a Reynolds-blind fit
across a 3.5× Reynolds spread. Measured against raw APC rows **inside the sample
plane's own cruise band** (J 0.45–0.68, 2800–4400 rpm):

| rpm window | 11×7E CT error | 11×7E η error | peak η |
|---|---|---|---|
| 3000–10000 (was shipped) | 2.55% | **6.90%** | 0.7167 |
| 2000–6000 | 1.20% | 2.02% | 0.6818 |
| **CT(J,Re), no window** (now) | 0.75% | **0.36%** | — |

So the 123.5 min was inflated a *second* time: at the honest fit, η_prop at that
operating point falls ~5.8%. Rankings survived every window tested
(11×7 > 11×6 > 11×5.5), which is the model's declared posture holding up — but
the absolute minutes never deserved the confidence they were given.

### 11.2 What changed as a result

- **Prop model is now `CT(J,Re)` / `CP(J,Re)`** (MODEL_DETAILS §2.1.1). No RPM
  window to choose; Reynolds is reconstructed from the operating point via one
  stored per-prop constant, accurate to 0.2%.
- **The whole published APC catalogue ships** — 443 fitted tables, median fit
  error 1.2%. Prop diameter and pitch are now a design decision, not a data
  limit. `planeopt props` lists them.
- **`apc_11x6_blend` is retired.** It was a pitch interpolation between the
  11×5.5E and 11×7E, because APC's thin-electric line has no 11×6. It was the
  only non-measured candidate in a study that then ranked it last. The real APC
  11×6 replaces it, and carries **11% more usable advance ratio** (`j_max` 0.681
  vs 0.607) than the blend predicted. New honest caveat: the real 11×6 is APC's
  thicker **sport** section, so blade section is now a confound between it and
  its two thin-electric neighbours.

### 11.3 Everything below §10 is quoted under the old prop model

No number in §1–§10 has been re-solved under `CT(J,Re)`. The rankings are
expected to hold; the minutes are expected to fall a few percent. **Nothing in
§11 is a new champion** — no battery has been run since. The two runs that would
make v4 readable are still outstanding:

1. v4 wing + `cam_11x6` pinned — isolates the wing at the incumbent prop.
2. v3 wing + `cam_11x7` pinned — the honest baseline for the prop swap.

Both under the new fit, which is the only model in which either is meaningful.

## 12. First champion under the honest prop model (2026-07-29 — M4.10)

Run `20260729T092108`, 505.8 min (8.4 h), 2-wide. The first battery run under
`CT(J,Re)` (MODEL_DETAILS §2.1.1) and with the synthetic 11×6 blend retired.

**Champion: 118.3 min at 2.0 m projected span, AUW 1768.5 g, 21.0 W at
9.5 m/s.** Prop **APC 11×7E**, puller, pod-boom, V-tail, smooth dihedral
curve, **no winglet**.

### The prop fit cost 5.3 min, and nothing else moved

The champion is the *same airframe* as the 2026-07-27 run — identical design
vector, identical AUW to 0.1 g, identical L/D 21.09. Only the propulsion model
changed:

| | 2026-07-27 (old fit) | 2026-07-29 (`CT(J,Re)`) |
|---|---|---|
| η_prop | 0.6690 | 0.6219 |
| η_chain | 0.3908 | 0.3717 |
| P_elec | 20.00 W | 21.03 W |
| **Endurance** | **123.5 min** | **118.3 min** |

−5.3 min (−4.3%), matching the −5.8% predicted from the fit error at that
operating point before the run. The old single-variable fit was flattering the
prop, exactly as §11.1 said.

### The prop verdict SURVIVED losing the blend

This was the open question, and the answer is unambiguous. Priced against the
**real** APC 11×6 rather than the synthetic pitch-blend:

| candidate | objective | vs incumbent |
|---|---|---|
| 11×5.5E | 103.5 min | −4.3 |
| 11×6 (real, incumbent baseline) | 107.8 min | — |
| **11×7E** | **117.5 min** | **+9.7 → adopted** |

So the 11×7 wins by **+9.7 min** on measured-vs-measured data. The 2026-07-27
result was confounded (§11) but its *conclusion* was right — the coarser prop is
the correct choice for this airframe, and the blend was not what made it win.

> **This verdict is a local one — the study searched 3 of 443 (2026-07-29).**
> `PROP_CANDIDATES` still lists only the three 11 in pitches (5.5 / 6 / 7) it was
> written with, so "the 11×7 wins" means "the 11×7 wins among those three". A
> free screen at this champion's operating point ranks the adopted 11×7E
> **119th of 441**: `apc_14x14e` 145.9 min, `apc_11x13ep` 143.4 min (an **11 in**
> prop — the lever is PITCH, not diameter), against the 11×7's 118.3. The
> screen holds the airframe fixed and puts the leaders at ~15% throttle, where
> the flat 0.95 ESC efficiency and the vendor motor constants are least
> trustworthy (§2.3) — so trust the direction, not the magnitude. Widening the
> shortlist is the first item in HANDOFF §5. The blocking question — must the
> prop fold? — was **answered on 2026-07-29: no**, so the whole catalogue is in
> scope, and the 0.95 folding derate must become a priced option rather than an
> unconditional one in the same pass.

Reading `J = 0.605` against the 11×7's peak-η `J = 0.538`, the design still
cruises on the falling side of the curve: a coarser prop than 11×7 is worth
pricing, and now costs nothing to add to the shortlist.

### Everything else held, and wing v4 is now priced

- **Winglet rejected again** (−0.78 min), so the champion carries none. The
  VLM cross-check still shows the winglet reducing induced drag
  (k 0.0228 vs 0.0263, span efficiency 1.47 vs 1.27) — it loses on mass and
  wetted area, not on aerodynamics.
- **V-tail holds**: conventional −8.3, T-tail −12.2.
- **Pod-boom holds**: integrated −8.1.
- **Smooth dihedral curve holds**: polyhedral2 −2.5, and `d_exp → 0` again —
  the same flat direction v3 found. Three architectures, one answer.
- **Wing v4 verdict:** the architecture change is worth **nothing measurable**.
  §11 showed it contributed ~1% of L/D; this run confirms the champion sits at
  the same L/D 21.09 as the v3-era airframe. v4 is a better *parameterization*
  (a rectangular wing and a straight taper are exact members), not a better wing.

### Verification and flags

Multistart spread 1.1e-9; NLP-vs-re-eval −1.5e-5 min; shadow price
7.40 min/100 g; cruise Reynolds 46.1 k, **inside** the fitted range.

- **SM still lands at 0.0787 against the 0.08 floor** (`sm_in_range: false`) —
  the third champion in a row to cross it. This is now a standing defect in the
  SM estimator, not a one-off — and since 2026-08-06 (§21) no external tool is
  scheduled to adjudicate it.
- **Two solves failed to converge**: `motor_mount: pusher` and the
  `printed_mass_x1.10` re-solve, both IPOPT assertions at the tight span cap.
  The pusher failure means **puller was retained by default, not by winning** —
  the mount is unpriced in this run.
- Cruise sits at the 9.5 m/s wind floor, as always.

## 13. Champion on measured folding-prop data (2026-07-29 evening — M4.11)

Run `20260729T203143`, 405 min, 2-wide, warm-started from `20260729T092108`.
First battery on **measured Aero-Naut CAM folding data** (UIUC PDB vol 3, AIAA
2020-2762) with the prop shortlist widened past 7 in of pitch.

**Champion: 134.5 min at the 2.0 m cap, AUW 1768.8 g, 18.1 W at 9.5 m/s.**
Prop **CAM 11×10 folding**, puller, pod-boom, V-tail, smooth dihedral curve,
no winglet, straight tail trailing edge.

### +16.2 min over the previous champion, in two roughly equal halves

| | Δ |
|---|---|
| measured CAM data replacing the APC rigid proxy × 0.95 (same nominal 11×6) | ≈ **+12 min** |
| pitch freed to coarsen (11×6 → 11×10) | ≈ **+13.6 min** |
| **total, 118.3 → 134.5 min** | **+16.2 (+13.7%)** |

A modelling error and a design error of about the same size. η_chain 0.372 →
0.431; cruise rpm 3372 → 2701.

**Why the modelling half was real:** `PROP_CANDIDATES` named
`aeronaut_cam_11x6_folding` and approximated it with an APC *rigid* table times a
flat 0.95 folding derate. The measured table already contains the folding
penalty, so the proxy derate charged it twice.

### The prop study, and an independent check on the data

| candidate | objective | |
|---|---|---|
| 11×6 (incumbent baseline) | 119.9 min | — |
| 11×7 | 126.9 | adopted |
| 11×8 | 129.3 | adopted |
| **11×10** | **133.5** | **adopted** |
| 11×12 | 128.0 | rejected |

11×12 falling *below* 11×10 reproduces AIAA 2020-2762's own finding — that CAM
gains continue only to p/D ≈ 0.8–1.0 — in this solver, from their data. A useful
sign the ingest is faithful.

**The cheap screen predicted the winner to within 1 min** (screen 134.5 at a
fixed operating point, full re-solve 133.5). That validates screening as a
shortlister and is the evidence M5.3 was waiting for.

### Straight tail trailing edge — free, and the tail reshaped around it

Declared as a shape constraint (`semi·tan(t_sweep) = t_c_root·(1−t_taper)`), the
exported loft comes out exact: vtail TE at x = 1433.35 mm at both root and tip,
**Δ = 0.0000 mm**, LE swept back 3.07 mm. It cost nothing measurable.

Unexpected: the optimizer responded by making the tail nearly **untapered**
(t_taper 0.968, chords 94.9 → 91.8 mm) rather than by buying sweep — with a
straight TE, taper must be paid for in sweep, so it largely stopped buying taper.
`t_sweep` landed at 0.80°, not the ~6.8° predicted from the *old* tail shape.

### Everything else held

Winglet rejected again; V-tail (conventional −9.8, T-tail −13.4); pod-boom
(integrated −11.1); smooth dihedral curve (polyhedral2 −4.0, `d_exp` → 0 for the
fourth architecture running).

### Verification and flags

Multistart spread 6.5e-8 (warm and cold starts agree), NLP-vs-re-eval −2e-5 min,
shadow price 7.76 min/100 g, cruise Reynolds 37.5 k inside the fitted range.

Carried forward, all detailed in HANDOFF's open-issues list: **SM 0.0782 under
its 0.08 floor for the fourth champion running**; `motor_mount: pusher` failed to
converge a third time (so puller is retained by default, not by winning) — this
time with 52 `NaN detected for output g, row 72` warnings confined entirely to
that solve; `printed_mass_x1.10` failed a third time; and the flatness sweep
returned 2 of 6 while consuming 43% of the run.

## 14. What was actually wrong with the solver (2026-07-30 — M4.12)

Not a design finding: a **solver-robustness** one. Two real defects were found
and fixed — and, importantly, **neither of them was why the chronic solves
fail**. The headline result of this session is a corrected diagnosis, not a
repaired battery.

| §13 symptom | verdict |
|---|---|
| NaN at `g` row 72, only in the pusher solve | **real bug, fixed** (§14.1, §14.2) |
| "failed to converge", three runs running | **was never diagnosable** — message truncated (§14.3) |
| short span / pusher / printed_mass fail | **still fail.** Three real defects found and fixed en route (§14.5.1, §14.5.5); the residue is a PRIMAL feasibility obstruction (§14.5.6-7) |
| SM under its floor, four champions running | **estimator artefact, fixed** (§14.6) |

### 14.1 The model was being evaluated outside its own bounds

`opti.solve()` ran with CasADi's `detect_simple_bounds` at its default `False`,
so every design variable's `lower_bound`/`upper_bound` was an ordinary row of the
constraint vector `g` rather than a bound. **An interior-point method is entitled
to violate constraints on the way to a solution** — it is only bounds it must
respect — so IPOPT was routinely evaluating the aircraft at negative chords and
negative boom lengths. Row 72 of `g` is the first row after the 36×2 bound rows,
i.e. `L == W`, which is exactly the row §13 saw going NaN.

Measured on a 4-variable probe: `detect_simple_bounds=True` takes the problem
from 9 inequality rows / 12 Jacobian nonzeros to **1 / 4**. On the real NLP it
removes 72 rows and puts the box where IPOPT cannot leave it.

### 14.2 One genuine unguarded NaN, inside the box

Independently of that, `fuselage.boom_body` was NaN-capable **within** the
declared bounds. The exposed boom length is not a design variable — it is

    x_tail − (pod bay_end + pod tail_len)

a difference of four of them, held positive only by the aircraft's 100 mm
boom-clearance constraint. Where that constraint is violated the length is
negative, `aero.body_cd0` forms `(ρVL/µ)**0.2` on a negative number, and the
result is NaN. Sampling the declared box at 600 random points, **23 made
`body_cd0` NaN**. After flooring the length (`geometry.smooth_floor`, a 1 mm
smooth hinge costing 2.5 µm at the clearance bound), a 1500-point sweep of the
same box found **no non-finite row anywhere in `g`** — while the same sweep
widened 50% past the bounds still finds them (rows 72, 73, 74, 113, 114), which
is precisely the region §14.1 stops IPOPT from visiting.

**Why only the pusher solve.** With `motor_mount = "pusher"` the motor hangs at
`x_tail + 0.08`, dragging the CG aft, so the optimizer works hard against a short
boom and its iterates cross zero. The puller keeps the motor in the nose and
never goes near it. §13's "52 warnings, all in one solve" was that, not a
coincidence.

### 14.3 The failure message was truncated exactly at the diagnosis

Every failed member was recorded as `str(e)[:120]`. CasADi's assertion text ends
with `return_status is '...'`, so 120 characters kept the boilerplate and threw
away the only useful word. Three runs of "failed to converge" carried no
information at all. Failures now record `return_status` and `iter_count`.

That change paid for itself immediately — see §14.4.

### 14.4 What the fixes did NOT fix

The three solves that have failed every run were re-run with everything above in
place. All three still fail, and they fail **identically**:

| solve | before | after |
|---|---|---|
| flatness `span = 1.5 m` | opaque assertion, up to 172 min | `Maximum_CpuTime_Exceeded` after **228 iterations**, 32.2 min |
| `motor_mount = pusher` | opaque assertion + 52 NaN warnings, ~50 min | `Maximum_CpuTime_Exceeded` after **222 iterations**, 31.9 min |
| `printed_mass_x1.10` | opaque assertion, three runs running | `Maximum_CpuTime_Exceeded` after **216 iterations**, 31.9 min |

(Those runs used a CPU-time cap — what AeroSandbox's `max_runtime` maps to — and
overshot the 30-minute budget by ~2 minutes of wall clock, because IPOPT checks
only between iterations and against CPU seconds. The shipped guard is now
`ipopt.max_wall_time`, reporting `Maximum_WallTime_Exceeded`.)

So the NaN was a genuine hazard and a genuine bug, but it was **not the cause of
these failures** — remove it and they fail the same way, in the same place, at
the same iteration count. Saying otherwise would have closed the issue on a
coincidence.

### 14.5 The real defect behind all three: scaling, then degeneracy

Two independent solves, two unrelated perturbations (a fixed span 25% below the
cap; a motor moved 600 mm aft), and the same signature: **~225 iterations, no
convergence, and never `Infeasible_Problem_Detected`**. That last part is the
informative one.

HANDOFF issue 2 guessed "an over-constrained corner … something in the
spar-fit / stall / Vv set goes infeasible", and issue 4 guessed the same cause
for `printed_mass_x1.10`. **IPOPT does not agree.** It never declares the problem
infeasible; it iterates until the clock stops it. That rules out the constraint
audit those issues proposed and points at slow or cycling convergence — bad
scaling, or an active set the solver keeps swapping between.

So an **iteration trace** was run on `span = 1.5 m`. It found two separate
things, one fixed and one not.

#### 14.5.1 The constraint vector spanned ten decades (fixed)

IPOPT opened the solve at **`inf_pr = 5.16e+07`**. The cause is dimensional:
`structures.spar_constraints` wrote `stress <= SIGMA_ALLOW / SAFETY_FACTOR` with
stress in **pascals** (~1e8) and the Reynolds floors as `... >= 90e3` (~1e5),
while `Cm == 0`, the tail-volume floor and the SM window are all ~1e-2. Those
rows now divide through by their own scale — `stress/allowable <= 1`,
`Re/Re_min >= 1` — which is the identical feasible set with an order-1 residual.

Measured effect on the same solve: **`inf_pr` at iteration 0 falls 5.16e+07 →
5.63**, and the iteration count drops 228 → 194. Worth having on its own — this
row dominated every solve in the project, not just the failing ones. **Write new
constraints dimensionless.**

**Regression gate — the solve that already worked still works.** Re-running the
nominal solve on the rescaled constraints:

    EXIT: Optimal Solution Found.   16 iterations, 126 s in IPOPT (4.7 min total)
    objective 119.89 min, span 2.0000 m, SM 0.080000, V 9.500 m/s

against the 2026-07-29 run's three multistart solves at the same configuration
(`prop_choice` baseline `cam_11x6`), which returned 119.8923910272774,
119.8923910903929 and 119.8923910920559. **Same optimum to five significant
figures.** As expected: dividing a constraint by a positive constant cannot move
the feasible set. Wall clock on this easy solve is unchanged (4.7 min against
4.6/5.5/9.9 cold previously — the time is model build, not solving); the win is
conditioning, and it shows on the hard corners.

#### 14.5.2 Second reading: a degenerate active set — LATER REFUTED (14.5.4)

It still does not converge, and with the primal side fixed the real signature is
visible:

| | baseline | rescaled |
|---|---|---|
| `inf_pr` at iter 0 | 5.16e+07 | **5.63** |
| `inf_pr` at the end | 2.88e-01 | 1.05e-01 |
| `inf_du` at the end | 5.78e+01 | **8.08e+04** (peaks 1.76e+12) |
| `lg(mu)` | 0.0 → −6.1 → +3.4 | never driven below −5.9, ends at 0.0 |
| median `alpha_pr`, last 60 | 2.5e-03 | **2.9e-04** |
| mean / max backtracks | 2.4 / 6 | **6.0 / 14** |
| iterations | 228 | 194 |

The problem stays essentially **feasible throughout** (`inf_pr` ~1e-1) while
**dual** infeasibility diverges by twelve orders of magnitude, the barrier
parameter cannot be reduced, and the line search collapses to α ≈ 1e-5 with 14
backtracks. Bounded primal residual with unbounded `inf_du` is the textbook
signature of **Lagrange multipliers that do not exist** — the active constraint
gradients have gone linearly dependent (LICQ/MFCQ failure). There is nothing for
IPOPT to converge *to*, which is also why it never reports infeasibility: the
design is feasible, it just cannot be certified optimal.

#### 14.5.3 The degenerate pair, named

That experiment was run: 60 iterations to reach the degenerate region, then the
SVD of the active rows' Jacobian at the last iterate.

    active rows: 7        singular values of the 7x36 active Jacobian:
    2.060e+00  1.000e+00  5.707e-01  2.278e-01  1.472e-01  5.223e-02  0.000e+00

**Exactly rank-deficient**, and the null direction has only two contributors:

    +0.874 · g[0]    span's own LOWER BOUND          (slack exactly 0)
    -0.486 · g[72]   subject_to(dv["span"] == 1.5)   (solve.py, the `fixed` dict)

`aircraft.py` declares `"span": (1.5, span_cap_m)` and the flatness sweep is
`np.linspace(1.5, span_cap, 6)` — so **its first member pins a design variable at
its own lower bound with an equality constraint**. `span >= 1.5` and
`span == 1.5` are the same constraint twice, with identical gradients.

**Caveat on this measurement, added after the fact.** The SVD above is over
`opti.g`, the SYMBOLIC constraint list, which still contains the bound rows.
With `detect_simple_bounds=True` CasADi hands plain bounds to IPOPT as `lbx`/
`ubx` and would be expected to merge `x >= 1.5` with `x == 1.5` into a single
fixed bound — in which case the solver never sees the duplicate and this exact
zero is an artefact of where the analysis looked, not a defect IPOPT suffered.
That reading is supported by §14.5.4: removing the duplication changes nothing.
Treat it as a latent modelling smell worth tidying, not as a proven solver bug.

Tidying it, if it is ever worth the churn:

1. **Apply `fixed` as a bound, not as an equality row** — one constraint rather
   than two. Deliberately NOT done: it changes the `design_variables(opti,
   inits)` signature that every user aircraft implements, and it demonstrably
   fixes nothing (§14.5.4). A breaking extension-point change needs a better
   reason than tidiness.
2. **Do not sample a sweep exactly at the variable's bound** — cheap, and the
   flatness sweep could start at `1.5 + eps` for free.

#### 14.5.4 …but that pair is NOT why the family fails either

The obvious check was run — the same solve at **`span = 1.55 m`**, off every
bound. It fails the same way:

    Maximum_WallTime_Exceeded after 183 iterations (27.6 min)
    inf_pr  5.29e+00 -> 7.06e-02        (well scaled, essentially feasible)
    inf_du  3.21e+00 -> 1.11e+15        (worse than at 1.5 m)
    lg(mu)  never below -5.9, ends +0.4
    alpha_pr last 60: median 8.6e-04    backtracks: mean 5.5, max 15

So the exact-zero singular value at 1.5 m is real, but **removing it would not
have fixed anything** — it is one instance of a degeneracy that is present across
the short-span family, not its cause. Same conclusion the `fixed`-free failures
(`pusher`, `printed_mass_x1.10`) already implied.

And the "degenerate active set" reading is wrong too. Running the same SVD at
`span = 1.55 m` found **one** active row at the last iterate — the `span == 1.55`
equality itself. One row cannot be linearly dependent on anything, so LICQ holds
there, and yet `inf_du` still reaches 1e15. Whatever this is, it is not the
constraint geometry.

#### 14.5.5 Third defect, real and fixed: a pole in the objective

`mission/endurance.py` is

    endurance = E_usable * 60 / (P_elec + P_avionics)

so the objective's gradient goes as `1/p_total²`. `P_elec` is tied to anything
physical only through `thrust == drag` — an **equality**, which an interior-point
method violates on the way to a solution. So `p_total` is not pinned positive
while iterating. Sampling 3000 points **inside the declared variable box**:

| | |
|---|---|
| `P_elec` range | **−109.3 W** to +867.3 W |
| `p_total = P_elec + 3 W` ≤ 0 | **703 of 3000 samples (23.4% of the box)** |
| samples within \|p_total\| < 1 W of the pole | 29 |
| objective range | −2.6e+04 to **+5.5e+04 min** |
| ‖∇objective‖ near the pole | **2.4e+07** |

**A quarter of the box is on the far side of a singularity**, and as `p_total →
0⁺` the endurance objective goes to `+∞` — an unbounded ascent direction that is
not an aircraft, held back only by a constraint the solver is entitled to break.

This explains every observation, including the ones that killed the earlier
theories:

- `inf_du` spiking to 1e16 **and falling back** — the gradient is ~1e7 within a
  watt of the pole and ordinary away from it. Degeneracy would not come back down.
- the line search collapsing to α ≈ 1e-5 with 13–15 backtracks — it is trying to
  step across a singularity.
- `lg(mu)` being pushed back up repeatedly.
- **never `Infeasible_Problem_Detected`** — the feasible set is fine. The
  *objective surface* is the defect.
- the champion at 2.0 m converging in 16 iterations — it starts in the
  well-behaved region and never goes near the pole. Forcing a short span (or an
  aft motor, or +10% printed mass) pushes the iterates across it.

#### 14.5.6 The reformulation — implemented, and what it did

For fixed usable energy, maximizing `E·60/p_total` is *exactly equivalent* to
**minimizing `p_total`** wherever `p_total > 0` — a monotone transform, since
`usable_energy_wh` is constant hardware. `Objective` now carries an optional
`nlp_surrogate` (always minimized) beside its reporting `evaluator`, and
`solve._solve_nlp` forms the solver's objective through `nlp_expression()` — one
seam, so a surrogate cannot be half-adopted. Endurance declares
`p_total`; the reported value still comes from `evaluate`, so no artifact
changed. Framework-level on purpose: every objective in `mission/` that divides
by a solved quantity has the same exposure.

**Regression: identical.** The nominal solve returns 119.89 min, span 2.0000 m,
AUW 1834.9 g, SM 0.080000, V 9.500 m/s, P 20.70 W — the same digits as before the
change, as a monotone transform must.

**On the hard corner it fixed the dual side, and only the dual side:**

| `span = 1.5 m` | with the pole | pole removed |
|---|---|---|
| `inf_du` at end | 8.08e+04 | **1.10e+01** |
| `inf_du` minimum | 1.02e+00 | **9.91e-02** |
| `lg(mu)` at end | 0.0 (stalled) | **−2.5** (descending) |
| median `alpha_pr`, last 60 | 2.9e-04 | **1.5e-03**, max 1.0 |
| restoration-phase iterations | 0 | **33** |
| `inf_pr` minimum | 9.12e-02 | 8.79e-02 |
| iterations / outcome | 194, timeout | 199, timeout |

Four orders of magnitude off the dual infeasibility, the barrier parameter
finally descends, and full unit steps appear. The pole was real and removing it
worked. **But the solve still does not converge**, and the reason has changed:
`inf_pr` floors at ~0.09 and will not go lower, while IPOPT drops into
**feasibility restoration 33 times**.

That is a *primal* obstruction — and it vindicates the original 2026-07-29
hypothesis this section spent two rounds arguing against. "An over-constrained
corner" was the right instinct; it was simply invisible under two layers of
numerical noise (a 5e7 scaling artefact and a 1e7-gradient pole), both of which
had to be removed before the feasibility problem could be seen at all.

#### 14.5.7 And it is stuck, not slow — the timeout was never the problem

The pusher solve looked like the best candidate for "just needs more clock": at
the 25-minute cap it had reached `inf_pr` 8.18e-03 with near-full steps and only
8 restoration phases. Given an hour it did not close.

| pusher | 25-min cap | 60-min cap |
|---|---|---|
| iterations | 187 | **474** (2.5x) |
| `inf_pr` minimum | 8.18e-03 | 6.73e-03 (no better) |
| `inf_du` at end | 4.49e+01 | **1.35e+04** (worse) |
| restoration-phase iterations | 8 | **29** |
| outcome | timeout | timeout |

`inf_pr` plateaus near 7e-03 and never closes while dual infeasibility drifts
back up. So **raising `SOLVE_TIMEOUT_MIN` would buy nothing but a longer wait** —
30 minutes stays the right default, and the cap is doing exactly its job by
turning an unbounded grind into a bounded, labelled failure.

Pusher and short span are the same primal obstruction at different severities:
pusher gets an order of magnitude closer to feasible (7e-03 against 9e-02) and
still cannot land.

#### 14.5.8 RESOLVED: the corners were infeasible all along

Asking which constraint could not be satisfied, at the pusher's last iterate:

    VIOLATED rows: 15    total violation 3.25e-02    worst 8.30e-03
      sm >= 0.08            value 0.07170   SHORT BY 8.30e-03   <-- dominant
      L == weight                           off by  6.14e-03
      winglet Re/60e3 >= 1  value 0.99504   short by 4.96e-03
      Cm == 0                               off by  4.84e-03
      ... 11 more, all <= 3e-03

    active-row Jacobian: condition number 14.7, smallest singular value 6.8e-02

Two things at once. The active Jacobian is **well conditioned** — cond 14.7 — so
LICQ holds and §14.5.2's degeneracy reading is dead for good. And nothing is
badly violated: every row is a near-miss. The dominant one, 2.5x the next, is the
**static-margin floor**, which is exactly what a pusher attacks — the mount hangs
the motor at `x_tail + 0.08` and drags the CG aft.

Relaxing that floor settles it:

| case | SM floor 0.08 | SM floor 0.05 |
|---|---|---|
| `motor_mount = pusher` | timeout at 25 AND 60 min (187, 474 iters) | **CONVERGED in 5.7 min**, 106.55 min, SM exactly 0.050000 |
| `printed_mass_x1.10` | timeout, 198 iters | **CONVERGED in 5.3 min**, 112.81 min, SM exactly 0.050000 |
| flatness `span = 1.5 m` | timeout, 199 iters | **`Infeasible_Problem_Detected`**, 131 iters |

**All three chronic failures are infeasible corners, not solver defects — and
two of the three are specifically STATIC-MARGIN limited.** Pusher and
printed_mass both converge in ~5 minutes once the floor moves, and both land
*exactly* on whatever floor they are given, which is what a binding constraint
looks like. `span = 1.5 m` is the odd one out: still infeasible at 0.05, so
something beyond stability is missing there.

`printed_mass_x1.10` also shows the mildest version of the pattern — its SM
shortfall is 5.4e-03 against pusher's 8.3e-03 — while being the only one that
cannot even close lift equilibrium (`L == weight_n` off by 1.6e-02, its largest
single miss).

- **Pusher cannot meet the 0.08 static-margin window.** It sits on whatever floor
  it is given and wants to go further aft still. And it is not being robbed of a
  win: at the *relaxed* floor it returns 106.55 min against the puller's 119.89
  at the *stricter* one. FINDINGS §10's puller adoption is now vindicated on
  merit rather than retained by default.
- **`span = 1.5 m` contains no aircraft at all** — infeasible even with the
  stability window opened up, and IPOPT now says so in 18 minutes instead of
  grinding for 32 with an opaque assertion.

> **RETIRED 2026-07-31 — read §15.** All three of these corners were CHORD
> STARVED, not infeasible. At a 275 mm root-chord cap, `printed_mass_x1.10`
> converges in 5.6 min (115.24, `c_root` 0.272) and `motor_mount = pusher` in
> 4.6 min (110.66, `c_root` 0.275 at the cap, **SM exactly 0.0800**). Both had
> been failing every run since M4.8.
>
> Note what that does to the pusher verdict: this section compared puller at the
> 0.08 floor against pusher at a RELAXED 0.05 (119.89 vs 106.55), because pusher
> would not solve at 0.08. It now solves — **puller 120.12 vs pusher 110.66,
> both at 0.0800**. So §10's puller adoption is vindicated more strongly than
> this section could show, on a genuinely like-for-like comparison.
>
> And the diagnosis "two of the three are STATIC-MARGIN limited" was reading the
> symptom. SM is normalised by MAC, so a wing denied chord reports its shortfall
> as a stability failure. That is the transferable lesson: **an SM violation on
> this model may be a chord problem wearing a stability costume.**

The four defects fixed above (bounds in `g`, the boom NaN, ten-decade scaling,
the objective pole) were all real, and all of them were *masking this*. None of
them was the cause. It took removing every one before the solver could express
the actual answer.

#### 14.5.9 Why `span = 1.5 m` is different: it is an AREA shortfall

The one corner that stayed infeasible even with the stability window opened.
Violated rows at its last iterate (`tools/degeneracy.py --span 1.5`), with the
`fixed` row shifting the numbering one past the pusher run's:

    VIOLATED rows: 15    total violation 1.1020    worst 7.5029e-01
      g[73]  L == weight_n            [0, 0]        BY 7.503e-01   <-- dominant
      g[79]  stall smooth_max <= 1    value 1.0878  BY 8.775e-02
      g[77]  sm >= 0.08               value 0.0080  BY 7.197e-02
      g[74]  Cm == 0                  [0, 0]        BY 6.921e-02
      g[75]  thrust == drag           [0, 0]        BY 3.278e-02

**Total violation 1.10 against the pusher's 0.0325 — thirty-four times worse**,
and the character is different. Pusher missed one constraint (stability) by a
hair. This one **cannot carry its own weight**: lift equilibrium is off by 0.75,
the critical-section stall limit is exceeded, and the static margin has collapsed
to 0.008 — not 0.072 short of the floor so much as absent.

That is an **area shortfall**, not a stability problem, which is exactly why
relaxing the SM floor to 0.05 rescued pusher and did nothing here: at 0.008 the
design is nowhere near even the relaxed floor. At 1.5 m of span with `c_root`
capped at 245 mm there is simply not enough wing to fly this 1.8 kg airframe
below the stall-station limit.

So the flatness sweep's bottom end is not a solver problem to be fixed — **it is
a correct answer to a question about an aircraft that does not exist.** Which is
what §14.5.10 acts on.

> **RETIRED 2026-07-31 — read §15 before acting on this.** The sentence above is
> true of the aircraft *as declared* and false as a claim about the aeroplane.
> `c_root` was capped at 245 mm by the print bed and was pinned on that bound in
> every solve that ever converged; at 275 mm, spans 1.8 m and 1.7 m converge in
> under 5 minutes. The area shortfall diagnosed here was real — it was just a
> shortfall against a *manufacturing* limit, not an aerodynamic one. 1.5 m and
> 1.6 m still fail, but on the empennage and on structure, not on wing area.

#### 14.5.10 What that changed in the product

A failed member now says what it failed ON. `SolveFailure` carries the worst
constraint violations at the last iterate, each labelled with the source line
that created it (`solve._ConstraintLabels` wraps `subject_to` during the build —
per-instance, so a build that raises cannot leave a patch behind). Verified on
the real model: 115 of 115 rows labelled, resolving to the exact lines this
section found by hand. `run.json` carries them under `violations`.

The bespoke script that produced the table above is no longer needed to answer
the question — but it ships anyway as `tools/degeneracy.py` (violated rows, then
the active-set SVD) alongside `tools/parse_trace.py` (tells scaling from
degeneracy from infeasibility on any verbose IPOPT log).

**Do not raise `SOLVE_TIMEOUT_MIN`.** 30 minutes is right: more clock buys
nothing on an infeasible corner, as the 60-minute pusher run proved.

Open, and now a design question rather than a solver one: should the flatness
sweep still spend 30 minutes per member on spans that hold no aircraft? Sampling
`linspace(1.5, cap, 6)` when the low end is infeasible is the sweep asking a
question with no answer. Take the last iterate, list the rows with
non-zero violation, then relax them one at a time and find which one frees the
solve. Unlike everything above this is a *modelling* answer — the short-span
corner may simply not contain a flyable aircraft, in which case the flatness
sweep should report it as infeasible rather than grind on it.

#### 14.5.11 The 2026-07-30 short-circuit was gated on a status this model has never returned

**It did nothing. The 2026-07-31 sweep spent 130.6 minutes on four spans and
skipped none of them.** Worth writing down carefully, because the code was
correct, the reasoning was correct, and the result was a no-op.

The sweep short-circuits when a member returns `Infeasible_Problem_Detected`.
Across every run this project has ever recorded:

    $ grep -rho '"return_status": "[^"]*"' runs/ | sort | uniq -c
         12 "return_status": "Maximum_WallTime_Exceeded"

Twelve failures, one status, and it is not the one the gate watches for. The
single observation of `Infeasible_Problem_Detected` that the gate was designed
against is the §14.5.8 table — and that cell comes from the **static-margin
floor relaxed to 0.05** diagnostic. The same row at the production floor of 0.08
reads *"timeout, 199 iters"*. The gate was built from evidence gathered in a
configuration the sweep does not run in.

The direction half of that change DID work — checkpoint timestamps confirm
2.0 → 1.9 → 1.8 → 1.7 → 1.6 → 1.5, and the four failures cost 32.7 min each
between 00:21 and 02:32.

It shipped unnoticed because `tests/test_flatness_sweep.py` **re-implemented the
sweep loop inside the test file** and fed the copy a hand-written
`Infeasible_Problem_Detected`. A test that re-implements the code under test can
only ever check the copy. The sweep is now `solve.flatness_sweep`, the tests
drive that function, and the expected statuses are written out as literals
rather than read back from `solve` — an alias would make the test agree with a
typo instead of catching it. Source-level mutation confirms all three
behaviours: sweeping upward, dropping the cascade, and dropping the member cap
each turn the suite red.

#### 14.5.12 Making the proof OBTAINABLE was the obvious fix, and it failed on measurement

If the cascade needs a certificate and the full solve never yields one, ask an
easier question: same variables, same constraints, **constant objective**. A
feasibility problem has nothing to trade feasibility against, and dropping the
objective also removes both pathologies this corner is known for — the pole
inside the variable box (§14.5.5) and the dual divergence of §14.5.8, neither of
which can occur when the objective gradient is identically zero.

Measured at `span = 1.8 m`, against the full member's 225 iterations / 30 min:

| feasibility-only solve | 5 min | 5 min, seeded from the 1.9 m champion | 20 min |
|---|---|---|---|
| iterations | 42 | 39 | 157 |
| outcome | timeout | timeout | timeout |
| `L == weight_n` miss | 2.40e-01 | 5.25e-01 | 3.56e-01 |

**No verdict at any budget, and at 20 minutes it sits FURTHER from lift
equilibrium (0.356) than the full member does at 30 (0.030).** Removing the
objective does not regularise this problem, it flattens the landscape and leaves
IPOPT wandering. Seeding from the converged neighbour is no better — consistent
with warm starts already being measured as a wash on this model.

So the probe was stripped rather than shipped. **Machinery that never fires is
the defect being fixed, not the fix.**

#### 14.5.13 What actually reclaims the time: the two outcomes do not overlap in cost

The sweep's problem was never the missing proof. It was paying a 30-minute
budget for an answer that no amount of clock improves.

| | minutes |
|---|---|
| every solve that has ever CONVERGED — multistart ×3, spans 1.9 and 2.0, the whole re-solve battery, all 7 prop candidates, the champion | **3.6 – 5.3** |
| every solve that has ever FAILED — spans 1.5-1.8, pusher, printed_mass_x1.10 | **ran to whatever ceiling it was given** |

**Not one solve in this model's recorded history lands between 5.3 and 30
minutes.** And more clock is now measured three separate times to buy nothing:
pusher at 25 vs 60 min (§14.5.7), and the two feasibility solves above.

Hence `FLATNESS_TIMEOUT_MIN = 12.0` — 2.3× the slowest solve that has ever
succeeded, so a converging member cannot plausibly be cut off by it, and a
quarter of what the four chronic spans used to cost. The cascade stays: it is
correct, it costs six lines, and it will fire the day a model does return a
certificate. It is simply not what does the work here.

Scoped to the sweep on purpose. `SOLVE_TIMEOUT_MIN` stays at 30 for the champion
and multistart, which are the solves whose failure would cost the whole run.

Still open, and unchanged by any of this: **the sweep samples the wrong range.**
`linspace(1.5, cap, 6)` dates from a 2.2 m cap with an interior optimum. The
optimum now sits ON the cap, so four of six samples are 10-25% below it, in a
region §14.5.9 showed contains no aircraft. Flatness of an optimum is a question
about its neighbourhood; 1.5 m is not in the neighbourhood of a 2.0 m optimum.
The 12-minute cap makes those four samples cheap rather than making them
informative.

### 14.6 Static margin: two estimators, not one drifting number

The NLP regressed Cm against CL over **3** alphas (−2, 0, +2) and the numeric
re-evaluation over **5** (−2, −1, 0, +1, +2). Cm(CL) is nonlinear enough here
that these are different quantities, and they differ by ~0.002 — a quarter of the
0.08–0.15 SM window. Four champions were read as missing their own floor on that
basis. There is now one estimator (`aero.SM_ALPHA_OFFSETS`), used by both; the
extra alphas survive only as the `sm_local_slopes` diagnostic.

Separately, `sm_in_range` compared an **active** constraint against its bound
exactly, so the NLP's own converged 0.07999999 already failed the test. It now
carries a 1e-4 tolerance — the same "active ≠ violated" convention `stall_ok`
has always used, and tight enough that a real miss still reports as one.

## 15. The short-span corner was the PRINT BED (2026-07-31 — M4.13)

§14.5.9 concluded that `span = 1.5 m` "contains no aircraft at all" and that the
sweep's bottom end was "a correct answer to a question about an aircraft that
does not exist." **That was true of the aircraft as declared, and false as a
statement about the aeroplane.** Raising one number — the root-chord cap, from
245 mm to 275 mm — turned two of the four chronic failures into converged
designs on the first attempt.

### 15.1 `c_root` was pinned on its bound in every solve that ever converged

The tell was there the whole time and nobody read it: `c_root` = 0.2450 exactly,
at the champion and at both converged flatness members. A bound the optimizer is
*always* against is the optimizer asking for something it is not allowed to have.

Two explanations were tested first and REFUTED, which is why the answer took a
detour:

- **Not the stall requirement.** The champion stalls at 7.715 m/s against
  `v_stall_max_ms` 8.0 — 7.5% of margin. Inactive; it binds only below ~1.7 m of
  span. Worth stating explicitly because the obvious reading — "a slow-flight
  requirement is what forces a big wing" — is wrong here, and was believed
  briefly during this session before it was checked.
- **Not the gust margin.** CL 0.781 against the 0.7·clmax_wing limit of 0.824.

The static-margin floor is meanwhile pushing chord the OTHER way — SM is a
fraction of MAC, so a fatter chord shrinks it — so whatever wanted chord was
strong enough to beat both that and the added wetted area.

### 15.2 What 30 mm of chord bought

| span | cap 245 mm | cap 275 mm | `c_root` chosen |
|---|---|---|---|
| 2.0 | 119.89 | 120.12 | 0.2533 — **interior** |
| 1.9 | 118.17 | 119.33 | 0.2645 — **interior** |
| 1.8 | timeout, 32.7 min | **116.73**, 4.6 min | 0.2750 — at cap |
| 1.7 | timeout, 32.7 min | **111.28**, 4.8 min | 0.2750 — at cap |
| 1.6 | timeout, 32.7 min | timeout, 14.7 min | — |
| 1.5 | timeout, 32.7 min | timeout, 14.8 min | — |

**At the champion the cap was worth 0.23 min.** Fourteen seconds: the wing wanted
8.3 mm more chord and then stopped, interior, with 21.7 mm of the new allowance
unused. Three independent cold starts agree to four decimals. So the printer was
never really costing the 2.0 m design anything — which is the opposite of what
"always pinned at max chord" suggests, and worth remembering the next time a
bound looks like it is strangling a design.

**At short span it was worth everything.** 1.8 m and 1.7 m had never converged in
any run, in any configuration, since M4.8. They converge in under 5 minutes at
275 mm, both pinned on the new cap. The corner was empty because of the print
bed, not because of the physics.

### 15.3 But only down to ~1.7 m — below that it is the EMPENNAGE

The wall moved from 1.9 m to 1.7 m; it did not disappear, and the failure changes
character rather than merely getting closer:

    span 1.6   L == W 2.7e-02 | Cm == 0 2.4e-02 | TAIL chord Re >= 60e3 1.9e-02 | sm 1.8e-02
    span 1.5   sm 4.6e-02 | SPAR STRESS 1.034x allowable | stall 1.030x | Cm == 0 1.9e-02

Stall — the constraint that dominated the bottom end at 245 mm — is absent at
1.6 m entirely. What binds now is the tail: static margin short, pitch trim
unclosed, and the tail chord too small to hold Re 60,000. **This is the fat-chord
spiral arriving from the other end.** Growing wing chord grows MAC, which shrinks
SM, which demands more tail volume, on a shorter boom, at a Reynolds number the
tail can no longer sustain. More chord does not fix that one — it causes it.

So the honest form of the conclusion is: **more chord buys span down to about
1.7 m and then actively hurts.** Three distinct physical walls across the sweep —
wing area at 1.7–1.8 (print bed), empennage at 1.6, structure and stability at
1.5 — where for the whole history of this project it looked like one solver
failure repeated four times.

Both remaining failures are TIMEOUTS, so they license nothing about smaller
spans; §14.5.11's standard applies unchanged.

### 15.4 The 12-minute flatness cap, measured in production

Same sweep, same machine, one run apart:

| | 245 mm cap | 275 mm cap |
|---|---|---|
| flatness phase | 140.2 min | **50.0 min** |
| spans converged | 2 of 6 | **4 of 6** |
| cost per failed member | 32.7 min | 14.7 min |

**2.8x cheaper and twice as informative in the same run.** The cap behaves exactly
as designed — 12 minutes of IPOPT plus ~2.7 minutes of graph build — and not one
converging member came close to it (worst was 6.0 min).

**A correction to how this cap was justified.** §15.4 as first written, and the
`FLATNESS_TIMEOUT_MIN` comment with it, claimed that no solve on this model lands
between 5.3 and 30 minutes. That was **false when written**, from a survey that
enumerated multistart, flatness, the battery, the prop candidates and the
champion and missed the tail-type studies — which hold the slowest convergences
here: `tail_type = conventional` took **10.6 min** at the 245 mm cap and **21.5
min** at 275 mm, both converged.

What survives is narrower and still supports the cap: every converged FLATNESS
member, both runs, took 4.6-6.0 min (n = 6), so 12 minutes is 2x the slowest —
not the 4x the bad survey implied. A tail-topology swap is a different problem
from a span perturbation, which is why a 21.5-minute convergence elsewhere does
not sink it. But the exposure is real and worth stating: **a genuinely slow
flatness member would be recorded as a timeout and its span silently lost**,
which is the exact failure mode §14.5.11 exists to prevent. If a flatness member
ever converges near the cap, raise it.

### 15.5 Consequences for the docs above

- §14.5.9's "1.5 m contains no aircraft at all" stands only for a 245 mm chord.
  The general claim is retired; 1.8 m and 1.7 m demonstrably contain aircraft.
- HANDOFF issue 0 (the sweep samples the wrong range) is **weaker** now: with 4
  of 6 spans converging the sweep is informative again, and the flatness curve
  has a visible knee exactly where `c_root` hits its cap (−0.79 min per 100 mm
  above it, −5.45 below). Re-ranging is no longer urgent.
- Note what the lower half of the curve now measures: with `c_root` pinned at
  1.8 m and 1.7 m, **those points move if the print bed moves.** Below 1.9 m the
  flatness curve is a property of the printer as much as of the aerodynamics.

### 15.6 The bed arithmetic, since the cap is now a real design lever

`c_root_max_m` is a DECLARED class attribute (the `span_cap_m` posture), because
a number every champion sits on has to be easy to find and easy to change.

The panel prints standing up — span along Z — so the bed footprint is chord ×
thickness, and Z height caps the segment LENGTH rather than the chord. Laid out
at **45° in plan** (a yaw; the airfoil stays flush on the plate) on the Bambu
A1's 256 mm square bed, a chord `c` with SD7037's 9.2% t/c needs `1.092·c/√2`
per axis:

    245 mm -> 189 mm box     275 mm -> 212 mm box     332 mm -> 256 mm, the ceiling

Axis-aligned the limit is a flat 256 mm, so the rotation is what makes anything
past 256 available. `LWPLA_A1` is unaffected: same material, same
single-perimeter skin, same printed ribs — nothing in the mass model depends on
plate orientation, so this is purely a bound change with no re-calibration.

The chosen 253.3 mm would in fact fit axis-aligned with 2.7 mm to spare — too
tight for a brim in practice, but it means **no larger printer is needed** for
the 2.0 m design. Only the 1.7–1.8 m end would benefit from going further.

### 15.7 The other two chronic corners fell to the same 30 mm

`printed_mass_x1.10` and `motor_mount = pusher` had failed every run since M4.8
and cost a full session of investigation (§14.5). Both converge at a 275 mm cap,
in under 6 minutes each:

| chronic corner | at 245 mm | at 275 mm | `c_root` taken |
|---|---|---|---|
| `printed_mass_x1.10` | timeout, 32.7 min | **115.24**, 5.6 min | 0.2721 |
| `motor_mount = pusher` | timeout, 32.7 min | **110.66**, 4.6 min | 0.2750 (at cap) |

Both land on **SM exactly 0.0800** — the signature of a binding constraint that
CAN be met, not an impossible one.

**The re-solve battery contains its own control, and it is decisive.** Chord
demand is monotone in structural mass, and the one member whose optimum was
already inside the old cap did not move at all:

| case | 245 mm | 275 mm | `c_root` |
|---|---|---|---|
| `printed_mass_x0.90` | 124.41 | **124.41 — identical** | 0.2367 (already interior) |
| nominal | 119.89 | 120.12 | 0.2533 |
| `printed_mass_x1.10` | FAILED | 115.24 | 0.2721 |

A ±10% structural-mass sweep moves the wanted chord 236.7 -> 253.3 -> 272.1 mm.
`printed_mass_x1.10` was not marginally infeasible; it was **27 mm short**. And
`printed_mass_x0.90` returning 124.41 to the decimal both times is as clean a
null control as this project is ever likely to get.

The prop study is the same story in miniature: all seven candidates gained
(+0.30 to +0.67 min), all seven landed interior, **the ranking did not change**
(cam_12x10 still wins, 141.02 -> 141.43), and the chord each one wants tracks
prop DIAMETER — 11 in -> 0.2533, 14 in -> 0.2585 — because a bigger disc is more
nose mass on a long lever, which needs more wing.

### 15.8 What is actually binding now

At the champion: **span at its 2.0 m cap, SM at its 0.08 floor, V at the 9.5 m/s
wind floor.** Chord is off the list.

Span sensitivity has to be read off the chord-INTERIOR members only — 1.7 and
1.8 m sit on the chord cap, so their slopes are the print bed talking:

    1.7 -> 1.8   +5.44 min/100mm    (both chord-limited: not span physics)
    1.8 -> 1.9   +2.60
    1.9 -> 2.0   +0.79              <- the clean number, was 1.72 at the 245 cap

**Half the apparent value of span was the wing compensating for chord it was not
allowed to have.** Whether the span optimum is far above 2.0 m is genuinely
unknown: the slope is positive and AUW is still FALLING with span (1.884 at
1.8 m, 1.836 at 2.0 m — short-span designs must fatten the chord, which costs
more mass than the longer spar saves), so the term that eventually turns the
curve over has not begun to bite. It only exists above the cap, where this model
has never been run. Extrapolating 0.79 min/100 mm suggests 2.0 -> 2.2 m is worth
roughly 1-1.5 min, not the several the pre-chord slope implied.

The experiment is the same one that worked here: raise `span_cap_m` in a variant
and sweep. Do it before spending build effort on a wider wing — chord looked
permanently strangled too, and was worth 14 seconds at the champion.

## 16. The winglet cross-check was never a cross-check (2026-07-31, thirteenth session)

Three of the open issues in HANDOFF turned out to be **measurement defects, not
physics** — and two of the three had already produced a wrong conclusion in a
previous session's notes. The pattern is worth naming: every one was found by
auditing an artifact against what the number is supposed to MEAN, and none of
them would have shown up in a log, a test, or a crash.

### 16.1 `aero.vlm_induced_check` returned an inviscid wing that made thrust

The 2026-07-31 champion recorded `k_induced = -0.5035` — the slope of a
`CD = CD0 + k·CL²` fit over an **inviscid** VLM alpha sweep. A negative slope
means drag FALLING as lift rises, which no inviscid solver can produce. The raw
sweep, which no run had ever printed, said it plainly:

    alpha 2.0   CL +0.6234   CD -0.5408
    alpha 4.0   CL +0.9599   CD -0.8772
    alpha 6.0   CL +1.3572   CD -1.2836

CD of order −CL. Not a fit artefact — the solve itself. Bisected: the main wing
alone reproduces it, with CL 3.5× the sane value; the tail and winglet are
innocent; the airfoil's camber line is byte-identical to AeroSandbox's own
`sd7037`; and a plain rectangular wing of the same aspect ratio comes out
perfectly normal.

**The cause is the VLM mesh.** AeroSandbox's default spanwise spacing is
`cosspace` applied *within each wing section*, which bunches panels against every
section boundary. This project's wing has four sections of unequal width (η at
0 / 0.16 / 0.31 / 0.80 / 1.0), so the joints carry near-coincident horseshoes,
the AIC goes near-singular, and the circulation is garbage. The signature is that
the answer swings with resolution — on the champion geometry, at 3 alphas:

| chordwise panels | 2 | 4 | 6 | 8 | 10 | 16 |
|---|---|---|---|---|---|---|
| CL at α=4° | +0.51 | +0.58 | +0.77 | +0.69 | **+0.94** | **+285.3** |

Uniform spanwise panels fix the champion outright: `k` goes −0.5035 → **+0.0267**,
`e_projected_span` −0.067 → **1.27**, and the winglet finally reduces induced
drag (k 0.0267 on against 0.0295 off, −9.6%) instead of raising it.

**But a single mesh still cannot be trusted.** With uniform spacing, individual
meshes on high-cant geometries continue to blow up sporadically — the same run's
continuous-cant plane returns k = 0.0226 / 0.0842 / 0.0219 at three neighbouring
resolutions, and a polyhedral one returns CL = 113 at (24, 12). The blow-ups look
perfectly physical in isolation (positive k, positive CD, rising polar), so no
single-mesh sanity test can catch them. The check therefore runs an **ensemble of
three meshes and reports the consensus**, flagging a configuration whose meshes
cannot agree instead of shipping a number. Across five real champion geometries
from the 2026-07-31 run, 8 of 10 configurations now agree and report physical
values; the polyhedral pair honestly reports ±17% mesh spread.

The chronic half of the issue — `cd0_inviscid` slightly negative in every run —
**is benign, as suspected.** It is the residual of a straight line through a
mildly nonlinear CD(CL²): a few 1e-4 against a CD of 1e-2, i.e. under 5%, and it
shrinks with more alphas. The sweep now uses 6 alphas rather than 3.

**Nothing in any champion moves.** The winglet verdict has always come from the
paired on/off re-optimizations (142.09 off vs 141.43 on → correctly rejected),
never from the VLM. What changes is that the second opinion is now worth reading
— and says the same thing the paired study did, which it never could before.

### 16.2 `fixed` is ALREADY applied as a bound — the fix landed a session early

HANDOFF issue 1 carried a work item: "apply `fixed` as a bound, not an equality
row", on the evidence of an SVD showing `span`'s lower bound and
`subject_to(dv["span"] == 1.5)` as two linearly dependent rows of the active
Jacobian — LICQ violated by construction.

**That is no longer true, and the reason is `detect_simple_bounds=True`**, added
the same session for an unrelated purpose (keeping the model from being evaluated
outside its own box). CasADi hoists `x == v` on a bounded `x` into `lbx`/`ubx`
and *eliminates the variable*. Measured on the real model, one IPOPT iteration
each:

| | variables | equality rows | inequality rows |
|---|---|---|---|
| span free | 36 | 4 | 34 |
| span fixed at 1.5 m (its own lower bound) | **35** | **4** | **34** |

One fewer variable, not one more row. The SVD that motivated the work item
predates the flag. `tests/test_solve_diagnostics.py` now pins the property
against CasADi's own `detect_simple_bounds_is_simple`, because the symptom if the
flag is ever dropped is a diverging `inf_du` in the flatness sweep — which cost a
session to diagnose the first time.

Consequence for the second half of that item ("don't sample a sweep exactly on a
bound"): it no longer matters. `linspace(1.5, cap, 6)` starting on span's own
lower bound is now one bound, not two constraints.

### 16.3 The winglet solves did not cost 2.7 GB — the measurement rose, not the memory

HANDOFF issue 0c read "most members ran at 11.7 GB; the two winglet solves hit
14.45 GB" and asked why the winglet pair costs 2.7 GB more. **It does not.** In
the sequential path `peak_rss_gb` was `RUSAGE_SELF`'s high-water mark, which only
ever RISES, so every member after the heaviest one inherits its number. In run
order:

| phase | recorded peak |
|---|---|
| multistart, flatness, battery, mount, prop, topology | 11.69 - 11.71 |
| **study tail_type: conventional** | **14.17** |
| **study tail_type: ttail** | **14.45** |
| wing_dihedral_form, and both winglet solves | 14.45 (inherited) |

Perfectly monotone. The step is the **tail-type study**, which is what it should
be: `conventional` and `ttail` declare fin dimensions the V-tail does not, 35
design variables against 32, and a separate fin surface in the lifting-line
graph. The winglet solves are the LIGHTEST members in the run — 27 design
variables, the winglet-off geometry having five fewer than the champion.

Two things follow. The per-solve number is now genuine: the in-process path
resets the mark between members (`/proc/self/clear_refs`, Linux), and where it
cannot, the member records `peak_rss_is_batch_watermark` rather than quietly
meaning something else. And the run-level peak is tracked explicitly, since
resetting means the process can no longer be asked at the end.

The remaining premise of 0c was also stale: "a ~15 GB WSL cap" is the default,
but `.wslconfig` has granted 26 GB since 2026-07-24 (`free -g`: 25 GB + 10 GB
swap). The margin at 14.45 GB is ~10 GB, not 0.5.

### 16.4 An active bound is now reported, not reconstructed

Issue 0b observed that the champion sat on eight declared bounds while the
session discussed three. The reason is structural: bounds live in the aircraft's
`design_variables`, so the framework never saw them and no artifact could name
them — reading them off meant comparing `run.json` against the aircraft file by
hand.

Every solve now records `active_bounds`, the progress log names them, and the
report marks each design variable that sits on one. The recorder wraps
`opti.variable` for the duration of the declaration only, the same
instance-bound discipline `_ConstraintLabels` uses.

This does not price anything, and the framing matters: **an active bound tells
you nothing about its value until you move it.** `c_root` was pinned in every
solve this project ever ran and was worth five seconds when finally released —
while being the difference between three studies being answerable or not (§15).

### 16.5 Warm start does not pay, and now that is measured rather than assumed

`--warm-start` seeded primal values only. Issue 5 asked for either dropping it or
wiring IPOPT's real warm-start options; both were done — the options
(`warm_start_init_point` plus the `warm_start_*` family and `mu_init`) are now
applied whenever a seed is given, because IPOPT ignores that family otherwise and
its default `bound_push`/`bound_frac` shove the starting point 1% off every bound
before the first iteration, on a champion that sits on eight of them.

Then it was measured, on the most favourable case that exists — the same aircraft
and mission, seeded with the previous champion's own design vector, so the seed
IS the answer:

| | wall clock | objective |
|---|---|---|
| cold | **5.35 min** | 120.12168 |
| warm, seed only (the old behaviour) | 6.78 min (+27%) | 120.12168 |
| warm, seed + IPOPT warm-start options | 5.58 min (+4%) | 120.12168 |

The fix is real — it recovers most of what the seed-only path was throwing away —
and the answer is still no. **Do not reach for `--warm-start` expecting speed;**
it is a provenance tool. The reason it cannot do better is structural: a run
artifact records `dv`, not IPOPT's multipliers, so an interior-point method
restarted from it has to rebuild the dual side from scratch, and on a problem
with eight active bounds that is most of the work. `solve` logs this whenever the
flag is used, so nobody has to find this section first.

Worth noting for the regression trail: all three land on the same objective to
eight significant figures, which is also the check that this session's changes
moved no optimum.

## 17. Searching the catalogue instead of a shortlist (2026-08-01 — M5.3)

HANDOFF issue 3. A discrete study costs one full NLP re-solve per candidate, so
the prop study priced **8 of 661** shipped tables and every widening of that list
was a negotiation about run time. `solve.screen_discrete` removes the cost
instead of the candidates: hold the champion's airframe and operating point
fixed, re-solve only the powertrain per candidate (`propulsion.solve`, no NLP),
and hand the optimizer the leaders.

**Measured on the 2026-07-31 battery, whose answer is already known.** That run
spent ~40 minutes on eight full prop re-solves and adopted `cam_12x10` at
141.43 min. The screen ranks 65 candidates in **0.5 seconds** and puts the same
prop first, at **141.56 min** — 0.13 min from the number eight solves produced:

| rank | candidate | screened | powertrain only | mass |
|---|---|---|---|---|
| 1 | ancf_12x10 | **141.56** | 142.37 | +10 g |
| 2 | ancf_14x9 | 138.29 | 141.03 | +35 g |
| 3 | ancf_13x11 | 137.51 | 139.23 | +22 g |
| 4 | ancf_12x9 | 136.25 | 137.06 | +10 g |

Two design points carry that accuracy:

- **Mass is charged**, at the run's own measured shadow price, from
  `fixed_equipment`. Without it the screen is systematically biased toward big
  propellers — a 14 in disc that arrives weightless is free thrust on the longest
  lever the airframe has, which is exactly the defect that kept the diameter cap
  at 11 in until 2026-07-30. It moves 14x9 from rank 2-on-power to a clear
  second, and would move it further on a heavier airframe.
- **It is opt-in per attribute** (`discrete_screen = {"prop_choice": 4}`).
  Declaring an attribute asserts that changing it moves nothing the airframe
  solve fixed — true of a propeller, false of a tail type. The framework cannot
  detect that; it would have to know what an attribute means.

What the screen cannot see is re-optimization: a candidate that would repay its
mass by reshaping the wing looks worse than it is. So it is a SHORTLISTER, four
candidates are re-solved in full, and the incumbent is priced as the baseline
whatever the screen thinks of it.

**The shortlist is now a rule, not a list.** `PROP_CANDIDATES` is derived from
the shipped catalogue — every measured, folding table inside the declared
diameter limit, 66 of them — rather than eight hand-written entries. The rule is
the one the hand-list already followed, and deriving it removes the hazard the
old comment itself warned about: two hand-maintained lists of the same thing
drift, and the one that drifts silently is the one the study runs. The incumbent
key changed (`cam_11x6` -> `ancf_11x6`) and the propeller did not: same table,
same size, same 1.00 derate.

### 17.1 The flatness sweep now samples the optimum's neighbourhood

Issue 0f, deferred twice and no longer deferrable at a 3 m cap. The range was
`linspace(1.5, cap, 6)`, a constant inherited from a 2.2 m cap with an interior
optimum; once the optimum sat ON the cap, four of six spans were 10-25% below it
in a region shown to hold no aircraft. The sweep now samples
`[0.85 x s*, cap]` around the champion's own span, which is the same range
whether the optimum is interior or on the cap.

The cost is stated rather than hidden: **flatness figures are no longer
comparable against runs before 2026-08-01**, because they are no longer the same
spans. That is precisely why it was deferred — and the alternative was a sweep
whose samples were chosen by a constant from a cap that has been retired twice.

## 18. The IN-LOOP model made thrust, and the optimizer went looking for it (2026-08-01)

Found by running the 3 m span-cap battery, twenty minutes in, and it is the most
serious defect this project has had — not because the error is large but because
of WHERE it is. §16.1's VLM defect was a second opinion that gated nothing. This
one is inside the NLP, so the optimizer is not merely misinformed by it; it is
attracted to it.

### 18.1 The symptom: 222 minutes and an L/D of 889

The flatness member at span 3.0 m returned **222.1 min** against a champion of
126.4. A flatness member re-optimizes everything at a FIXED span, so a number
that far above the free optimum is a contradiction on its face: the free solve
could have gone to 3.0 m and did not.

    drag_n            0.0275 N        (champion: 0.749 N)
    P_elec            9.79 W          (champion: 19.49 W)
    AUW               2.495 kg        -> L/D = 889

Re-evaluated numerically through the M1 path, the same design gives the same
drag, so this was not a symbolic-vs-numeric mismatch. The model itself believed
it. Decomposed by surface:

| configuration | drag |
|---|---|
| wing alone | +0.826 N |
| wing + vtail | +0.902 N |
| **wing + winglet** | **-0.108 N** |
| all three (as solved) | -0.033 N |

The winglet — 52 mm long, canted 86 degrees — was contributing about **-0.93 N**.
And the neighbourhood is discontinuous, which is the tell that this is numerics
rather than physics: at `washout_tip` -3.0 deg the drag is +0.86 N, at -3.854
(the solved value) it is -0.03, and at -4.0 it is **-5.33**.

The same 222.12 min turns up again in §18.3 on a completely different geometry,
which is what identifies it as a ceiling rather than a design.

### 18.2 The cause: an unregularized vortex core

A lifting-line filament's induced velocity goes as **1/r**. AeroSandbox's
`vortex_core_radius` — the radius inside which that singularity is smoothed —
defaults to **1e-8 m**. Ten nanometres is not regularization; it means a control
point that happens to land a micron from a filament receives an enormous induced
velocity, and the circulation solution built on it is garbage. On a small,
strongly canted winglet the panels sit close enough for exactly that.

Sweeping the core radius on the offending design, at the shipped 4 panels per
section and at 16:

| core radius | 1e-8 | 1e-6 | 1e-5 | **1e-4** | 3e-4 | 1e-3 |
|---|---|---|---|---|---|---|
| drag, 4 panels/section | **-0.034** | +0.863 | +0.902 | **+0.903** | +0.904 | +0.909 |
| drag, 16 panels/section | +0.923 | +0.921 | +0.916 | +0.915 | +0.915 | +0.913 |

**1e-4 m is the shipped value**, chosen from that table rather than from taste:
it fixes the sign, brings the in-loop mesh within ~1.3% of a 16-panel one on
this design and ~2% on the champion, and sits a full order of magnitude below
where the core starts distorting the FINE mesh as well (at 1e-3 the 16-panel
answer itself moves 8%). It is also the physically conservative direction — a
real vortex core on a model wing is millimetres, not nanometres.

### 18.3 Refining the mesh was tried FIRST, and it is the wrong fix

The obvious response to "four panels is too few" is more panels, and it was the
first thing implemented: a third winglet station, which on the offending design
gives +0.900 N against the converged +0.920, for four extra panels a side.

**It failed in the very next solve, in two different ways.** The nominal solve
died with `Invalid_Number_Detected` after 28 iterations — a NaN where there had
been none — and the perturbed start converged to **222.12 min again**, on a
DIFFERENT geometry (span 2.62, cant 78 deg instead of span 3.0, cant 86 deg).

That is the lesson worth keeping: **refining the mesh moved the artefact rather
than removing it.** More panels on a small canted surface is more chances of the
near-coincident filaments that cause this, which is also why the NaN appeared.
Regularizing the core attacks the mechanism instead, costs nothing in graph size
on a solve that already peaks near 12 GB, and cannot relocate the problem
because it removes the singularity everywhere rather than re-drawing where the
panels fall.

Evidence that it is the same failure at both places: both artefacts converge to
**exactly 222.12 min and 0.02754 N of drag**. That number is not a coincidence
and not an aircraft — it is this powertrain's IDLE-POWER CEILING, the endurance
you get when drag goes to zero and the bus is carrying only the motor's no-load
current. Any solve that reports it has stopped modelling an aeroplane.

### 18.4 And the champion is now checked against a finer mesh

A fix for one mechanism is not a defence against the next one.
`aero.mesh_convergence_check` re-runs the champion's operating point at 16 panels
per section and compares: negative in-loop drag is never converged whatever the
fine mesh says, and a disagreement over 10% flags the run in `run.json`, in the
log, and in the report notes. Two lifting-line runs at one operating point,
against a battery measured in hours.

**What this does not do is make the in-loop model right** — it makes a wrong one
say so. The honest statement of the model's status is: 4 panels per section is a
deliberate economy bought against a 12 GB solve, the core radius is what keeps
that economy from being wrong, and the champion is the only point re-checked at a
resolution that would catch a failure.

### 18.5 Verified on the solve that found it

Three solves under the regularized core, and the third is the one that matters —
it is `perturbed_0`'s start, which reached 222.12 min under BOTH the original
model and the rejected station fix:

| solve | objective | span | drag |
|---|---|---|---|
| 2.0 m sample (regression) | 119.93422 (was 120.12168, **-0.16%**) | 2.0000 | 0.832 N |
| 3 m nominal | 126.20350 (was 126.35968, -0.12%) | 2.4751 | 0.751 N |
| **3 m, the artefact-finding start** | **126.20350** | **2.4751** | **0.751 N** |

The start that twice found a 222-minute aeroplane now lands on the same interior
optimum as the nominal, to five decimals. Both regressions move ~0.15%, which is
the size of a mesh correction rather than of a design change, and both move
TOWARD the fine-mesh answer.

### 18.6 A model-validity ceiling on L/D, as the next backstop

The core radius fixes the hole that was found. A battery is ~24 solves and only
the champion gets a fine-mesh cross-check, so the next hole would again be
discovered by reading an implausible number hours later. `lift_to_drag_max = 45`
is declared by the aircraft and enforced in the NLP — the same posture as
speed_sample's `aspect_ratio_min`, a limit on what this model may be believed
about rather than on the aeroplane. Both champions on record trim near L/D 25,
so it cannot quietly cap a real design, and **a solve that lands ON it is a
defect report rather than an optimum** — it will say so in `active_bounds`.

One subtlety worth recording, because the natural form is wrong: it is written
as a DRAG FLOOR, `drag * ld_max / W >= 1`, not as `L / drag <= ld_max`. The
natural form is *satisfied* by negative drag — a negative number is comfortably
below any ceiling — so it would have let the exact iterate this constraint exists
to refuse walk straight through. Against WEIGHT rather than lift, because lift
equals weight only at a converged point while weight is a sum of positive masses
at every iterate.

### 18.7 What it means for the runs already on disk

The 2026-08-01 battery was stopped twice — once at its second flatness member,
and again after the rejected station fix produced a NaN — and its checkpoints
were discarded both times, because they were solved under a superseded model.

Earlier runs are not retro-invalidated, but they are not cleared either — no run
before this one recorded a mesh check. What can be said: every champion since
M4.8 sits at a winglet cant of 55 degrees or has the winglet rejected outright,
and at 55 degrees the model is converged (0.700 / 0.715 / 0.724 across
resolutions). The corner that fails is high cant, which is where the
`continuous_cant` study member goes by construction — so that member is the one
to distrust in any pre-2026-08-01 artifact, and it has never won a study.

## 19. The span curve turns over at 2.50 m (2026-08-01 — the 3 m run)

`runs/20260801T043954-endurance_sample-vtail_sample_v1-7_span300`, 127 minutes,
**champion 150.53 min**. The run exists because span had sat exactly on its cap in
every solve this project has ever done, so no span figure it has ever quoted was
a property of the aeroplane.

### 19.1 It is a genuine interior optimum, and it is FLAT

Span landed at **2.4970 m** against a 3.0 m cap — the first time it has not been
pinned. Three multistarts agreed to five decimals, and the flatness sweep (which
now samples around the champion rather than from a constant 1.5 m) drew both
sides of the curve for the first time, **6 of 6 members converged**:

| span (m) | 2.104 | 2.283 | **2.462** | 2.642 | 2.821 | 3.000 |
|---|---|---|---|---|---|---|
| endurance (min) | 123.44 | 125.43 | **126.20** | 125.71 | 124.53 | 122.03 |

(That sweep is at the pre-study incumbent prop, hence 126 rather than 150.)

**Going to 3.0 m COSTS 4.2 min.** The extra span stops paying well before the cap,
because wing and spar mass overtake the induced-drag saving — and AUW confirms it,
rising 1.912 -> 1.932 kg between 2.475 and 2.497 m where it had been FALLING with
span at every earlier cap.

Two consequences worth carrying:

- **The 2.0 m cap costs ~6.3 min** (119.93 at 2.0 against 126.20 at 2.475, same
  configuration). §15.8 extrapolated 1-1.5 min for 2.0 -> 2.2 m from a slope
  measured against a wall; the real curve is steeper near 2.0 and then flattens.
- **The optimum is flat to +-180 mm** (under 1 min across 2.28-2.64 m), so the
  buildability call — transport, storage, hand-launch — has real room before it
  costs endurance. That is a better answer for a builder than the peak itself.

### 19.2 The prop is worth more than the span

`ancf_12x10` beat the incumbent `ancf_11x6` by **+24.33 min**, which is four
times what the whole span increase bought. It is the same story the reports have
carried for four sessions — cruise J below peak-eta J, i.e. the design asking for
a coarser prop — and it took M5.3's screen to make the question affordable: **65
candidates ranked with no NLP, and the full re-solves reproduced the screen's
ordering exactly** (150.53 / 146.93 / 146.15 / 144.53 against screen ranks
1/2/3/4).

The caveat is unchanged and now matters more: the champion cruises at **19.3%
throttle**, where a flat 0.95 ESC efficiency and vendor motor constants are least
trustworthy (MODEL_DETAILS 2.3). The RANKING is solid; the absolute minutes at
that throttle are the uncalibrated part.

### 19.3 The winglet is retained for the first time — and read the bound

Winglet-on 150.53 against winglet-off 149.88: **+0.65 min**, where every earlier
run rejected it. Both independent checks agree it is real:

- `aero.mesh_convergence_check`: in-loop drag 0.70712 N against 0.72724 N at 16
  panels/section, **-2.8%, converged** — the champion is not a mesh artefact,
  which after §18 is not a formality.
- The rebuilt VLM ensemble, 3-of-3 mesh consensus on both configurations and both
  flagged reliable: **k_induced 0.01839 with the winglet against 0.02278
  without** (-19.3%), e_projected 1.240 against 1.001. This is the first run in
  which that cross-check has been worth reading at all (§16.1), and it agrees
  with the paired re-optimizations.

**But `wl_cant` sits on its 55-degree LOWER bound**, i.e. the optimizer wants the
panel FLATTER than the floor allows. That floor exists precisely to keep a
winglet from becoming "a span extension the Schrenk stall model cannot see"
(MODEL_DETAILS 3.6). So the honest reading is not "a winglet finally pays" but
**"the design wants more span, and with the projected-span cap binding, a
low-cant winglet is the only door left open"**. Before adopting it, price the
same panel as span.

### 19.4 What the champion is pinned against

Eight bounds, now reported rather than reconstructed (§16.4):

| variable | at | reading |
|---|---|---|
| `spar_od_center` | 14 mm max | **the centre spar wants to be fatter** — part of this answer is the tube you can buy, not the aerodynamics |
| `wl_cant` | 55 deg min | see §19.3 — wants to be a span extension |
| `t_dihedral` | 55 deg max | V-angle at its declared handling cap, as in every run since M4.7 |
| `le_shear` | 1.0 max | straight TRAILING edge — DESIGN_SPEC specifies a straight LE |
| `cs_frac` | 0.40 max | max control-surface fraction |
| `fullness` | 1.0 min | straight taper, the simplest member of the chord family |
| `d_exp`, `ballast_kg` | 0 | simple dihedral, no ballast — both benign |

`span` and `c_root` are absent for the first time. **`spar_od_center` is the one
to move next**: it is the same shape as the `c_root` story in §15 — a declared
manufacturing limit that has been quietly setting an aerodynamic answer.

### 19.5 Everything else held

Pod-boom over integrated (**-8.22 min**, a wider margin than at 2.0 m — a longer
wing wants a longer tail arm and the boom buys it cheaply), V-tail over
conventional (-4.36) and T-tail (-6.20), smooth dihedral curve over polyhedral
(-4.19). Static margin exactly on its 0.08 floor, stall clear, NLP-vs-re-eval gap
**0.0000**.

### 19.6 …and the cap stays at 2.0 m anyway (user decision, 2026-08-04)

The experiment answered its question and the answer was **not adopted**. That is
the correct outcome for this kind of run and it is worth writing down as such,
because the tempting reading — "the optimizer found 2.5 m, so build 2.5 m" — is
wrong on this project's own terms: `span_cap_m` is a BUILD decision, in the same
class as `c_root_max_m` and `prop_diameter_max_in`, and nothing in this model
prices transport, storage, hand-launch or the print bed.

What changed is not the number but its **standing**. Before the run, 2.0 m was a
decision with an extrapolated price (§15.8: 1-1.5 min for 2.0 -> 2.2 m, read off
a slope measured against a wall). After it, 2.0 m is a decision with a measured
one:

| against the 2.5 m optimum | cost of capping at 2.0 m |
|---|---|
| at the incumbent `ancf_11x6` | **~6.3 min** (119.93 vs 126.20, both post-§18) |
| at the `12x10` the 2.5 m run adopted | **~8.5 min** (142.09 vs 150.53) |

The second row is the one a builder should be quoted, and it is the larger of the
two: a coarser prop and a longer wing want each other, so pricing the cap at the
incumbent prop **understates it by a third**. The 142.09 figure predates the
vortex-core fix by -0.16%, so the true gap is nearer 8.7 min.

Three consequences that outlive the decision:

1. **The §15.8 extrapolation was wrong by a factor of four or five**, in the
   direction of underestimating span. That is the fourth time a slope measured
   against an active bound has misled this project (§14.5, §15.1, §16.1 are the
   others), and the pattern is now specific enough to state as a rule: **a
   gradient at a bound predicts the objective only over distances small compared
   with how far the bound is from the interior optimum.** Here the bound was
   500 mm away and the extrapolation was run 200 mm.
2. **The 150.53 min champion is out of the sample's feasible set.** It is a
   2.497 m aeroplane. The best 2.0 m number is 142.09 min from the chord275 run,
   which predates both this fix and the mesh/VLM guards — so at the moment of
   this decision the project has **no guard-checked champion at its own cap**,
   and a fresh 2.0 m battery is owed.
3. **Capping span raises the pressure on the winglet, it does not lower it.** At
   2.5 m — interior, no cap binding — the winglet was retained with `wl_cant`
   already on its 55 deg LOWER bound (§19.3). Back at 2.0 m the projected-span
   cap binds directly, so any winglet the optimizer adopts there should be read
   as a span request that found a door, and priced against span before it is
   believed. The 2.0 m champion of record rejected the winglet; if the re-run
   adopts it, that reversal is the finding, not a footnote.

`aircraft/vtail_span300/` is **kept and marked RETIRED** rather than deleted (the
`chord275` precedent went the other way because that experiment was *adopted*, so
its package would have been a duplicate of the sample). Its `name` now derives
from `VTailSample.name` instead of restating it, so a retired package cannot
drift into claiming a version whose feasible set it no longer shares.

## 20. The battery converged and described a different aeroplane (2026-08-05)

The 2.0 m battery owed by §19 ran overnight and produced a clean champion:
**142.087 min**, mesh check converged at -0.46%, NLP-vs-re-eval gap 2.2e-5,
multistart spread 1.6e-7, stall clear, SM in range, winglet rejected again and
the 12x10 prop picked again — both of the things HANDOFF said to watch, resolved
as predicted. Nothing failed. The audit of the artifact nonetheless found
**seven claims the run was not entitled to make**, and the shape of them is the
finding: *every guard green* is not the same as *the artifact describes the
aircraft*.

### 20.1 The sensitivity phases belonged to a superseded design

The flatness sweep and the re-solve battery ran immediately after the
multistart. The discrete studies and the winglet study run AFTER them, and they
change the design — the prop study adopted the 12x10 (+22 min) and the winglet
study rejected the winglet. So the artifact shipped:

| in the artifact | the aeroplane it describes |
| --- | --- |
| champion, 142.087 min | 12x10 prop, no winglet |
| flatness curve, 119.93 min at 2.0 m | incumbent 11x6, winglet on |
| all four ±10% sensitivities | incumbent 11x6, winglet on |
| shadow price, -0.0663 min/g | incumbent 11x6, winglet on |

Nothing in the run said these were different aircraft. The deltas even *look*
right — the battery's four entries are internally consistent, each computed
against the multistart champion — which is precisely what makes it dangerous: a
sensitivity that is not a sensitivity of the shipped design reads exactly like
one. This is the same failure as §16 (the winglet cross-check measuring its own
mesh) and §18 (the in-loop model making thrust): **the number was never wrong,
the thing it was a number ABOUT was.**

Fixed by ordering: characterization now runs after the winglet study, with the
champion's discrete attributes and winglet state applied to the aircraft first.
The +20 g shadow-price bump moved into the battery so the reported trade rate is
also the final design's; the multistart bump stays, unreported, because
`screen_discrete` needs a shadow price before the studies can run. The property
is an ordering one, so `tests/test_phase_order.py` pins the order with a fake
NLP rather than re-deriving it from aerodynamics.

### 20.2 Four things the run knew and did not say

Smaller, same family — the run had the information and the artifact did not
carry the claim:

1. **The objective was limited by `v_min`, not by the airframe.** 142.09 min at
   9.5 m/s, while the sweep's own peak is 143.01 min at 9.0. Correct behaviour,
   undisclosed conclusion: the number answers "best at or above 9.5 m/s", and
   was read as "best". Now `diagnostics.v_min_price`, priced and noted.
2. **Non-convergence was recorded as infeasibility.** V = 8.0 m/s carried
   `infeasible: "the iteration is not making good progress"` — a statement about
   the root-find's step size, 0.28 m/s above computed stall. Sweep points now
   carry a `cause`; `trim_not_converged` reports as UNKNOWN.
3. **The static margin changes sign inside its own regression window.** 0.0800
   reported, local dCm/dCL of +0.187, +0.138, **-0.022 at the trim alpha**. Known
   (HANDOFF issue 2, and it cannot be closed in this app) — but a known limit
   that nothing announces is indistinguishable from a clean result downstream.
   Now `sm_sign_consistent`, warned and explained beside the margin.
4. **A fully resumed phase looked like a skipped one.** Multistart and flatness
   reported 0.0 minutes; both were solved in full the previous evening and came
   off disk under the same fingerprint. The resume was legitimate — that is what
   §18.7's fingerprint guard is for — but "this battery re-searched the design"
   was not a claim the artifact could support or withdraw. Now
   `diagnostics.phase_resumed`.

### 20.3 A prediction that did not come true, and why that was not a bug

HANDOFF predicted the regularized vortex core (§18) would move the 2.0 m
champion by ~-0.16%, to ~141.9. The measured champion is **142.087 against the
pre-fix 142.086 — no movement at all**, which reads immediately as the fix not
having been applied. It was applied: all four `asb.LiftingLine` call sites pass
`LL_VORTEX_CORE_RADIUS`, and the same run shows the shift plainly in the
flatness sweep, **120.1217 -> 119.9342, exactly -0.156%**.

The difference is the winglet. The core artefact is a near-coincident-filament
effect concentrated on high-cant winglet panels; the flatness and multistart
solves carry live winglet design variables and the champion does not, because
the winglet study rejects it. The prediction was extrapolated from a nominal
configuration that keeps its winglet and never applied to this champion.

Worth recording for the same reason §19.1 records the span extrapolation: **a
model-change delta measured on one configuration does not transfer to another
whose active features differ.** The cost of not writing it down is an afternoon
spent ruling out a fix that was never broken.

### 20.4 The per-solve RAM figure was folklore

`DEFAULT_PER_SOLVE_GB = 13.0` against a measured 14.48 GB peak. The error is not
symmetric — `budget_to_parallel` divides by it, so optimism hands out a
concurrency the machine cannot honour and the OOM killer takes a battery
measured in hours, while pessimism costs one concurrent solve on a machine that
is single-core-bound anyway. Now 14.5, with the prose in `memory.py`, `cli.py`,
`geometry.py` and `solve.py` agreeing.

## 21. The yaw axis LL was believed not to have, and the gate that was removed (2026-08-06)

Two decisions in one session, one of them a correction and one of them a trade
the user made with the cost stated. Both concern the same question: **who checks
this aeroplane?**

### 21.1 "LL has no yaw axis" was false

`MODEL_DETAILS` §8.4, and the same sentence copied into `aircraft.py` twice,
justified the declared vertical-tail-volume floor with "LL has no yaw axis:
without a constraint, fins optimize to zero and V-tails shed angle." The second
clause is true. **The first is not, on asb 4.2.10.** LiftingLine answers sideslip
with the correct sign and a clean monotonic trend in V-angle.

What it gets wrong is the magnitude, measured against a 3-mesh VLM ensemble on
the 2026-08-05 champion:

| Γ | LL `Cn_β`/deg | VLM ensemble | LL over-predicts |
| --- | --- | --- | --- |
| 20° | +0.000454 | +0.000211 | **2.15×** |
| 30° | +0.000789 | +0.000472 | 1.67× |
| 40° | +0.001151 | +0.000785 | 1.47× |
| 55° | +0.001678 | +0.001252 | 1.34× |

So the floor remains a proxy — but for a completely different and much narrower
reason than the one recorded. LL's yaw axis is a usable **shape** and an unusable
**number**. `aero.vlm_directional_check` now supplies the number on every
champion.

**The floor turns out to be well calibrated — and "per degree" nearly hid that.**
`Cn_β = 0.000116 + 0.002245·sin²Γ` fits within 2.5% at every angle measured, so
the tail's own `sin²Γ` scaling is right, though the constant is not zero: ~7% of
directional stability comes from the winglet, wing and fuselage, which `Vv`
credits to nobody.

The trap is what to conclude from that. The champion returns a positive `Cn_β`
even at Γ = 20°, which reads as "the floor is loose, tail area is being wasted,
go and recalibrate it." **That conclusion is wrong, and only the unit conversion
shows why.**

| Γ | `Cn_β`/deg | `Cn_β`/rad | vs the conventional 0.04–0.10/rad band |
| --- | --- | --- | --- |
| 20° | +0.000211 | 0.0121 | ~4× below |
| 40° | +0.000785 | 0.0450 | at the lower edge |
| 55° | +0.001251 | 0.0717 | inside |

Γ = 20° weathercocks in the arithmetic sense and nowhere else. The declared
0.030 — whose entire stated provenance was "the spec's own tail works out to
0.034, and 0.02–0.04 is class practice" — lands `Cn_β` exactly where an
independent directional-stiffness argument would have put it. The floor was a
better constraint than its own justification claimed, and it took measuring to
find that out. **Do not loosen it.**

**The V-angle was investigated for un-pinning and should stay pinned.** Γ sits on
its 55° bound every run, and the natural suspicion is that a steep V hides an
unmodeled handling cost. Measured through LL (the VLM ignores control-surface
deflections entirely — identical `CL`/`Cm` at 0° and 10° ruddervator):

| Γ | pitch authority | yaw authority | `\|Cl_δr/Cn_δr\|` |
| --- | --- | --- | --- |
| 20° | 1.55× | 0.43× | 0.346 |
| 55° | 1.00× | 1.00× | 0.141 |

Adverse roll per unit yaw command **improves** 2.46× with steepness and yaw
authority more than doubles. The only cost that rises with angle is reduced pitch
authority, and that is already modeled — the V-tail is real canted geometry and
the trim-throw constraint is active at the champion. Adding a yaw-aware
control-authority budget would pin Γ *harder*. §9's original reading stands: how
steep a V is acceptable is a build and handling decision, not a model output.

### 21.2 The external stability gate was removed, and what that costs

Every prior session deferred the stability verdict to flow5 — "an external tool,
not a code change, and it gates BUILDING rather than running" (HANDOFF issue 2).
**On 2026-08-06 the user removed that gate**, on the argument that the app should
stand on its own. All 12 references are gone.

The cost, stated plainly because a removed safety gate should never be
discoverable only by its absence:

- **Every cross-check this app performs is AeroSandbox checking AeroSandbox.**
  `mesh_convergence_check`, `vlm_induced_check` and `vlm_directional_check` are
  independent *methods* sharing one *implementation*. They catch discretization
  and mesh artefacts. They cannot catch a systematic error in the library.
- **That failure mode is live, not historical.** §16 is the precedent — an
  induced-drag check that shipped `k = -0.50` in every run it ever ran in. And
  during this session the VLM returned `CL = +123.1` on the sample aircraft's own
  DV_DEFAULTS geometry at mesh (8, 8), where LiftingLine returns 0.52 on the same
  aeroplane. The ensemble caught it. An ensemble of the same code is what caught
  it, which is exactly the limit being described.
- **The `sm_local_slopes` fidelity issue is now unadjudicated.** It was open,
  known, and explicitly assigned to the external tool. It is still open and now
  assigned to nothing but flight test.

The guard that made the directional check survivable is worth recording, because
it is not the induced check's guard. A sideslip sweep has no polar shape to lean
on, so it leans on symmetry: a symmetric aeroplane must return
`Cn(-β) = -Cn(β)`. **That was not sufficient.** The blown-up (8, 8) mesh returned
`cn_beta = +1.849` — positive, reading as a comfortably stable aircraft, 830×
too large — and it was *perfectly antisymmetric*. Symmetry alone admits it. The
blunt sanity bound on CL is what rejected it. Both guards are load-bearing, and
`tests/test_directional_check.py` pins that with the measured numbers.

## 22. The static margin is the aeroplane's, and the guards moved earlier (2026-08-06)

### 22.1 Cm now has a second opinion, and it settled where the nonlinearity lives

§21.2 recorded that drag had two cross-checks and Cm had none — backwards,
since Cm is the quantity this project already calls its weakest and the only one
that decides whether the aeroplane is flyable. Both halves of that gap are now
closed, and between them they diagnose the standing static-margin defect.

`aero.vlm_static_margin_check` samples the SAME alpha window through the SAME
estimator (`static_margin_from_polar`, Munk term included), so the only
difference from the in-loop number is the aerodynamic method. On the spec
aircraft at the 2026-08-06 run's own trim point (V 10.5, α 6.078):

| | static margin | local dCm/dCL across the window |
| --- | --- | --- |
| LiftingLine (in-loop) | 0.054 | −0.022 → +0.037 → +0.125 → +0.159 |
| VLM (inviscid) | 0.113 | +0.124 → +0.127 → +0.131 → +0.135 |

The VLM is very nearly linear — 9% spread, never negative — and lands mid-window
where LL lands below the floor. **Read alone this looks like an exoneration. It
is not.**

`mesh_convergence_check` now asks the same question of the margin that it always
asked of drag, and that is what settles it:

| LL spanwise | SM | first local slope |
| --- | --- | --- |
| 4 | +0.0541 | −0.0220 |
| 8 | +0.0515 | −0.0255 |
| 16 | +0.0491 | −0.0281 |

The sign change **does not wash out under refinement — it deepens**, while the
margin is still falling at 16 panels. So three explanations existed and two are
now eliminated: it is not a discretization artefact (it converges), and it is not
the inviscid geometry or load distribution (the VLM sweep is monotone). What
remains is the **viscous Cm at Re ≈ 46 k**, which is exactly where laminar
separation bubble behaviour lives.

**The uncomfortable conclusion is the supported one: the low margin and the sign
change are most likely real.** The design does sit below its 0.08 floor and does
lose pitch stiffness at the fast end of its window. The cross-checks did not
clear the aeroplane; they removed the excuses.

Note what Cm is NOT compared at: the trim point. Trim drives Cm to ~0 by
construction, so a delta there is noise about nothing. The comparable quantity is
the slope, and the verdict that matters is whether a sign change survives
refinement — `sign_flip_survives_refinement` and `sign_flip_is_mesh_artefact` say
which, and demand opposite responses.

`LL_SM_MESH_TOL` is 0.002, set to the magnitude ALREADY known to change verdicts
here (HANDOFF issue 5: a ~0.002 estimator difference read, for four champions
running, as the design missing its floor). The spec aircraft moves 0.0050 across
a 4× refinement and therefore fails it, correctly. An earlier draft sat at 0.005,
which the measured case passed by 1e-5 — a threshold chosen to be survived rather
than to mean something.

### 22.2 The guards moved to where the decisions are

Every expensive failure this project has had was a **selection-time** failure
found late: the L/D 889 aeroplane (§18), the winglet cross-check measuring its
own mesh, the in-loop model making thrust. In each the model was untrustworthy
*while the studies were choosing the design*, and nothing said so until the run
was over. §20's fix moved characterization AFTER the studies so it describes the
shipped design; this is the complementary half.

**A candidate is no longer adopted on an untrusted objective.** A discrete study
wins by comparing its objective against the incumbent's, and that comparison is
meaningless if the drag is the mesh's. `objective_is_mesh_trustworthy` — the
drag half of the mesh check, well under a second — now runs at the moment of
adoption. A candidate that wins on a mesh-dependent number is refused, the
incumbent stands, and the run says so.

**An untrusted champion is no longer characterized.** The flatness sweep plus
four full re-optimizations are the most expensive phase after the multistart, and
all of them describe the objective the design reports. A gate between "design is
final" and "characterize it" costs under a second and skips both when the
objective is not trustworthy — keeping `mass_bump`, which is not a sensitivity
member but the only source of the shadow price the rest of the run quotes.

Deliberately **fail-open**: a member carrying no operating point, or a check that
raises, counts as trustworthy. A guard that read "I cannot tell" as "reject"
would delete candidates for having crashed rather than for being wrong.

The gate is the DRAG half only. The reporting cross-checks — static margin,
lateral derivatives — still run against the re-evaluated champion afterwards, so
no number the artifact quotes changed. The gate answers go/no-go; it does not
report.

## 23. The chord family cannot reach an ellipse, and more stations cannot help (2026-08-06)

Asked whether the wing is "still generated in paneled sections", and whether the
superellipse should become a spline. Both halves were measured rather than
argued, and both answers are no — for reasons that are worth keeping because the
obvious reading of each is wrong.

### 23.1 The parameterization stopped being paneled; the geometry did not

`superellipse_chords` is a continuous chord law and the optimizer no longer picks
panel breaks or panel chords. But `station_grid` samples it at **5 stations**
(`WING_STATIONS_INNER/OUTER = 2`), those become 5 `asb.WingXSec`s, and
AeroSandbox lofts straight lines between them. The built wing is a four-trapezoid
piecewise-linear loft; LiftingLine's 4x spanwise subdivision refines the solution
*on* that loft, not the loft itself.

This is self-consistent, which is the property that matters. Lift, drag, `s_ref`,
`c_ref`, mass (`massmodel.printed_surface`) and every geometry constraint all
read the faceted object. There is no seam where the objective sees a smooth
curve and the mass model sees a trapezoid, so no solve can buy free area. The
one place two representations of one curve coexist — `_wing_curve_z`'s analytic
small-angle integral for the spar-sag constraint, against the built loft's
midpoint-sampled dihedral accumulation — agrees to **under 5 mm** at semi = 1.5 m
across the whole `dihedral_tip`/`d_exp` box, against spar depths in the tens of
mm.

What the faceting costs, at `DV_DEFAULTS` (c_root 220 mm, taper 0.682, eta_break
0.389), 4 panels against the curve being sampled:

| fullness | max chord error | area error |
|---|---|---|
| 1.0 | 0.0 mm (exact) | 0.00% |
| 2.0 | 10.7 mm (4.9% of root) | −1.17% |
| 4.0 | 30.7 mm (13.9% of root) | −2.00% |

At `a = 1` the loft is exact: the family degenerates to what four trapezoids can
represent, which is where the champion sits.

### 23.2 `a = 2` is not an ellipse at any taper this project can build

The law is `c = c_root·[lam + (1−lam)(1−eta^a)^(1/a)]`, so the `lam` term is a
constant chord added under the whole span and `a = 2` gives a rectangle-plus-
ellipse blend. It becomes a true ellipse only as `lam -> 0`, and `taper`'s
declared floor is 0.35. **The docstring's claim that a = 2 is "a true ellipse"
was wrong for every reachable design** and has been corrected.

Planar span efficiency by classical lifting line (Glauert/Fourier, validated
against the exact case — `lam = 0, a = 2` returns e = 1.0000):

| taper \ fullness | 1.0 | 1.5 | 2.0 | 3.0 | 4.0 |
|---|---|---|---|---|---|
| 0.35 (floor) | 0.9798 | **0.9891** | 0.9815 | 0.9652 | 0.9552 |
| 0.55 | 0.9720 | 0.9729 | 0.9666 | 0.9554 | 0.9487 |
| 0.682 (defaults) | 0.9613 | 0.9613 | 0.9569 | 0.9492 | 0.9446 |
| 1.0 | 0.9352 | 0.9352 | 0.9352 | 0.9352 | 0.9352 |

**e has an INTERIOR maximum in `a`** — visible in the 0.35 row above, where it
rises 0.9798 -> 0.9891 and then falls — and the peak sits near a = 1.2-1.5 for
tapers below ~0.6, flattening onto the 1.0 edge as taper rises. Past the peak,
pushing "toward the ellipse" makes loading LESS elliptic, because at nonzero lam
a larger `a` is a fuller MID-SPAN, not a rounder tip.

That single curve explains both behaviours the project has seen, and neither is a
discretization artefact:

| configuration | taper | `fullness` | e-optimum here | reading |
|---|---|---|---|---|
| `vtail_sample` @ span 2.0 m | 0.5456 | **1.305, interior** | a ~ 1.2 | sitting essentially ON the optimum |
| span300 champion (§19.4) | — | **1.0, pinned** | at/below the box edge | peak has flattened onto the bound |

So `fullness` is a knob the optimizer USES and solves to its physical optimum
when the taper leaves it room, and pins only where the peak has migrated to the
edge of the declared box. **Correction to an earlier draft of this section**,
which claimed e falls monotonically with `a` and that `fullness` always pins at
1.0: both were wrong, generalized from the span300 champion alone, and
contradicted by this section's own 0.35 row.

### 23.3 The faceting FLATTERS fullness, so refining stations pushes the wrong way

The natural hypothesis — 4 panels cannot resolve a tip curve, so the ellipse's
benefit is hidden and `fullness` pins low as an artefact — is backwards. The
4-facet loft reports e = 0.9606 at `a = 2` against the true curve's 0.9569, and
0.9538 against 0.9446 at `a = 4`. Truncating the tip **raises** computed span
efficiency by up to ~1%. Refining the stations would make high fullness look
slightly *worse* and drive `fullness` harder into the bound it already occupies.

### 23.4 What stations cost, measured on the 16 GB Mac

Full converged solves, `endurance_sample` / `vtail_sample_v1.7`:

| panels | stations | iters | build | solve | total | peak |
|---|---|---|---|---|---|---|
| **4** (current) | 5 | 85 | 17.4 s | 441.0 s | **7.8 min** | **10.18 GB** |
| 5 | 6 | 101 | 17.9 s | 603.3 s | **10.6 min** | **12.09 GB** |
| 6 | 7 | — | 23.5 s | — | — | **13.15 GB** |
| 8 | 9 | — | — | — | — | **killed at 14.54 GB** |

The 6- and 8-panel peaks come from 3-iteration runs, which is sound because the
full solves validated the capped ones exactly (10.18 vs 10.19; 12.09 vs 12.10):
**peak is established within the first three iterations and never rises again.**

Two corrections to standing assumptions:

- **The CasADi graph is not the memory.** Build is 17–24 s and never exceeds
  0.81 GB. All of the peak is IPOPT's function generation and factorization.
  `geometry.station_grid`'s docstring reasoning — that stations grow the graph
  and the graph is the peak — is right about direction and wrong about mechanism.
- **The 14.5 GB figure is the 25 GB WSL box's, not this machine's.** Here a
  4-panel solve peaks at 10.18 GB against 16 GB total. `plan_parallel` returns
  width 1 at *every* station count, so there is no concurrency to lose — extra
  per-solve time multiplies straight through a battery. One added panel is +35%
  wall clock and +19% IPOPT iterations (the NLP also gets harder to converge, not
  just slower per step); the §19 span300 battery would go 127 -> ~172 min.

### 23.5 Verdict: no spline, no extra stations

A spline sampled at 5 stations produces the identical 4-facet loft, so it changes
the reachable family and nothing else. A knotted B-spline is additionally
excluded: `eta_break` is a design variable, so evaluating one means comparing a
DV against a knot, which is the branching-on-a-DV-value that the whole module
forbids. (A Bernstein/Bézier basis would be admissible and would delete the
`exp(a·ln eta)` NaN hazard the current law needs analytic endpoints to survive —
worth knowing, not worth doing.)

The cost is +35% on every battery, on a machine with no headroom, and the case
for spending it is weaker than "the optimizer wants shapes it cannot reach". It
already reaches the one it wants: `vtail_sample` solves `fullness` to 1.305
against a computed e-optimum of ~1.2, with `taper` interior at 0.5456. Two knobs,
one landing on its physical optimum and the other freely chosen — that is a
family with SLACK in it, and slack is not fixed by adding knobs.

This is §19's verdict a second time: **a better parameterization, not a better
wing.** Reopen only on evidence of a wanted shape the family cannot express —
e.g. an aircraft whose `taper` pins at the 0.35 floor while `fullness` also
saturates, which would mean the peak has left the box rather than been found
inside it.

## 24. A run that could not reproduce itself, and a way to exercise it cheaply (2026-08-06)

### 23.1 The artifact was missing its own input

`EXECUTION_PLAN` §2 has described `run.json` as carrying "design vector,
constraint activity, shadow prices, re-solve battery, diagnostics" for as long
as it has existed. **It carried four of those five.** There was no design vector
anywhere in a run directory.

Everything the artifact recorded was an OUTPUT. `geometry` gives span, area,
aspect ratio and mean chord, and none of those invert back to taper, fullness,
washout, dihedral exponent or the seven tail variables — so rebuilding a
champion meant re-running the optimizer that produced it. This was found by
trying to reproduce the 2026-08-05 champion for the static-margin cross-check
(§22) and having to fall back to `DV_DEFAULTS`, which is a different aeroplane.

`RunResult.design_vector` now records the **complete effective vector** —
defaults with any overrides merged in, never a diff, because a diff sends the
reader to a Python file that has since changed.

**The trap, which caught the first implementation.** The obvious reading is that
`dv=None` means "the defaults". It does not. `aircraft.geometry`'s own docstring
says `dv=None` builds *"the fixed v1.2 spec design; else the parametric
architecture"*, and those are materially different aeroplanes:

| | `geometry(None)` | `geometry(DV_DEFAULTS)` |
| --- | --- | --- |
| wing area | 0.3575 m² | 0.3330 m² |
| projected span | 1.7985 m | 1.8609 m |
| mean chord | 0.1986 m | 0.1850 m |

7% in area. So filling the field with `DV_DEFAULTS` for a spec-design run would
have written an authoritative-looking vector that rebuilds an aeroplane the run
never evaluated — **strictly worse than the empty field it was fixing**, because
nothing would flag it. The field is `{}` for a spec run, disambiguated by
`diagnostics["design_source"]` (`"spec"` / `"parametric"`), and `{}` round-trips
correctly since `geometry(recorded or None)` is `geometry(None)`. A test pins
that the two geometries really do differ, because the fact is surprising enough
to be "simplified" away by a later reader.

A second defect surfaced from a test rather than from reasoning: `np.float64`
subclasses `float`, so `isinstance(v, (int, float))` catches it — but
**`np.int64` subclasses neither** and would have reached `json.dump` uncoerced,
failing at write time, after the solving was done. The coercion keys on
`numbers.Real` with `bool` excluded explicitly (`bool` IS a `Real`, and a
discrete flag recorded as 1.0 rebuilds the aircraft with a float where it
declared a switch).

### 23.2 `--max-iter`, and why it has to shout

`SOLVE_MAX_ITER` was a module constant. It is now `--max-iter`, threaded
CLI → `optimize` → `_solve_many` → `_solve_nlp` → `opti.solve`, defaulting to
the same 1000 so an ordinary run is unchanged.

The point is bug-hunting at a cost the machine can absorb. Most defects this
project ships are in plumbing — graph construction, study branching, artifact
writing, the GUI lifecycle — not in whether IPOPT converged, and all of that is
exercised by a solve that merely TERMINATES. At `--max-iter 3` the whole
pipeline runs in seconds instead of hours. Unlike `--solve-timeout-min` it is
deterministic, which is what makes it usable as a test oracle; wall-clock
truncation is not reproducible.

**A capped run produces a complete artifact** — champion, discrete studies,
sensitivities, a build document — describing an aeroplane no solver ever
finished converging. That is the easiest false claim this project has ever been
able to make by accident (§20 is a list of seven it made on purpose-built
code). So `diagnostics["max_iter"]` is always recorded, `iteration_truncated`
is set whenever it is below the default, and a note is inserted at **position
zero** of `notes`: *"THIS RUN IS NOT AN OPTIMIZATION."*

The tests pin the cap arriving at every member rather than merely being accepted
by the CLI. The dangerous failure is not a wrong cap — it is a flag that looks
applied and silently does nothing, which would burn exactly the hours it was
invoked to avoid.

## 25. The spar ceilings were a constraint the model already had (2026-08-06)

§19.4 named `spar_od_center` "the one to move next", reading its 14 mm ceiling as
a purchasing limit quietly setting an aerodynamic answer. It was not a purchasing
limit. It was **a hard-coded copy of a constraint the model already enforces
honestly**, and the copy had gone stale.

### 25.1 Where 14 mm came from

§2 records the bound's origin as "Spar OD <= 14 mm (fit in the root section)".
`geometry_constraints` now enforces exactly that, symbolically, against the chord
the optimizer is choosing: `spar_od <= SPAR_DEPTH_FRACTION * t_c * c`, plus the
dihedral curve's sag. Evaluate it by hand:

| `c_root` | section admits `0.70 * t_c * c` |
|---|---|
| 0.160 m | 10.30 mm |
| **0.220 m** | **14.17 mm** — where 14 came from |
| 0.275 m (the cap) | 17.71 mm |

The number was frozen when `c_root` was not yet free. It is now, so the box was
overriding the real constraint by up to 3.7 mm. The outer spar's 12 mm ceiling
was the same artefact and was active alongside it, so freeing one alone would
only have moved the binding row. Both went to 20 mm — clear of the widest
section any declared `c_root` offers, so the fit constraint is what binds.

The lower bounds stayed. They are not physics — stress alone would keep a spar
off zero — but `structures.tube` forms `id = od - 2*wall`, and below `od = 2*wall`
the section area and I change SIGN. An interior-point iterate may pass through
points its constraints forbid, so that has to be a box, which IPOPT cannot
violate, rather than only `wall <= od/2 * 0.45`, which it can.

### 25.2 What it bought, measured

Paired single solves, `endurance_sample` / `vtail_sample_v1.7`, same initial
guesses. The baseline arm pins both ODs at the bounds they were ACTIVE against,
which reproduces the pre-change optimum exactly:

| | baseline | freed | delta |
|---|---|---|---|
| endurance | 119.4946 min | **119.7810 min** | **+0.29 min** |
| AUW | 1.8510 kg | **1.8411 kg** | **-9.9 g** |
| drag | 0.83813 N | 0.83422 N | -0.0039 N |
| `spar_od_center` | 0.0140 (pinned) | 0.0151 | left the active set |
| `spar_od_outer` | 0.0120 (active) | 0.0065 | left the active set |
| wall clock | 626 s | 548 s | — |

Both OD bounds are now interior and **`spar_wall_center` and `spar_wall_outer`
are the binding structural rows instead.** That is the honest next question, and
unlike the ODs it is probably real: 0.5 mm is about the thinnest CF tube wall
that can be bought and socketed without crushing. Treat it as a decision, not a
cleanup.

**Read the magnitude with care.** One solve per arm, no multistart, and the outer
spar reversing from *pressed against* 12 mm to *choosing* 6.5 mm is a large
enough move that the arms may not sit in the same basin. The direction and the
change in the active set are solid; +0.29 min is not a precision figure. An
earlier attempt at the freed arm also hit `Maximum_WallTime_Exceeded` at 205
iterations under a 20 min cap and needed 45 min to converge — freeing a bound
that was holding a variable still is not free for the solver.

### 25.3 The boom is a constant ON PURPOSE, and that is the opposite case

Asked the same question of `BOOM_OD_M`, the answer inverts. Freeing it would make
the boom SHRINK to its bound, and the shrink would be an artefact:

- MASS does not respond. `structure_extras` charges `0.056 * boom_len`, a flat
  56 g/m annotated "12x10 CF". A 4 mm boom weighs what a 12 mm boom weighs.
- STRUCTURE does not respond. `structure_constraints` calls
  `structures.spar_constraints` exactly twice, both times for a WING spar. The
  boom has no stress and no deflection check; the only constraint naming it is a
  LENGTH one.

So only drag pulls on it, against one weak opposing term (a smaller `r_cap`
steepens the pod's afterbody closure). The optimizer would buy a 5 mm tube
holding a V-tail out on an arm `tail_arm` may stretch to 1.2 m.

**The distinction worth carrying:** `spar_od_center`'s ceiling was a duplicate of
a constraint that EXISTS, so deleting it let real physics bind. `BOOM_OD_M` is
the only stand-in for physics that is ABSENT, so deleting it would remove the
last thing holding the answer up. Two bounds that look identical from the outside
and want opposite treatment. Held at 12 mm by user decision; the reopen order is
recorded at the constant itself.

## 26. The first `vtail_rcv2` evaluation, and a filter that chose the answer (2026-08-06)

Today's session changed 17 files and none of it had been run. The bug-hunting
pass that followed found its first defect in the cheapest stage available — an
M1 evaluation, no optimizer, ~9 minutes — and it was not in any of the new code.
It was in code that has been shipping since M1 and had never met an aeroplane
that provoked it.

### 26.1 An endurance aeroplane whose best point was its fastest speed

`vtail_rcv2` has never been executed. Its first run reported:

    best 53.76 min at V = 16.5 m/s

16.5 m/s is the FASTEST speed the sweep samples, which for a loiter design is
the wrong end of the curve by construction. The sweep's own peak is **71.16 min
at 12.0 m/s** — 32% more endurance, at a speed the run never mentions.

Nothing was wrong with the arithmetic. `best = max(candidates, key=objective)`
is correct, and `candidates` is correct too: of the thirteen speeds that
trimmed, twelve were removed by the **trim-throw limit**. The RC v2 equipment
package puts the motor at station 34.7 mm and the battery at 115 mm, which makes
the spec aeroplane nose-heavy enough (static margin 0.85 against a required
0.08–0.15) to need more than its 6.53 deg of ruddervator at every speed below
16.5. One point survived, and that point became the headline.

### 26.2 Why nothing said so, and why the existing mechanism could not

§20 built `v_min_price` for exactly this shape of claim: *"the best this
aeroplane can do"* and *"the best it may do at or above 9.5 m/s"* are different
sentences and the artifact could only write the first. That fix is structurally
unable to see this case:

    feasible ──[gust margin, advance ratio, trim throw]──> airworthy ──[v_min]──> legal
                                                              ^
                                                    v_min_price starts HERE

By the time `v_min_price` is called, the twelve points are already gone. It
looked at a one-element list, found its peak was the reported best, and
correctly returned `None`.

**The trap is what the artifact says instead.** `constraints.trim_deflection_deg`
read **-6.29 deg** against a 6.53 deg cap — comfortably inside, apparently a
design with throw to spare. It is the deflection of the one point the cap
admitted. The same is true of the reported CL and advance ratio. Every number in
that run was correct and the run as a whole was not readable: a nose-heavy
aeroplane that cannot trim across its own speed range presented as a healthy one
with mediocre endurance.

### 26.3 The fix

`solve.airworthiness_price` asks `v_min_price`'s question of the filters that
run before it, and the filter predicates now live in one named dict that both
the filter and the pricing read — a rule cannot be priced in one place and
applied in another. It reports the excluded peak, which rules excluded it, what
it costs, and **how many speeds each rule removed**, because "one awkward point
dropped out" and "this filter chose the answer" are different findings and the
count is what separates them. It returns `None` when the reported best already
is the peak, so a healthy run carries no note rather than an empty one.

`run.json` gets `diagnostics.airworthiness_price`, `report.html` gets it under
the existing "What limits this result" heading next to the v_min price, and the
note ends by naming the trap directly: read the reported deflection, advance
ratio and CL as properties of the point that SURVIVED the filters.

### 26.4 What this says about where to look next

The defect was reachable from an M1 evaluation with no optimizer, no NLP and no
new code — it needed a new AIRCRAFT. Four aircraft packages have been run
against this pipeline and all four were comfortable inside their throw limits,
so the branch that reports on the filter had never been asked for. The general
form is worth keeping: **a guard that has only ever been evaluated on designs
that pass it has not been tested**, and the cheapest way to test one is a
differently-shaped aeroplane rather than a longer solve.

## 27. Running the new code, and the three things that only running it found (2026-08-06)

§26 came from the cheapest stage of a bug hunt — an M1 evaluation, no optimizer.
These came from the next two, and they share a shape worth naming: **each is a
number the code already computed and no one had made it answerable for.**

### 27.1 `--max-iter` crashed the pipeline it was added to exercise

§24.2 added the flag so the whole pipeline could run "in seconds instead of
hours". The first run that used it died in 2.5 minutes with:

    ValueError: max() iterable argument is empty     (solve.py:1999)

no artifact, no diagnosis, every solve already paid for. Two defects met, and
neither is visible without the other:

- **A truncated member was recorded as FAILED.** IPOPT returns
  `Maximum_Iterations_Exceeded`, `_solve_nlp` raised `SolveFailure`, and at
  `--max-iter 3` that is EVERY member by construction. So `ok` was empty.
- **`optimize` then chose a champion from the empty list with a bare `max()`.**
  `run` has raised a proper diagnosis for this exact shape since M1, on the
  explicit grounds that a bare `max()` error "tells the user nothing, and this is
  exactly where a broken install surfaces". `optimize` had the identical hole.
  Nobody had fallen into it because until this flag existed, no battery had ever
  had every member fail.

The fix is in two halves, and the first is the interesting one. A deliberately
truncated solve now **harvests its last iterate** through `opti.debug` — the
same accessor the converged path uses, so the two cannot drift into reporting
different fields. IPOPT keeps design variables inside their bounds, so the point
is real; it is simply not optimal. Guarded three ways, because harvesting the
wrong thing here puts a garbage champion into a run that looks complete: only
when the cap was lowered ON PURPOSE (`max_iter < SOLVE_MAX_ITER`), only for the
iteration status (a restoration failure or an infeasible corner has nothing
worth keeping), and only if every harvested number is finite.

The second half is `no_survivors_error`, grouped **by return status** — because
a multistart is many attempts at ONE problem, so the way they all failed is the
diagnosis. Every member `Infeasible_Problem_Detected` is an over-constrained
aircraft; every member `Maximum_WallTime_Exceeded` is a cap to raise; a mixture
is a badly scaled model. Three different fixes, and one flattened message picks
the wrong one twice.

### 27.2 A gate test spent 1 h 39 min proving that a frame stream replays

`test_a_real_run_writes_frames_and_relocates_them` is marked `solve` and was
assumed slow-by-design. It was slow by accident. It ran ~10 members to
convergence, which wrote **1,062 frames** — one per solver iterate — and then
rendered every one of them through Qt at 640x480, while its own docstring says
what is under test is "the plumbing... not the optimizer". It was paying for
convergence it explicitly disclaims, twice.

Now `max_iter=3`: three iterates per member exercise the same callback, the same
ordering, the same relocation and the same renderer as a hundred do. **1 h 39 min
-> ~2 min.**

`test_m3_optimize_smoke` was deliberately NOT given the same treatment, and the
distinction is the point. It asserts a CONVERGED champion — static margin inside
its window, trim inside its throws, a negative shadow price — and every one of
those assertions is meaningless on a truncated solve. Capping it would leave the
assertions passing while testing nothing, which is worse than slow. Its ~10 real
solves are inherent; the measured costs of both now sit in `pyproject.toml`,
because "minutes of runtime and GB of RAM" was the estimate and it was wrong by
an order of magnitude.

### 27.3 The two models disagreed by 53% and the artifact did not mention it

`nlp_vs_reeval_gap` compares the NLP's objective against the numeric
re-evaluation of the SAME design vector. It has been recorded since M2. Nothing
has ever read it.

The 2026-08-06 smoke battery recorded **64.16 min on a 120 min champion — 53%**
— and its artifact said nothing at all. Both numbers describe one design vector,
so a gap that size means one of them is describing a different aeroplane.

What makes this more than an oversight: **the project already had a declared
tolerance and had put it in the wrong place.** `test_m3_optimize_smoke` has
asserted `abs(gap) < 0.1 * objective` since M3. So the property was ENFORCED on
one aircraft in the test suite and UNREPORTED on every run of every other
aircraft. That is §20's split exactly — a thing the project knows, kept
somewhere the artifact cannot reach.

`NLP_REEVAL_GAP_FRAC` is now declared once, read by the run and by the test, and
pinned by a test that fails if either re-spells the literal. The note names the
causes in the order worth checking, and the order is deliberate: iteration
truncation first (cheap to confirm, and the usual answer during a smoke run), a
filter-limited re-evaluation second (`airworthiness_price` — in which case the
two are answering DIFFERENT questions rather than disagreeing), and a genuine
divergence between the in-loop and numeric models last, because it is the one
that matters and the one worth ruling out properly.

### 27.4 The pattern

All three, and §26, are the same defect wearing different clothes: **a quantity
the run computes, stores, and never adjudicates.** The active ingredient in
finding them was not cleverness, it was execution — §26 needed a differently
shaped AIRCRAFT, §27.1 needed a flag nobody had used, §27.3 needed a run
degenerate enough to make a silent number loud. A guard evaluated only on inputs
that pass it has not been tested, and a number reported only where nobody reads
it has not been reported.

## 28. A sweep with no legal point at all, reported as a design (2026-08-06)

The bug hunt's fifth defect, and the purest instance of the pattern §27.4 named.

### 28.1 What the first `vtail_rcv2` battery returned

The RC v2 package's first NLP (43 min, `--max-iter 3`) produced a champion, and
the numeric re-evaluation of it reported **44.71 min at 12.5 m/s**. Its sweep:

| | |
|---|---|
| speeds swept | 18 |
| failed to trim at all | **9** (8.0 through 12.0 m/s) |
| trimmed | 9, at deflections **-26.5 to -43.6 deg** |
| against a throw cap of | **6.53 deg** |
| passing that cap | **0** |

Not one airworthy operating point exists anywhere in the sweep. The reported
point trims at **4.2x its control limit** with a static margin of **0.439**
against a required [0.08, 0.15].

### 28.2 The fallback that changes what "best" means

    candidates = legal if legal else feasible

One line, present since M1, and correct as a policy — a run with nothing legal
should still report SOMETHING rather than raise. What it must not do is report
it in the same voice as a legal answer, and that is exactly what it did.

**`airworthiness_price` (§26) cannot catch this, and is not meant to.** It asks
which rule excluded a BETTER point. Here the rules excluded EVERY point, so
there is no better one to name and it correctly returned `None`. The two are
complementary: §26 is "a filter chose among the legal answers", §28 is "there
were no legal answers". A reader seeing `airworthiness_price: null` would
reasonably conclude the filters cost nothing, which was true and deeply
misleading.

**What the artifact actually said.** Eight notes. The closest were that the
static margin is *mesh-dependent* — a statement about the PRECISION of an
unbuildable margin — and that the NLP and re-evaluation disagree by 61% (§27.3,
itself only added hours earlier). The sole trace of the real failure was
`sm_in_range: false` in a constraints table, beside `trim_deflection_deg:
-27.55` and a cap the artifact **never prints anywhere**. Note 4 honestly listed
the nine speeds that did not trim. Nothing said the reported champion is
illegal.

### 28.3 The fix, and the two properties it has to have

`diagnostics.candidates_source` is now `"legal"` or `"feasible_fallback"`, so
the MEANING of the headline number is recorded rather than implied. When the
fallback fires, `rule_violations` reports each broken rule with **both numbers**
and the note goes in at **position zero** — ahead of every standing caveat,
because a reader who stops after the first line must have read this one.

Both details are load-bearing:

- **Quoting the limit, not just the rule.** "Violates `trim_throw`" sends the
  reader to the aircraft file to find out by how much. "trim deflection 27.55
  deg against a 6.529 deg limit" does not, and the cap appears nowhere else in
  the artifact.
- **`rule_violations` degrades to silence, never to a raise.** A predicate added
  without a matching limit entry is skipped, and an aircraft that declares no
  throw cap reports no violation rather than "a None deg limit". A diagnostic is
  the last thing that should be able to destroy hours of solving — the same
  fail-open posture as the §22.2 gate.

### 28.4 Why the aeroplane is like that, which is a separate question

At 3 iterations this is not a design and the numbers are not a verdict on
`vtail_rcv2` — the run says so at note zero already. But the DIRECTION is
consistent with §26: the RC v2 manifest puts the motor at station 34.7 mm and
the battery at 115 mm, and the spec geometry was nose-heavy enough to need more
than its throw at every speed below 16.5 m/s. A truncated champion is worse
balanced still. Whether a CONVERGED rcv2 battery solves its own balance — it
has `ballast_kg`, ten placement variables and the throw limit as a hard NLP
constraint, so it should — is the open question, and `candidates_source` is now
the first thing to read in its artifact.

## 29. What the exact Hessian costs, and what it buys (2026-08-07)

Stage 5 of the bug hunt, queued 2026-08-06 and never run because a 16 GB Mac
could not run it honestly. Run on the 25 GB Linux box:
`docs/studies/hessian_stage5.json`, driver `tools/bughunt/hessian_experiment.py`.

The question was specific. A 39-variable NLP takes 5.2 s per IPOPT iteration and
peaks above 10 GB, of which the CasADi graph is 0.81 GB (§23.4). A dense 39x39
Hessian is 12 KB, so the gigabytes are not linear algebra on the KKT system —
they are the second derivative of a full LiftingLine solve embedded
symbolically, four times over. `opti.solve()` sets no `hessian_approximation`,
so IPOPT computes that exactly, and nobody had ever asked the price.

### 29.1 The paired result: L-BFGS lost, and lost clearly

One solve per arm, `vtail_sample` / `endurance_sample`, same inits, back to
back, baseline first so a machine degrading across the pair penalises the
challenger rather than flattering it.

| | exact Hessian | limited-memory |
|---|---|---|
| wall clock | **17.38 min** | 31.12 min |
| peak RAM | 12.02 GB | **8.68 GB** |
| status | **Solve_Succeeded** | `Maximum_WallTime_Exceeded` |
| iterations | not recorded (§29.3) | **871** |
| objective | **119.7810 min** | never reached one |

L-BFGS did exactly what the theory promises on the memory side — dropping the
second-derivative graph saved 3.34 GB, 28% — and then could not convert it into
an answer. It spent 871 iterations and hit the 30 min `SOLVE_TIMEOUT_MIN` cap
with its closest miss on the nose-length row, against a baseline that had a
converged optimum in 17.38 min.

**So the exact Hessian is not an oversight to be tuned away. It is buying
convergence, and at this size it is the cheaper of the two.** The instruction
attached to this experiment — "if L-BFGS wins, do not leave it as a patch, make
it a declared default with the measurement behind it" — does not trigger. The
monkeypatch stays a monkeypatch and `solve.py` gains no new knob.

**What this does NOT establish.** 30 min is a cap, not a divergence proof, and
§25.2 records a freed-spar arm that needed 45 min. L-BFGS may converge given
more clock; what is settled is that it is decisively worse at the timeout this
project actually runs with. Reopening it means raising the cap for BOTH arms —
raising it only for the challenger would be the same flattery the pairing order
exists to prevent.

### 29.2 §25.2's spar prediction, closed — and reproduced across platforms

The baseline arm is a real converged solve at stock settings, which is precisely
the freed-spar-bound check §25.2 predicted but could not test on a truncated
solve: an active set is a property of a converged one.

    spar_od_center     15.131 mm   interior
    spar_od_outer       6.530 mm   interior
    spar_wall_center    0.600 mm   ACTIVE
    spar_wall_outer     0.500 mm   ACTIVE

**Predicted: both ODs interior, both walls binding. Observed: exactly that.**
Freeing the ceilings (14 -> 20 mm, 12 -> 20 mm) moved the binding structural
rows off the diameters and onto the wall thicknesses, and `spar_od_center`
settled at 15.13 mm — genuinely above the old 14 mm ceiling, so that bound had
been holding a variable still rather than describing anything physical.

The reproduction is worth as much as the prediction. §25.2's freed arm was
measured on macOS; this one ran on Linux, in a different session, on different
hardware, and returned 119.7810 min, 1.8411 kg, 0.0151 m and 0.0065 m — the same
numbers to every digit §25.2 published. A cross-platform bit-level match on a
39-variable NLP says the solve is deterministic and platform-independent, which
nothing in this project had previously demonstrated.

Both walls landed on their LOWER bounds (0.0006 and 0.0005 m). The optimizer
wants the thinnest wall it is permitted, which sharpens the open purchasability
question rather than answering it: the binding quantity is now a wall thickness
pinned at the manufacturing floor, so rounding to a catalogue OD x ID pair moves
the exact constraint that sized the structure.

### 29.3 The experiment recorded iterations only when it failed

`arm()` set `iters = None` on the success path and read `e.iter_count` only from
the exception, so the converged arm reported `"iter_count": null` while the arm
that timed out reported 871. The one number the trade is ABOUT — L-BFGS "pays in
iteration count" — was captured only when there was no answer to pay for.

It is not recoverable after the fact: `_solve_nlp` returns `_pack(sol)`, which
carries no solver statistics, and `solve.py:1614` passes `verbose=False`, so
IPOPT's iteration table is not in the log either. Fixed in the driver rather
than in `solve.py` — the patched `Opti.solve` now records
`opti.debug.stats()["iter_count"]` for every solve in the arm, and reports
`opti_solve_calls` beside it rather than assuming there was one.

The baseline's iteration count is therefore still unknown, and stays unknown
unless the pair is re-run. It is not needed for the verdict, which rests on wall
clock and convergence.

### 29.4 The transferable part

Same shape as §26-28: **a quantity the run computes, stores, and never
adjudicates.** IPOPT has computed an exact Hessian on every solve this project
has ever run, at a cost nobody had measured, because the default was never a
decision — it was an absence of one. `grep -ri "hessian\|BFGS\|limited-memory"`
over `docs/` and `src/` returned nothing before this entry.

The answer happens to endorse the default. That is the outcome to be most
careful with: an unexamined default that turns out to be right is
indistinguishable, from the inside, from one that was never examined.

## 30. Share the aerodynamic graph, not the Hessian approximation (2026-08-07)

Section 29 established that L-BFGS is the wrong memory trade here: it saved 28%
but failed to converge in 30 minutes. The four inline LiftingLine calls still
duplicated the same geometry, NeuralFoil, and derivative implementation at the
cruise point and the three static-margin samples. CasADi can encapsulate that
model as one `Function`; the four calls then remain exact symbolic evaluations,
while IPOPT builds the function's derivative graphs once.

Paired on Windows, same model and exact-Hessian settings, with three IPOPT
iterations so setup cost is measured identically (`docs/studies/casadi_graph_sharing.json`):

| | four inline graphs | one shared function |
|---|---:|---:|
| wall clock | 680.74 s | **61.17 s** |
| peak working set | 4.85 GB | **3.162 GB** |
| status / iterations | truncated / 3 | truncated / 3 |

That is 11.13x faster for the graph-heavy short solve and 34.8% less peak RAM.
Unlike section 29's experiment, it changes neither the Hessian approximation
nor any equation. The full exact-Hessian solve then converged in 690.97 s at
3.162 GB. Its result matches section 29's independently recorded inline Linux
solve to at least nine significant digits: objective 119.7809664732 min, mass
1.841103929 kg, drag 0.8342164482 N, speed 9.499999890 m/s, and static margin
0.0799999900.

The hard-coded 14.5 GB fallback stays conservative until the same measurement
has been repeated on Linux and macOS; recorded run peaks will continue to drive
the budget automatically. The implementation decision is nevertheless closed:
keep IPOPT's exact Hessian for convergence, and stop asking CasADi to construct
four copies of the function it differentiates.

### 30.1 CSE and non-inlining: more memory headroom, mixed wall-clock result

The shared function is now marked `never_inline`, so a future CasADi heuristic
cannot silently turn the four call sites back into four graphs. Common-
subexpression elimination inside that function is exact as well. On the paired
three-iteration setup benchmark it improved 61.17 s / 3.162 GB to **55.85 s /
2.522 GB**. Against the original inline graph that is 12.19x faster and 48.0%
less peak memory.

The full converged result is more nuanced and is recorded rather than rounded
into a win: **735.96 s / 2.569 GB**, 106 iterations, versus 690.97 s / 3.162 GB
without CSE. Thus CSE bought another 18.8% of memory headroom while this single
full run took 6.5% longer, despite the setup-heavy run being faster. Both landed
on the same result to numerical precision. Keep it for the deterministic graph
and OOM-resilience improvement; do not cite it as a demonstrated full-run speed
improvement until a repeated paired benchmark separates runtime variance from
a real evaluation penalty.

Two robustness changes cost no model evaluations: the measured exact-Hessian
choice is now an explicit IPOPT option instead of an inherited default, and
successful members record `return_status`, `iter_count`, and `converged` just as
failed and deliberately truncated members already did. Future solver regressions
can therefore be seen in ordinary run artifacts rather than reconstructed by a
special monkeypatch.

### 30.2 Map the operating points as one serial batch

Sharing the function removed four copies of its implementation, but the outer
NLP still contained four scalar call nodes. CasADi's serial `Function.map(4)`
expresses the cruise point and three static-margin samples as one batched call.
It does not create threads and therefore does not trade lower latency for more
RAM or CPU contention.

A synthetic 20-variable function, used only to isolate outer-graph overhead,
dropped from 19 to 8 graph nodes; its Jacobian dropped from 198 to 179 nodes.
This is a construction-level result, not a claim of the same percentage in a
full solve. The full NLP remains dominated by the lifting-line implementation
and IPOPT factorization, so the next real run should record the end-to-end delta
through the existing `iter_count`, wall-time, and peak-memory instrumentation.

## 31. A cumulative frame count is not an iteration count (2026-08-07)

The live window reached frame 338 and looked like one optimizer had still not
converged. The checkpoints showed the opposite: nominal converged in 22
iterations, `perturbed_0` converged in 36 to an objective only 5.46e-12 away,
and `perturbed_1` then consumed the full 30-minute cap before stopping at 266
iterations. Frame 338 was already `mass_bump` iteration 9. The viewer now labels
the cumulative total separately from phase, member, member-local iteration and
member-local elapsed time.

The two successful starts also matched in every design variable: the worst was
`t_taper`, differing by 1.20e-7 of its declared range. On serial runs, two
successful starts inside 1e-8 relative objective and 1e-5 of every declared DV
range are now strict consensus; requested later cold starts are recorded and
skipped. The rule fails closed on any failure, NaN, missing/different box, or
larger discrepancy. Parallel runs retain the one-batch schedule because the
remaining starts cost wall time only when they are serial.

## 32. Re-solves now reuse the complete optimizer state (2026-08-07)

The shared CasADi graph made each iteration cheaper, but the full run was still
paying for nearby sensitivity problems as if each were unrelated. The active
run reached more than 2,000 cumulative frames because the counter covered over
twenty full NLP members, not because one solve had reached 2,000 iterations.
Failed or timed-out optional members alone consumed about **135 minutes**.

Successful solves now retain IPOPT's complete primal vector and constraint-dual
vector in the private checkpoint record. A compatible nearby re-solve restores
both and enables IPOPT's warm-start settings. Shape checks are exact and fail
closed: a topology change or added fixed-span equality that changes either NLP
dimension rejects the dual seed and falls back to the physical design/state
guess. The first fixed-span member therefore uses the champion's primal values;
subsequent fixed-span members have matching shapes and reuse the complete point.
Independent multistarts deliberately remain cold so they still test attraction
from different initial conditions.

The serial schedule also changed so the +20 g screen bump runs after the best
successful primary start and reuses that solution, even when only one or two
multistarts were requested. Discrete studies, winglet alternatives, the final
re-solve battery and flatness sweep all receive champion-derived state guesses;
compatible members additionally receive the complete primal/dual seed.

Runtime ceilings now reflect the phase rather than inheriting the primary
solve's 30-minute allowance:

| member type | ceiling | behavior at timeout |
|---|---:|---|
| optional alternative / sensitivity | 12 min | record the failed member |
| flatness point | 10 min | record it as timed out; leave smaller points unproven |

This does not call an unattempted span infeasible. It stops repeating an equal
budget below the first timed-out span and makes that missing evidence explicit
in the report. The 10-minute flatness cap is a TRIAL (user decision,
2026-08-10) superseding the standing 2026-07-31 decision to hold 20: that
decision predated both graph sharing (converged members now take 1.7-3.2
minutes against a pre-sharing record of 6.0) and this cascade, which turned a
wrong timeout from a silently lost span into visible, bounded evidence. The
exit condition is written at `FLATNESS_TIMEOUT_MIN`: a timed-out member whose
convergence trace says "still converging when the clock stopped" sends the cap
back toward 20; "stuck, not slow" confirms it, which is what RCV2_CAP_PRICING
§4 measured at 15 vs 60 minutes. One interaction closed on merge: a timeout
whose member spanned a machine-sleep window (`suspended_minutes`, §4 of that
study) does not trigger the skip-below cascade, because that member never
received its budget. This policy reduces worst-case time without adding model
evaluations or weakening the equations.

## 33. "Legal" now includes final numeric stability (2026-08-07)

The completed `20260807T174248` run exposed a false-positive trust path. Its NLP
converged at 9.742 m/s with static margin 0.080, but the numeric speed sweep
selected 9.5 m/s as the best "legal" point and only then evaluated stability.
That point returned SM 0.057 against the mission's 0.08 floor, with a negative
local stability slope. The fine LiftingLine mesh and independent VLM returned
approximately 0.053. Nevertheless the artifact recorded
`candidates_source=legal`, no reported-point violations, and
`design_trustworthy=true`, because that last field meant only that drag was mesh
converged.

Static margin is now part of the same named airworthiness-rule set as gust
margin, propeller advance ratio and control throw. Each candidate must satisfy
the full margin window and keep the local stability slope nonnegative before it
can become the reported legal operating point. Evaluations are cached and tried
in objective order; the sweep stops at the first fully legal candidate instead
of evaluating five additional LiftingLine points at every speed. Thus a normal
run pays only for candidates that could actually win, while a run with no stable
point necessarily checks every plausible candidate before saying so.

The final trust verdict is now broader than the early objective-mesh gate. It
fails closed when the numeric re-evaluation fails, no legal operating point
exists, stall fails, the reported static margin lies outside its window, the
local margin changes sign, or the objective is mesh-dependent. The earlier
selection-time result remains separately recorded as
`objective_mesh_trustworthy`. A failed final verdict is the first note in
`run.json` and a red banner immediately below the report status; the artifact
remains useful diagnostically but no longer presents itself as a flight or
construction recommendation.

## 34. The rcv2 measurement of §30-32, and the seed that was a ratio (2026-08-10)

Sections 30-32 were measured on `vtail_sample`. This is the first paired
measurement on `vtail_rcv2` — the aeroplane this project is actually flying —
run from the GUI against the same mission and checkpoint set the two 2026-08
main-code batteries used, so every row below has a cold-start control that is
bit-identical across those two runs.

### 34.1 Graph sharing buys memory, not time

| member | branch | main (x2) | wall | peak |
|---|---|---|---:|---:|
| `nominal` | 105.8184 / 5.61 min / 5.58 GB | 105.8184 / 5.69-5.83 / 11.66-12.02 | -1 to -4% | **-52%** |
| `perturbed_0` | 105.8184 / 8.75 min / 9.87 GB | 105.8184 / 8.22-8.23 / 11.67-12.04 | **+6.4%** | -16% |

The objective is identical to four decimals on both, and
`tools/bughunt/verify_shared_ll.py` returns EQUIVALENT on rcv2 at a worst error
of 1.998e-15 against a 1e-12 tolerance, with the deflection leak absent. So the
physics is untouched — that part of §30 holds on this aeroplane too.

The speed claim does not. §30.1 already declined to call CSE a full-run
improvement after one run came in 6.5% slower; here the harder of the two
members is 6.4% slower, which is the same number again from an independent
model. **The saving is memory, and it is not uniform**: 52% on one member and
16% on the other. Treat the 12.19x as what it was measured as — a
three-iteration setup benchmark — and not as a member-time expectation.

This matters to §32's cap arithmetic. The 10-minute flatness ceiling is
defended partly on converged members having dropped to 1.7-3.2 minutes after
graph sharing. That figure is `vtail_sample`. On rcv2 the four converged
flatness members of both main batteries took **4.22-6.43 minutes**, and nothing
measured here suggests graph sharing shortens them. The margin under a 10-minute
cap is therefore about 1.56x, not the 3x the surrounding comment implies. The
trial is not thereby wrong — its exit condition is about a timed-out member's
convergence trace, and all four timed-out rcv2 flatness members (1.76 m and
1.70 m, both runs) read "dual blow-up... Stuck, not slow", which is the trace
that CONFIRMS the cap. But the cap has less headroom on this aeroplane than the
comment claims, and no run has yet measured a converged rcv2 flatness member
under the shared graph.

### 34.2 Multistart consensus, priced on real members

The §31 predicate fires on the recorded rcv2 champions with room to spare:
objective relative error 6.61e-12 against a 1e-8 tolerance, worst design
variable `t_taper` at 1.45e-7 of its declared range against 1e-5. It is not a
threshold so strict that it never triggers. What it skips is `perturbed_1`,
which **failed in both main batteries** after consuming 33.2 minutes each time.
Confirmed live in this run.

### 34.3 A hot start replayed a ratio and killed every member it touched

`mass_bump` and all four `prop_choice` alternatives died with
`Invalid_Number_Detected` at iteration 0. Cold members in the same run
converged normally; the correlation with `solver_seed` was perfect across five
members, and every one of them converges on main.

AeroSandbox builds each variable as `var = scale * raw`, taking `scale` from
that member's `init_guess`, and scales constraint rows the same way
(`var/scale >= lower_bound/scale`). IPOPT's `x` and `lam_g` are therefore
ratios against a per-member basis. A hot start is precisely when that basis
moves, since `init_guess` becomes the champion's value — so the champion's
converged ratios `[1.111, 1.25, 0.745, 1.929, ...]` were written into a problem
whose correct starting point was `[1.0, 1.0, ...]`, applying the design twice.
Instrumented at the failure: `x` finite, **sixteen rows of `g` NaN**, reported
V 8.24 against the champion's 9.52.

The `nx`/`ng` guard cannot detect it — both members have identical dimensions.
The round-trip test could not either: it built both problems with
`init_guess=2.0`, the one basis a hot start never has.

`_hot_start_kwargs` now carries only `inits`, which was always the sound half —
physical values keyed by name, scaled correctly on the way in by
`Opti.variable(init_guess=...)`. Dropping the seed and keeping `inits`
reproduced main's `mass_bump` objective exactly: 104.3996, `Solve_Succeeded`,
52 iterations.

One caveat on §32's remaining premise. That corrected member took **11.93
minutes against main's cold 7.41-7.78**, i.e. the primal warm start made it
slower, on one member. That is the direction `WARM_START_OPTIONS` in `solve.py`
already documents ("do not reach for `--warm-start` expecting speed"). Whether
champion-derived `inits` pay for themselves anywhere in the battery is now an
open question rather than an assumption, and it wants the same paired treatment
the rows above got.

### 34.4 The hot start was not slow, it was missing its options (2026-08-10)

§34.3 left the open question above, and the answer is that dropping the seed
dropped something else with it. `_solve_nlp` gates `WARM_START_OPTIONS` on
`warm_start or hot_start_used`, and `hot_start_used` is set by
`_apply_solver_seed` — so the seed was also the only thing switching those
options on for a battery member. Removing it in cf9d5b6 silently left every hot
start in the seed-only configuration `WARM_START_OPTIONS` was written to
prevent: IPOPT's default `bound_push` of 0.01 shoves the starting point 1% off
each bound before iteration 0, and the whole value of a champion seed is that it
already sits ON those bounds.

Measured with `tools/bughunt/warm_start_experiment.py` — four arms, one solve
each, one process per arm, back to back on an M5/16 GB laptop, on the same
`mass_bump` member (+20 g) that §34.3 reports. The cold control ran BEFORE both
challengers, so machine drift over the sequence counts against the fix.

| arm | wall | iterations | peak | vs cold |
|---|---:|---:|---:|---:|
| `champion` (cold, seed source) | 1.61 min | 22 | 4.08 GB | — |
| `bump_cold` (control) | 2.11 min | 31 | 4.07 GB | — |
| `bump_inits_only` (cf9d5b6) | 3.34 min | 52 | 4.08 GB | **+58.3%** |
| `bump_inits_and_options` (fix) | 1.09 min | 13 | 4.08 GB | **-48.3%** |

The iteration column is the finding. A primal seed WITHOUT the options costs
more iterations than starting cold — 52 against 31 — so on this aeroplane it is
not the "wash" §32 assumed but an active penalty; the solver is pushed off the
champion and walks back from worse than a fresh start. The same seed WITH the
options converges in 13. The champion here sits on thirteen declared bounds,
against the eight `vtail_sample` was characterised on.

**This reproduces §34.3's caveat and reinterprets it.** That entry recorded the
corrected member at 11.93 min against main's cold 7.41-7.78, i.e. +53% to +61%,
and read it as evidence that champion-derived `inits` may not pay. The +58.3%
here, on a different machine at a quarter of the absolute wall-clock, lands
inside that band — it was the missing options, not the seed being worthless.

All three +20 g arms return the same design: objective spread 1.136e-07 on
104.4 (~1e-9 relative), identical active-bound sets, `V_ms` agreeing to eight
figures. So the comparison is about time only, as the 2026-07-31 measurement
was. Nothing paged: swap flat at 3.00 GB across all four arms, every peak
4.07-4.08 GB against 5.4-8.1 GB available.

Two things this does NOT establish. One solve per arm is direction and rough
magnitude, not a precision figure. And it is one member — `mass_bump` is a 20 g
perturbation of the champion, the most favourable hot start in the battery; the
`prop_choice` alternatives and the winglet study seed across bigger design
changes and are not measured here.

`vtail_sample` is unchanged and still a wash (5.35 / 6.78 / 5.58 min). The
conclusion is now per-aeroplane, and the part that is not: a primal seed must
always be paired with `WARM_START_OPTIONS`, which is why `_hot_start_kwargs`
now returns `warm_start=True` alongside `inits` rather than relying on a seed
to imply it.

The seed machinery itself is gone as of this section. `_apply_solver_seed` and
`_capture_solver_seed` were kept unwired by cf9d5b6 to carry the measurement,
but neither records the scale factors a correct implementation would need, so
they were a trap rather than a foundation — and `_capture_solver_seed` was still
writing a full `x`/`lam_g` pair into every result, across the worker pipe and
into every checkpoint at `indent=1`, read by nobody. `_solve_nlp` no longer takes
`solver_seed` and gates `WARM_START_OPTIONS` on `warm_start` alone. What the
functions knew is preserved where it is load-bearing: the scaling explanation in
`_hot_start_kwargs`, and a test in `test_solver_graph.py` that pins AeroSandbox's
`var = scale * raw` behaviour directly rather than through helpers that can be
deleted. Results now record `warm_started` in place of `hot_start_used`, which
is the flag that turned out to matter.

## 35. The full rcv2 battery on this branch: the warm start costs more than it buys (2026-08-10)

§34.4 ended by naming what it had not established: "it is one member —
`mass_bump` is a 20 g perturbation of the champion, the most favourable hot
start in the battery; the `prop_choice` alternatives and the winglet study seed
across bigger design changes and are not measured here." This is that
measurement. A complete `vtail_rcv2` battery, launched through the GUI New Run
dialog, against the two completed main-code batteries on the same aircraft,
mission and checkpoint set. Every member below therefore has a cold control
that is bit-identical across two independent main runs. Distilled results:
`docs/studies/rcv2_branch_vs_main_20260810.json`.

The answer is that the options generalise badly. On the nearest seed they halve
a solve; three members further out they destroy it.

### 35.1 What the battery did and did not produce

**181.5 minutes against main's 333.3, and that ratio is not a speed figure** —
the branch is fast partly because six members hit a wall-clock cap instead of
converging. The honest ledger is by outcome, not by clock:

| | members |
|---|---|
| main failed, branch **solved** | `polyhedral2`, `winglet continuous_cant`, `re-solve mass_bump` |
| main solved, branch **failed** | `flatness 2.0`, `winglet off`, `priced_equipment_fit`, `printed_mass_x1.10`, `printed_mass_x0.90`, `chain_eta_x0.90` |
| skipped by design | `perturbed_1` (multistart consensus, §34.2) |
| never attempted | five flatness spans, 1.94 m down to 1.70 m |

The gains are real and three of them are new knowledge. Every one of main's four
33-minute burns is now resolved: `perturbed_1` skipped as provably redundant,
and the other three SOLVED — `polyhedral2` in 9.95 min at 40 iterations against
main's 33.35 and 212, `continuous_cant` in 8.96 against 32.43, `re-solve
mass_bump` in 7.24 against 32.41. **The continuous-cant question has never had
an answer before this run**; both main batteries decided it by timeout.
`continuous_cant` converges to 122.12279342 against main's `winglet off`
122.12279353, with `d_exp` at 3.8e-10 — freeing tip cant to 88° reproduces the
winglet-off optimum exactly and buys nothing.

The losses cost more. **The flatness sweep produced nothing**: main returned
four converged points (122.12 / 119.55 / 116.18 / 105.86) and this run returned
zero. `winglet off` is the baseline of the paired winglet comparison, so the
winglet cannot be priced. Both `chain_eta` arms are compromised — one failed,
the other landed 0.045 low (§35.4).

### 35.2 The iteration ladder: the seed helps, then it stops, then it kills

Every warm-started member in one table, ordered by iterations. The pattern is
monotone and it is the finding:

| member | iters | branch | main | outcome |
|---|---:|---:|---:|---|
| `mass_bump` (+20 g) | 13 | 3.81 | 7.41-7.78 | **-50%** |
| prop `ancf_12x10` | 14 | 4.52 | 9.00-9.23 | **-50%** |
| prop `ancf_13x11` | 25 | 6.81 | 6.68-6.93 | +2% |
| prop `ancf_14x9` | 27 | 6.67 | 8.63-8.82 | -23% |
| tail `conventional` | 28 | 8.89 | 7.05-7.27 | +26% |
| fuselage `integrated` | 31 | 7.65 | 5.73-5.81 | +32% |
| prop `ancf_12x9` | 32 | 7.71 | 8.23-8.34 | -6% |
| `flatness 2.0` | 46 | 10.79 | 6.39-6.43 | **FAILED** |
| `printed_mass_x1.10` | 54 | 13.62 | 6.91-6.99 | **FAILED** |
| `printed_mass_x0.90` | 57 | 12.95 | 4.51-4.60 | **FAILED** |
| `chain_eta_x0.90` | 57 | 12.78 | 12.32-12.33 | **FAILED** |
| `winglet off` | 74 | 13.45 | 12.37-12.38 | **FAILED** |

`WARM_START_OPTIONS` pins the starting point to the bounds (`bound_push` and
its three companions at 1e-6) and starts with almost no barrier (`mu_init`
1e-4). Those settings are correct for a point that is near-optimal **including
its duals**. `_hot_start_kwargs` supplies primal values only, and correctly so:
§34.3 removed the duals because they are ratios against a basis a hot start
moves. So every warm-started member now begins pinned against thirteen active
bounds, with no barrier to regularise multipliers it was never given.

When the seed is nearly exact that is a gift. Further out the solver has to
walk away from the corner it was pinned to, with no barrier to help, and the
failure modes are the ones the run recorded verbatim:

- `printed_mass_x1.10` — *"dual blow-up: the multipliers diverged while the
  primal side sat still. Stuck, not slow — more clock buys nothing."*
- `printed_mass_x0.90` — *"no dual blow-up, but the primal side stopped moving
  — a plateau short of feasible, which is what a starved corner looks like."*
  `inf_pr_final` 0.0796, and `inf_pr_progress_last_25` **negative**.

**Seed distance does not explain it.** `printed_mass_x0.90` is a -10% mass
perturbation, no further from the champion than `mass_bump`'s +20 g, and it was
main's FASTEST member at 4.51 min. What separates them is that the re-solve
battery perturbs model parameters rather than design variables, so the champion
is infeasible under the perturbed physics — and an infeasible corner is exactly
where these options leave no room to move. That is a hypothesis; the
measurement is the table.

The remedy that follows from the evidence is to stop `_hot_start_kwargs`
sending `warm_start=True`. The 2026-08-10 02:08 run is the control: `inits`
alone converged `mass_bump` in 11.93 min — slower than main, but CONVERGED.
Five of this run's six failures are the options, not the caps. Whether
`mu_init` at IPOPT's default 0.1 keeps the wins while removing the failures is
the obvious next experiment and is not yet measured.

### 35.3 Both wall-clock caps are set below members that converge

Two caps failed members that main solved, for two different reasons, and only
one of them is a cap problem.

**`FLATNESS_TIMEOUT_MIN = 10.0` — the trial ends. Raise it toward 20.** The
exit condition written at the constant is a timed-out member whose trace reads
"still converging when the clock stopped". The 2.0 m member returned exactly
that string, at `inf_pr_final` 1.8e-04 with a worst violation of 1.6e-05 on
`L == weight_n` and `inf_pr_progress_last_25` still positive. This is the EASY
span — main converged it in 6.39 and 6.43 minutes. §34.1's evidence that the
cap was safe came from the 1.76 m and 1.70 m members reading "dual blow-up...
Stuck, not slow"; those are the hard ones and that reading still confirms the
cap for them. Ten minutes does not fit the span the champion sits on.

**`OPTIONAL_MEMBER_TIMEOUT_MIN = 12.0` is below four members main converged.**
`winglet off` 12.37-12.38, `priced_equipment_fit__airframe_only` 12.97,
`chain_eta_x0.90` 12.32-12.33, `chain_eta_x1.10` 12.28-12.40. (The 08-07
battery priced a different candidate, `core`, at 12.62 — also over.) The
constant's docstring justifies
12 on the grounds that "every optional member that did converge in that run
landed inside 9.1 minutes", citing the 2026-08-07 full run — which is one of
the two batteries above, and has four converged optional members between 12.28
and 12.62. The 9.1 figure is `vtail_sample`'s. **This is the same category
error §34.1 caught in the flatness cap's own justification**, made twice in the
same constant block, and this time it costs converged members. Sixteen clears
all four with margin.

### 35.4 A warm start moves WHERE a member lands, not only how long it takes

Two members converged to different optima than main, in both directions:

| member | branch | main | delta |
|---|---:|---:|---:|
| `study_tail_type__ttail` | 111.8640 | 110.6555 | **+1.21** |
| `re-solve_battery__chain_eta_x1.10` | 132.5800 | 132.6251 | **-0.045** |

Both `Solve_Succeeded`; both main batteries agree with each other to 14 digits.
The T-tail is a different aeroplane, not a numerical wobble — `fin_height`
-34%, `fin_c_root` +84%, `fin_taper` -60%, `fin_sweep` -23%, `tail_arm` +17%.

`WARM_START_OPTIONS` states that the seed "is not changing WHERE it lands, only
how long it takes to get there". That held for every member §32 and §34.1
measured and it is false here. Two consequences. Study candidates seeded from
the champion are no longer landing in the same basins their cold controls
found, so a rejection margin computed this way is not the margin a cold run
would have computed. And a sensitivity band is the worst place for it: a failed
member is visibly absent from a report, whereas `chain_eta_x1.10` at 0.03% low
is printed as a number.

The T-tail conclusion is unchanged either way — V-tail 122.08 over conventional
115.28 over T-tail 111.86 — so no adoption decision in this run turns on it.

### 35.5 The run-level gate fired, on a champion that only exists because of the above

`design_trustworthy` is **False** for this run and True for both main runs:
"fewer than 2 of 3 meshes agree on static_margin: +0.07374 at (8, 8), +0.08701
at (12, 10), +0.05155 at (16, 10)". `aero.py` is byte-identical to main, so
this is a property of this champion rather than a code regression — and this
champion reached the artifact through `continuous_cant` because `winglet off`
failed. The §33 gate is working: it declined to certify a design whose
stability estimate depends on the mesh. Worth recording that the branch
champion is nonetheless CLOSER to the mission's 0.08 floor than main's, gap
-0.0135 against -0.0228.

Everything downstream of the solver worked. Artifacts, report, `interactive_3d`,
geometry, manufacturing, timelapse and MP4 all wrote without incident;
`suspended_minutes` stayed at nanosecond jitter for 192 minutes with the lid
open; peak RSS reached 16.4 GB against a 22 GB budget. The timelapse is 793
source frames against main's 2385, which is the run's own summary in one number
— frames are written per iteration.

### 35.6 What was changed, and what that trade costs

All four fixes are applied as of this section (`_hot_start_kwargs` no longer
sends `warm_start`, `FLATNESS_TIMEOUT_MIN` 20, `OPTIONAL_MEMBER_TIMEOUT_MIN`
16, and a "still converging" flatness timeout no longer cascades — keyed off a
new stable `verdict` rather than the prose `reading`, so a copy-edit cannot
change which members cascade). **None of them is re-measured.** The next battery
prices them, and it starts from a fresh fingerprint because `solve.py` moved.

The trade item 1 makes is not free and is worth stating plainly: all three
members this run solved that main could not — `polyhedral2`, `continuous_cant`,
re-solve `mass_bump` — were WARM-STARTED when they succeeded. Removing the
automatic seed may cost those gains. The expectation is therefore that the next
run is slower than 181 minutes and more complete, and the number to beat is
main's 333.

### 35.7 What this does NOT establish

One battery, not a paired repeat, so a member that failed here might converge
on a second run; main's figures are doubled and this branch's are not. The
mechanism in §35.2 is inferred from three convergence traces and the option
values, not from an instrumented solve — nobody has watched the multipliers
diverge with `mu_init` varied. And the branch's three genuine gains
(`polyhedral2`, `continuous_cant`, `re-solve mass_bump`) are all members main
never solved, so they have no cold control at all: they are new answers, but
they are unverified new answers, and `continuous_cant` agreeing with main's
`winglet off` to nine digits is the only one with independent corroboration.
