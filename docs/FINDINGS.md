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
  fat pod, and LL's Cm noise is averaged, not eliminated — flow5 should still
  own the final stability verdict. Remaining NLP-vs-re-eval gap ~4% is
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
  this is the first champion where it crosses the line — flow5 should own
  the final stability check before anything is built.
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
  SM estimator, not a one-off. flow5 should own the stability verdict.
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
