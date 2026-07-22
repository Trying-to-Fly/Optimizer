# Validation Anchors

Published data from real aircraft, used as the Phase 1 gate's plausibility bands
(MODEL_DETAILS.md §6.5). The sample spec's own performance figures are rough
estimates and are *not* anchors. Data collected 2026-07; quality graded
(measured log > documented build > manufacturer spec > forum/review claim).

## Hard anchors

| # | Aircraft | Data | Quality | Source |
|---|---|---|---|---|
| 1 | X-UAV Mini Talon (1.3 m, 1.65 kg) | **56 W (3.8 A) measured level cruise at ~13.4 m/s** → ~34 W/kg; endurance 68–92 min on 77–118 Wh | Measured log (ItsQv) | itsqv.com Mini Talon build compilation |
| 2 | Mini Talon (ArduPilot docs, 1.45–1.9 kg) | **< 80 mAh/km ≈ < 1.2 Wh/km**; 60–120 min typical | Documented build | ardupilot.org miniTalon build |
| 3 | Grafas MAXI solar (3.52 m, 2.58 kg, 80 dm²) | **25–45 W total level flight incl. ~7 W avionics** (10–17 W/kg); 11 h / 520 km | Telemetry log | discuss.ardupilot.org solar-rc-plane-300km-7h |
| 4 | Kraga Kodo / Kodo II (1.6/1.65 m) | Printed parts **418 g / 364 g** on 0.25 m² wings; RTF 850/875 g | Mfr spec | 3dprintedrcplanes.com |
| 5 | Eclipson Apex (2.3 m, 36 dm²) | Printed 750–1000 g; TOW 1.30–1.55 kg; **stall 6.4–6.9 m/s at 36–43 g/dm²** | Mfr spec | eclipson-airplanes.com/apex |
| 6 | Eclipson Model Y (1.0 m) | Structure **400 g PLA vs 240 g LW-PLA** (−40%); stall 8.3→6.9 m/s | Mfr spec | air-rc.com Model Y |
| 7 | SD7037 UIUC wind-tunnel polars, Re 40k–500k | Drag-polar validation source for the Re 150–200k band | Wind tunnel | m-selig.ae.illinois.edu UIUC LSAT |

Secondary (bracket only, don't calibrate): Believer 1960 ~122–133 W at ~5 kg / 20 m/s
(forum log); Phoenix 2400 ~67 W avg over 10 h 45 min (derived, AUW unknown);
Skywalker 1900 ~191 mAh/km (voltage unconfirmed); Planeprint RISE 2.0–2.35 m from
650 g / 19 g/dm² (mfr).

## Bands for a 1.8 m / ~1.9 kg efficiency design

| Quantity | Band | Basis |
|---|---|---|
| Level cruise power (10–15 m/s) | ~25–90 W; efficient builds 40–70 W; sailplane-class floor ~18–25 W | anchors 1, 3, secondary |
| Specific power | ~10–45 W/kg | anchors 1, 3 |
| Energy per distance | ~0.8–1.5 Wh/km (efficient); < 2.8 worst logged | anchors 2, secondary |
| Printed structure / RTF mass | ~43–52 % (PLA-class); LW-PLA ≈ −40 % structure | anchors 4, 5, 6 |
| Implied CL_max | ~1.1–1.3 (clean) | anchor 5 + Believer stall |

## M1 assessment (first model run vs. anchors, 2026-07-23)

Model (uncalibrated construction profile, smooth polars): AUW 1934 g, best-endurance
27 W at 9.5 m/s (14 W/kg), 0.8–0.9 Wh/km, printed fraction 45 %, CL_max_3D 1.19,
V_stall 8.6 m/s at 54 g/dm².

- **Inside every band, but at the optimistic edge of the power/energy ones** — a
  14 W/kg prediction for an AR-9 airframe undercuts the measured Mini Talon
  (34 W/kg, lower AR, draggier) and approaches the Grafas sailplane floor
  (10–17 W/kg at AR ~15). Plausible, not proven.
- Posture: treat absolute endurance as optimistically biased (smooth polars,
  no prop-in-wake losses, vendor motor constants); trust rankings, not minutes —
  consistent with MODEL_DETAILS.md §2.3.
- Structure and stall sides of the model sit comfortably mid-band.
- Static margin (19.8 %) exceeds the 8–15 % window, but LiftingLine carries no
  fuselage/boom destabilizing moment, so modeled NP is biased aft. Add a fuselage
  moment correction before trusting SM numbers (M2/M3 item).
