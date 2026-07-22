# Design Findings — sample aircraft (endurance mission)

What the optimizer has actually said about the DESIGN_SPEC.md plane so far.
All numbers from uncalibrated models (construction profile from ballparks,
propulsion from datasheets/proxy tables): **trust the rankings and the active
constraint set, not the absolute minutes** (see VALIDATION_ANCHORS.md).
Generated 2026-07-23, M3/M4 runs.

## 1. The active constraint set (what actually shapes this airplane)

| Constraint | Status at the optimum | Meaning |
|---|---|---|
| Static margin ≥ 8% | **active** | The tail is sized by stability, not by anything aerodynamic — the optimizer shrinks the tail to its floor (scale 0.70, arm 590 mm vs. the spec's 700 mm). Every extra cm² of tail is pure loss at this CG. |
| Span ≤ 2.2 m | **active** | Even with spar mass now load-scaled, span still pays. The bound is the mission/config choice, not physics. |
| Gust margin CL ≤ 0.7·CLmax | **active** | Sets cruise speed (~10.9 m/s), not the wind floor (9.5). The plane cruises faster than power-optimal because slow flight leaves no CL headroom. |
| Ballast ≥ 0 | **active at 0** | With the battery at its forward stop (95 mm), no nose lead is needed. The spec's 70 g ballast is avoidable by layout. |
| Spar OD bounds | **active** | Optimizer wants max-diameter, thin-wall tubes (center 14×0.8). Notably: the spec's 10×8 center spar **fails** the 5 g / SF 2.0 root-stress check (~300 MPa vs. 200 allowable). Either accept a lower limit load/SF or upsize the spar. |
| Stall ≤ 8 m/s | active in most variants | The wing-area sizer. The 8.0 limit is a mission input; the spec itself estimated 8.3 — worth an explicit decision. |

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
- **The static-margin model is the weakest link in the loop right now**, twice
  over: (a) no fuselage/boom destabilizing moment (LiftingLine is
  lifting-surfaces-only), biasing the neutral point aft; (b) LiftingLine's
  dCm/dCL is strongly alpha-dependent for this configuration — at the M3
  champion, the local SM reads ~0.080 at cruise alpha ~4 deg but collapses
  toward ~0.01 by alpha ~6 deg (regression over the window: ~0.04). Because the
  SM-window constraint evaluated at cruise alpha is what pushes cruise speed to
  10.9 m/s and shrinks the tail to its floor, **the tail sizing and cruise-speed
  results inherit this fragility** — treat them as provisional until the SM
  model gets a fuselage-moment correction and a more robust NP estimate
  (options: slender-body/Munk fuselage term + Cm-alpha regression in the NLP,
  a VLM/AVL derivative cross-check, or deferring SM to flow5 validation).
  This is also the source of the reported NLP-vs-re-evaluation objective gap
  (~8 min): the numeric re-evaluation finds slower operating points the NLP's
  alpha-local SM constraint rejects.
- Tripped Δ(objective) ≈ −9 to −11 min across candidates: the design survives
  losing its laminar runs, but calibrating print-surface reality matters.
- Chain efficiency ~0.39–0.45 at cruise: the 900 kV motor is far from its happy
  point at 25 W. If hardware were ever revisited, a lower-Kv motor or bigger
  pack-voltage-to-load match is the single biggest endurance lever the fixed
  equipment list is hiding.

## 5. Next calibration actions (highest value first)

1. Slice 2–3 wing sections at different chords → `tools/fit_profile.py` →
   calibrated construction profile (turns mass model from ballpark to data).
2. Decide the stall-speed limit (8.0 vs 8.3+ m/s) and the span cap as mission
   inputs — both are active constraints, so they move the answer directly.
3. XFOIL spot-check of AG35 vs SD7037 at Re 150–200k (one-off, per §3.1) before
   committing the airfoil switch.
