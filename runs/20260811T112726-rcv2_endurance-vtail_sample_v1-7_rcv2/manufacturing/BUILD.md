# Build document — vtail_sample_v1.7_rcv2 / rcv2_endurance

From the `2026-08-11T11:27:26` run. Every dimension here is read off the
same geometry the solver analysed.

**Datum and units.** Millimetres unless stated. Aircraft frame: **+x aft**
from the nose datum, **+y starboard**, **+z up**. Surfaces marked
symmetric are given as the STARBOARD half only — mirror about y = 0.

## 1. Balance — get this right first

- **CG target:** **503.2 mm** aft of the nose datum
- **Allowable CG range:** 481.7 mm (forward, 15% margin) to 497.9 mm (aft, 8% margin) — a **16 mm** window
- **Neutral point:** 516.5 mm; reference chord 232.0 mm
- **As-designed static margin:** 0.0572
- **WARNING — the CG target is 5.3 mm aft of the aft limit** derived just above. The design does not meet the stability window it was optimized against. Nothing outside this app checks that margin — weigh, balance and fly conservatively rather than treating the number as verified.
- **Nose ballast in this design:** 0 g

Aft of the aft limit the aircraft is unflyable, not merely twitchy.
Weigh and balance before the first flight, not after.

## 2. Surfaces

| surface | airfoil | span_mm | area_m2 | root_chord_mm | tip_chord_mm | sections | mirrored |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wing | sd7037 | 2,000 | 0.4639 | 275 | 136.5 | 5 | True |
| vtail | naca0009 | 458.2 | 0.0417 | 91.1 | 90.9 | 2 | True |

Every surface the solver analysed, including any the report's summary
table omits. `mirrored` surfaces are given as the starboard half.

Section-by-section loft (leading/trailing edge points, chord, twist,
airfoil) is in `../geometry/stations.csv`; the placed airfoil outlines
are in `../geometry/sections_3d.csv`. Edge polylines are in
`edges.csv` beside this document — the loft between stations is
STRAIGHT, so those points are the whole edge, not a sampling.

## 3. Control surfaces

- **ruddervator** on `vtail`, station 0→1: hinge at **60% chord**, length 229.1 mm, control chord 36.4 → 36.4 mm (mirrored pair)

The hinge is a constant CHORD FRACTION, so on a tapered panel the
hinge line is not square to the root. Endpoints are in `hinges.csv`.

## 4. Mass budget

Target all-up weight **2105 g**.

| component | mass (g) | station (mm) | share |
| --- | --- | --- | --- |
| printed_wing | 633.3 | 494 | 30.1% |
| battery | 460.0 | 341 | 21.9% |
| pod | 213.8 | 471 | 10.2% |
| motor | 170.0 | 243 | 8.1% |
| wing_spars_joiners | 124.2 | 472 | 5.9% |
| printed_vtail | 80.8 | 1594 | 3.8% |
| esc | 75.0 | 446 | 3.6% |
| propeller | 55.5 | 200 | 2.6% |
| boom | 47.2 | 1133 | 2.2% |
| flight_controller | 40.0 | 534 | 1.9% |
| telemetry_sik | 30.0 | 442 | 1.4% |
| wiring_pod | 24.0 | 441 | 1.1% |
| gps_compass | 22.0 | 542 | 1.0% |
| companion_pi | 20.0 | 448 | 1.0% |
| wiring_boom | 16.0 | 1133 | 0.8% |
| servo_aileron_left | 14.0 | 574 | 0.7% |
| servo_aileron_right | 14.0 | 574 | 0.7% |
| servo_ruddervator_left | 14.0 | 1529 | 0.7% |
| servo_ruddervator_right | 14.0 | 1529 | 0.7% |
| bec_pi | 12.0 | 494 | 0.6% |
| pitot_probe | 9.0 | 401 | 0.4% |
| airspeed_board | 6.0 | 600 | 0.3% |
| receiver_elrs | 5.0 | 575 | 0.2% |
| buzzer | 3.0 | 561 | 0.1% |
| sd_card_fc | 1.0 | 534 | 0.0% |
| sd_card_pi | 1.0 | 448 | 0.0% |
| nose_ballast | 0.0 | 210 | 0.0% |

| **total** | **2105** | | |

Stations are millimetres aft of the nose datum — the same datum the
CG above is quoted against, so this table is a weigh-and-balance
sheet as well as a shopping list.

## 5. Spars (sized at 5 g limit load)

| part | qty | od_mm | wall_mm | bore_mm | length_mm | mass_g | root_moment_Nm | stress_MPa | stress_allow_MPa | stress_margin_pct | tip_defl_mm | defl_allow_mm | defl_margin_pct | stock_length_mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| centre carry-through | 1 | 10 | 1 | 8 | 350 | 15.8 | 19.7 | 339.9 | 200 | -41.2 | 25.2 | 17.5 | -30.6 | 700 |
| outer panel | 2 | 8 | 1 | 6 | 467.5 | 16.4 | 6.82 | 198.3 | 200 | 0.8 | 32.8 | 23.4 | -28.8 | 467.5 |

Also written as `spars_sized_at_5_g_limit_load.csv`.

## 6. Stock list

| item | spec | length_mm | qty |
| --- | --- | --- | --- |
| CF tube, centre spar | 10.0 x 1.00 mm wall | 700 | 1 |
| CF tube, outer spar | 8.0 x 1.00 mm wall | 467.5 | 2 |
| CF boom tube | 12 x 10 mm (1 mm wall) | 605.3 | 1 |

Also written as `stock_list.csv`.

## 7. Nose parts (the loft is the outer mould line, not one part)

- **nosecone — removable fairing over the motor:** 9 mm long, nose tip to bulkhead (station 0 mm to 9 mm); mates to a 49 mm x 63 mm face
- **pod front bulkhead:** 49 mm x 63 mm section, circular opening 42 mm = the can's own diameter (add print clearance to taste — the model sizes the structure, not the fit), wall 3.5 mm per side
- **motor bay depth, bulkhead to bay start:** 21 mm for a 51 mm can
- **print note:** the cone is a fairing, not structure — the motor mount takes its load into the bulkhead, and the model charges the cone's skin through the pod's own wetted-area mass term

## 8. Spar and joint stations

- **reading the spar margins:** 0% means the constraint is ACTIVE — the optimizer sized the tube exactly to its limit, which is the expected outcome, not a warning. The 2x safety factor is already inside the 400 MPa allowable, so the quoted allowable is 200 MPa.
- **load case:** 5 g limit, elliptical lift, no inertia relief
- **spar line, aft of nose datum:** 456 mm
- **as a fraction of root chord:** 30%
- **wing joint (centre spar ends, outer begins):** 350 mm from centreline (eta = 0.389)
- **semi-span:** 900 mm
- **dihedral form:** curve
- **spar hole must clear:** 70% of section thickness

## 9. Control throws

- **pitch surface:** ruddervator
- **control chord (mean):** 35 mm
- **available TE throw (linkage):** +/- 12 mm
- **trim may use:** 33% of it (= +/- 6.5 deg)
- **as-trimmed deflection:** see report.html / run.json

## 10. Equipment placement (stations mm from nose datum)

| item | group | example part | station_mm | mass_g | mass_basis | max_g | size_mm | lane | status | requirement | not checked here |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| motor | Propulsion | D3548 900 kV brushless outrunner | 34.7 | 170 | max | 170 |  | derived from structure | placed | Bolts to the motor plate; prop plane 50-65 mm behind the ruddervator TE (pusher). HARD limit — the farthest-aft mass on the aircraft. | 0 deg thrust line with +-2 deg shim provision | mount must match the 19/25 mm M3 cross on the tail-block plate, or use a <=10 g adapter | open-sided venting around the can | UNDER A PULLER this row's pusher geometry does not apply — the can sits inside the nose, sized by the motor-fit constraint |
| propeller | Propulsion |  | 5 | 55.5 | max | 55.5 |  | derived from structure | placed | On the shaft, at the spinner. |  |
| esc | Propulsion | Hobbywing Skywalker 60A V2 (or AM32 equivalent, no BEC) | 220 | 75 | max | 75 | 60.0 x 8.0 x 25.0 | bay_left | placed | Left sidewall, aft of the battery. May overlap the FC-tray zone lengthwise — different wall. | must sit in the nose-inlet -> tail-exit cooling stream | battery leads <=100 mm; phase wires exit rear into the LEFT boom channel, twisted + heat-shrunk every ~100 mm |
| battery | Propulsion | 4S 4,000 mAh 30C LiPo | 115 | 460 | max | 460 | 138.0 x 44.0 x 32.0 | bay_floor | placed | Battery bay, hard against the F1 crash bulkhead via printed spacer blocks. Its station IS the balance variable. | 2 velcro straps through floor slots + 3 mm foam | must be rigidly retained — belly lander; a loose pack through F1 is the crash mode |
| servo_aileron_left | Actuation | MG90S metal gear (9 g class) | 494.7 | 14 | max | 14 | 22.8 x 12.2 x 28.5 | derived from structure | placed | Wing, 65% semi-span, direct linkage. | body must fit the printed 23.2 x 12.4 mm pocket, lugs outboard |
| servo_aileron_right | Actuation | MG90S metal gear (9 g class) | 494.7 | 14 | max | 14 | 22.8 x 12.2 x 28.5 | derived from structure | placed | Wing, 65% semi-span, direct linkage. | body must fit the printed 23.2 x 12.4 mm pocket, lugs outboard |
| servo_ruddervator_left | Actuation | MG90S metal gear (9 g class) | 1,140 | 14 | max | 14 | 22.8 x 12.2 x 28.5 | derived from structure | placed | Bay in the tail root block, 70 mm x 2 mm pushrod. | counts against the <=120 g tail-group budget — NO heavier substitutes at the tail, ever |
| servo_ruddervator_right | Actuation | MG90S metal gear (9 g class) | 1,140 | 14 | max | 14 | 22.8 x 12.2 x 28.5 | derived from structure | placed | Bay in the tail root block, 70 mm x 2 mm pushrod. | counts against the <=120 g tail-group budget — NO heavier substitutes at the tail, ever |
| flight_controller | Autopilot core | Matek H743-WING V3 (spec minimum: F405-Wing class) | 311 | 40 | max | 40 | 54.0 x 36.0 x 13.0 | bay_shelf | placed | FC tray on the avionics shelf, aft of the battery. | 30.5 x 30.5 mm pattern, arrow FORWARD and level | soft-mount (foam tape / grommets) — pusher prop vibration comes down the boom | keep off the ESC wall (heat) | USB port reachable through the hatch for bench work |
| sd_card_fc | Autopilot core | 32 GB class-10 | 311 | 1 | max | 1 | 15.0 x 11.0 x 1.0 | rides flight_controller | placed | FC card slot (no freedom of its own). | slot must face somewhere reachable through the hatch |
| gps_compass | Autopilot core | Matek M10Q-5883 (M10 GNSS + QMC5883L mag) | 320 | 22 | max | 22 | 20.0 x 20.0 x 12.4 | bay_deck | placed | Top deck, highest point in the pod. >=80 mm from the battery leads and from the ESC. | directly under the LW-PLA hatch skin — RF-transparent, no carbon or metal above it | all high-current wiring routed below the deck shelf | sky view unobstructed |
| airspeed_board | Autopilot core | Matek ASPD-4525 (MS4525DO / DLVR based) | 379 | 6 | max | 6 | 22.0 x 16.0 x 8.0 | bay_shelf | placed | Within 300 mm of the FC — this is an I2C run, not a bus. | tubing kink-free |
| pitot_probe | Autopilot core |  | 350 | 9 | max | 9 |  | derived from structure | placed | Clean air: outer wing LE at ~2/3 semi-span, protruding >=40 mm ahead of the surface, clear of the fuselage boundary layer. | a handling hazard on a hand launch — position away from the grip | its own parasite drag is NOT in the buildup at this fidelity |
| buzzer | Autopilot core | Passive buzzer on FC BUZ pads | 340 | 3 | max | 3 | 12.0 x 12.0 x 9.5 | bay_deck | placed | Anywhere in the pod — no structural requirement. | unobstructed sound path — near the hatch seam or a cooling exit |
| companion_pi | Companion compute | Raspberry Pi Zero 2 W | 223 | 20 | max | 20 | 65.0 x 30.0 x 13.0 | bay_shelf | placed | Nose bay preferred, flat against the F1 bulkhead face (max forward moment). Fallback: beside the FC tray — which is where a PULLER puts it, the nose being full of motor. | keep the WiFi antenna end clear of carbon | common ground with the FC | verify nose-cap internal clearance in CAD |
| bec_pi | Companion compute | Matek mini BEC / Pololu D24V22F5, 5 V / 3 A | 270 | 12 | max | 12 | 20.3 x 17.8 x 5.0 | bay_shelf | placed | Within ~50 mm of the Pi; twisted input pair from the PDB tap. | common ground with the FC |
| sd_card_pi | Companion compute | 32 GB A1 | 223 | 1 | max | 1 | 15.0 x 11.0 x 1.0 | rides companion_pi | placed | Pi card slot (no freedom of its own). | orient the slot toward the hatch |
| receiver_elrs | RC link | RadioMaster RP3 V2 (ELRS 2.4 GHz diversity) | 353 | 5 | max | 5 | 22.0 x 13.0 x 4.0 | bay_shelf | placed | Behind the FC tray. | THE ANTENNAS ARE THE REAL CONSTRAINT, NOT THE BOARD: tips 90 deg apart and >=30 mm from ANY carbon (boom, wing spar), from the phase wires and from the GPS puck |
| telemetry_sik | Telemetry / GCS | Holybro SiK Radio V3, 915 MHz 100 mW (air unit) | 217 | 30 | max | 30 | 53.0 x 10.7 x 28.0 | bay_right | placed | RIGHT sidewall, opposite the ESC. >=100 mm from the GPS puck (desense). | antenna vertical; do not lay it along the boom | >=100 mm from the ELRS antennas |
| wiring_pod | Support |  | 220 | 24 | max | 24 |  | derived from structure | placed | Distributed through the bay; charged at the bay centroid. | keep every harness clear of the RX antennas |
| wiring_boom | Support |  | 862.6 | 16 | max | 16 |  | derived from structure | placed | Motor phase wires in the LEFT boom channel, servo leads in the RIGHT; charged at the boom's midpoint. | zip-tie slots at both boom ends | aileron leads pass through the wing saddle |
| transmitter | RC link | RadioMaster Boxer ELRS 2.4 GHz |  |  |  |  |  |  | ground/bench — no airframe constraint | Ground item — no airframe constraint. |  |
| ground_station | Telemetry / GCS | Laptop + Mission Planner / QGroundControl |  |  |  |  |  |  | ground/bench — no airframe constraint | Ground item — no airframe constraint. |  |
| charger | Support | ISDT / ToolkitRC >=100 W balance charger |  |  |  |  |  |  | ground/bench — no airframe constraint | Bench item — no airframe constraint. |  |
| lipo_checker | Support | Any cell-voltage checker |  |  |  |  |  |  | ground/bench — no airframe constraint | Field-box item — no airframe constraint. |  |

Also written as `equipment_placement_stations_mm_from_nose_datum.csv`.

---

Generated by `planeopt build`. Re-run it after any re-solve — every
number above moves with the design.
