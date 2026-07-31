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
