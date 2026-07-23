# Design Findings — sample aircraft (endurance mission)

What the optimizer has actually said about the DESIGN_SPEC.md plane so far.
All numbers from uncalibrated models (construction profile from ballparks,
propulsion from datasheets/proxy tables): **trust the rankings and the active
constraint set, not the absolute minutes** (see VALIDATION_ANCHORS.md).
Generated 2026-07-23, M3/M4 runs. Updated same day after the SM fix
(Munk fuselage term + regression derivative) and the span-cap raise to 3.0 m.

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
