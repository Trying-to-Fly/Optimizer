# Endurance V-Tail Pusher — Design Specification

3D-printed endurance RC aircraft. Layout, front to back: fuselage pod → shoulder wing → carbon boom → V-tail → tail-mounted pusher motor with folding prop.

| Overview | |
|---|---|
| Wingspan | 1,800 mm |
| Overall length | ~1,300 mm (pod 585 + cone to 620 + boom + motor/prop) |
| Target all-up weight (AUW) | ~1,800 g |
| Wing loading | ~50 g/dm² |
| Stall speed | ~30 km/h (8.3 m/s) |
| Cruise | 12–14 m/s at ~80–110 W |
| Est. endurance / range | 30–40 min / 25–30 km (80% of pack) |
| Launch / recovery | Hand launch, belly landing |

---

## 1. Power System

| Item | Spec |
|---|---|
| Motor | D3548 900kV, tail-mounted pusher at boom tip |
| Battery | 4S 4,000 mAh 30C (~430 g, ~138 × 44 × 32 mm) |
| ESC | 60 A, mounted in pod (short battery leads ~80 mm — no extra capacitor needed; motor phase wires are the extended run) |
| Prop (test flights) | APC 10×7E |
| Prop (endurance) | Aeronaut CAM 11×6 folding (folds aft on belly landing) |
| Static output | ~550–600 W, ~2.2 kg thrust |
| Thrust angle | 0°, with ±2° shim provision at the motor plate |
| Servos | 4× 9g-class **metal gear** (MG90S-class): 2 ailerons, 2 ruddervators |
| FC / GPS | F405-Wing-class flight controller (30.5 × 30.5 mm mount) + M10 GPS, iNav or ArduPilot |

---

## 2. Wing

### Planform

| Parameter | Value |
|---|---|
| Span | 1,800 mm |
| Center section | 700 mm wide, constant 220 mm chord, flat (0° dihedral) |
| Outer panels | 550 mm each, chord 220 → 150 mm (taper 0.68) |
| Leading edge | Straight — all taper from the trailing edge |
| Area | 35.7 dm² |
| Aspect ratio | 9.1 |
| MAC | ~201 mm (MAC leading edge aligns with root LE) |
| Airfoil | SD7037, root to tip (full section schedule incl. TE truncation: §9) |
| Incidence | +2° to fuselage datum |
| Washout | 2° at tip, linear twist across outer panel only (center section 0°) |
| Dihedral | 3° per outer panel, break at the center/outer panel joint |
| Mounting | Shoulder (top of pod) |

### Winglets
Blended type, printed integral with tip section: **75 mm tall**, canted 15° out from vertical, swept ~30°, **2° toe-out**, thin symmetric section (~8%). LW-PLA, ~8–10 g each. (Deletable without redesign — replace with rounded tip cap.)

### Ailerons
- One per outer panel: **460 mm × 22% chord**, from just outboard of the dihedral joint to 40 mm short of the tip
- Servo in-wing at ~65% semi-span, direct linkage
- Setup: **2:1 differential** (up:down), flaperon landing mode (both droop 4–5 mm)

### Structure

| Element | Spec |
|---|---|
| Center spar | 10×8 mm CF tube, full 700 mm center section, at 30% chord |
| Outer spars | 8×6 mm CF tube, to ~85% of outer panel |
| Dihedral joint | PETG joiner block: 10 mm socket one side, 8 mm socket at 3° the other, ~60 mm engagement each side |
| Anti-rotation | 4 mm CF pin at ~65% chord, center section |
| Skins | LW-PLA, single perimeter, printed ribs (no slicer infill) |
| Print sections | ~225 mm spanwise, printed vertically: 4 per side + winglet tip |
| Target weight | ~450 g complete |

### Wing-to-pod attachment
- Front: 2 printed tabs on wing root hook into slots in former F3 (station 390)
- Rear: 2× **M4 nylon bolts** at station 566, 30 mm apart, into captured nylon nuts (crash shear-away)
- Aileron leads: connectors through saddle hole at station ~470

---

## 3. V-Tail

### Sizing
Tail arm 700 mm (wing AC → tail AC). Tail volumes: horizontal 0.50, vertical 0.035. Total true area 8.35 dm².

### Panels (each of 2)

| Parameter | Value |
|---|---|
| True area | 4.17 dm² |
| Span (in panel plane) | 320 mm |
| Root / tip chord | 150 / 110 mm (taper 0.73) |
| Trailing edge | Straight, perpendicular to boom in top view |
| LE sweep | 7.1° |
| Dihedral | 38° from horizontal (104° included angle) |
| Incidence / twist / toe | 0° / none / none |
| Airfoil | NACA 0009, constant (section schedule incl. TE truncation: §9) |
| Print | LW-PLA, 2 pieces per panel (root ~180 + tip ~140 mm) joined on spar + 3 mm TE pin |
| Panel spar | 6×4 mm CF tube at 30% chord, root to ~60% span (60 mm into root block) |

CAD tip: model the panel flat (root chord on X axis, tip at Y=320 offset 40 mm aft), loft, cut the ruddervator, then rotate 38° about the boom axis and mirror.

### Ruddervators (each)

| Parameter | Value |
|---|---|
| Chord | 40 mm, constant |
| Length | 300 mm — starts 15 mm from panel root, ends 5 mm before tip |
| Fixed panel chord remaining | 110 mm root / 70 mm tip |
| Thickness | ~7 mm at hinge line → 1.2–1.5 mm at TE |
| LE bevel | 30° symmetric V (allows ±28° in ≤1 mm gap; seal gap with tape) |
| Hinges | 3× flat nylon CA hinges — slots 20 × 0.8 mm, 12 mm deep each side, at 20 / 150 / 280 mm along the surface |
| Control horn | Inboard face, hole 9 mm from hinge line, 35 mm from surface root end |
| Print | LW-PLA, 2 perimeters |

### Throws (at root TE, perpendicular to hinge) and mixing
- Elevator: ±12 mm low / ±16 mm high rate
- Rudder: ±8 mm low / ±11 mm high rate
- Combined deflection cap ~28°; 30% expo both axes
- V-tail mixing in the flight controller (not hardware)

### Tail root block (single PETG part — 4 functions)
Print 40–50% infill, 4 perimeters.

| Feature | Spec |
|---|---|
| Boom clamp | 2× 30 mm slit collars at block ends, bore **12.2 mm** — full detail in §4 |
| Panel sockets | 2× 6 mm bores at 38° (model **6.15 mm**, glue fit), 60 mm deep + 3 mm anti-rotation pin holes near TE + angled root seating pads. Panels epoxy in; whole tail unit removes from boom as one piece |
| Servo bays | 2× MG90S pockets (**23.2 × 12.4 mm**, lugs outboard) ahead of panel LE, shafts outboard. Pushrods 2 mm × ~70 mm, Z-bend at servo, clevis at horn. Servo arm 10 mm : horn 9 mm |
| Motor mount | Block extends ~25 mm past boom tip; aft plate with D3548 cross pattern (**19 & 25 mm spacing, M3**); 0° thrust + ±2° shim provision; open-sided venting around motor |

Prop plane sits 50–65 mm behind the ruddervator TE. Tail group target: **≤120 g** (panels ~35 g each, block ~22 g, servos ~27 g, linkages ~6 g).

---

## 4. Boom & Boom Joints

| Parameter | Value |
|---|---|
| Tube | **12 mm OD × 10 mm ID, woven/roll-wrapped 3K carbon** (not pultruded, not solid rod) |
| Length | ~750 mm total: ~100 mm socketed in pod, ~650 mm exposed |
| Design loads | Bending ~10 N·m at pod joint (15 N tail load × 0.65 m); thrust ~22 N axial; torsion ~0.6–1 N·m (motor torque + asymmetric ruddervator) |
| Wire routing | Motor phase wires twisted + heat-shrunk to left side of boom every ~100 mm; tail servo leads on right side |

### Boom → fuselage: glued socket sleeve (permanent)
One printed PETG socket unit bonded into (or integral with) the rear pod section:

| Feature | Spec |
|---|---|
| Sleeve | 18 mm OD × 105 mm, pod centerline, stations 478–583; internal shoulder at 100 mm depth (sets tail arm — datum) |
| Structure | Bulkhead disks F5/F6 at sleeve ends with 6–8 mm glue flanges to shell + top web to rear wing-bolt block + 2× 45° side gussets (bending couple ≈100 N per bulkhead into shell) |
| Bore | Model **12.3 mm** — target 0.1–0.15 mm epoxy gap per side, light finger-push slip fit. **Print a 10 mm test ring first** to calibrate |
| Torsion keying | 4× internal grooves 1.5 w × 0.8 d mm full length + 1 circumferential groove mid-sleeve (epoxy splines) |
| Glue-up | Sand boom's last 100 mm to dull (150–220 grit), IPA wipe; foam plug 105 mm inside boom bore; 2 mm vent hole at shoulder end of sleeve; 30-min epoxy (not CA); verify depth-to-shoulder and boom parallel to wing saddle before cure |

### Boom → tail: twin clamp collars (removable)
Two short collars integral with the tail root block; the block between them is skeletonized (open frame connecting panel sockets, servo bays, and motor plate — boom passes through untouched). Local joint loads are small (tail lift acts at this station): ~1 N·m torsion, 22 N thrust.

| Feature | Spec |
|---|---|
| Collars | 2× **30 mm** engagement, one at each end of the block (~110 mm apart), bore **12.2 mm** (test-ring calibrate), 1–1.2 mm slit along the bottom of each |
| Bolts | **1× M3 per collar** bridging the slit, heat-set insert one side, socket-head screw the other. Snug + 1/8 turn — do not crush the tube |
| Bore ends | ~1 mm internal chamfer/flare on all four collar edges (no sharp clamp edge on the carbon — stress riser) |
| Print | **Bore axis vertical** (hoop-direction layers take the clamp load), 4–6 perimeters; motor plate lands flat at top of print |
| Wire management | Molded exterior channels: phase wires left, servo leads right; zip-tie slots at each end |

Block weight target drops to ~22 g (tail group ≤120 g).

**Visual references for the collar clamp method** (mechanism = bicycle seatpost clamp: slit ring + bolt bridging the slit):
- Commercial carbon-tube clamps, exact mechanism: https://www.rjxhobby.com/rjx-12-16-20-25mm-pipe-clamps-for-carbon-fiber-tube-aluminum-tube-clips-carbon-tube-clip-pipe-clamp
- 3D-printed 12 mm carbon tube clamp designs (multirotor motor mounts): https://www.stlfinder.com/3dmodels/12mm+Carbon+Tube+Anti+Vibration+Motor+Mount+Clamps/
- Kraga Kodo — 3D-printed pod-and-boom glider, closest whole-aircraft example: https://3dprintedrcplanes.com/kodo/
- Kodo build guide PDF (printed tail structure on carbon boom): https://3dprintedrcplanes.com/static/files/KRAGA_Kodo_build_guide_latest.pdf

### Assembly & alignment sequence
1. Print test rings; calibrate both bores.
2. Epoxy boom into pod socket (depth to shoulder; sight parallel to saddle; cure overnight).
3. Assemble complete tail unit on bench: panels epoxied into block, servos, linkages, motor.
4. Slide tail unit on, plane on flat bench, view from astern: each V-panel tip equal height off bench ±1 mm, and tip-to-same-side-wingtip distances equal (yaw twist check). Tighten both collar bolts.
5. Fly and trim; optional thin-CA bead along one clamp edge as a witness lock, or leave dry for removable-tail transport.

---

## 5. Fuselage Pod

### Form
- Structural pod **585 mm** + tail cone fairing to ~620 mm blending into boom
- Cross-section: rounded rectangle ~**68 W × 88 H mm** external, 12 mm corner radii, flat-ish belly
- Battery on floor (low CG), electronics shelf above, GPS on top deck
- Wing saddle from station 390, cut at **+2° incidence** (LE high)

### Station map (mm from nose tip)

| Station | Feature |
|---|---|
| 0–25 | Nose cap: ballast/FPV bay, chin skid, 2× 8×16 mm cooling inlets |
| 25 | **F1** crash bulkhead (3 mm PETG) — battery front stop |
| 25–205 | Battery bay (180 mm); position set by printed spacer blocks (~10 mm steps = ±20 mm CG range); 2 velcro straps through floor slots; 3 mm foam |
| 205 | **F2** bay rear wall, wire pass-throughs |
| 205–260 | ESC on left sidewall, in cooling airflow |
| 240–310 | FC tray (PETG, 30.5 × 30.5 mm pattern), RX behind |
| 330–385 | GPS/compass on top deck under hatch |
| 390 | **F3** main former — saddle front + wing tab slots |
| 456 | Wing spar passes over pod (inside wing; no carry-through) |
| 480–585 | Boom socket bulkheads F5/F6 |
| 566 | Rear wing bolts: 2× M4 nylon, 30 mm apart, PETG block above boom socket |
| 585–620 | Tail cone: 2× 10×25 mm cooling exits, wire exits |

### Hatch
Top, stations **45–385**, ~55 mm wide opening. Front: 2 tongues under deck. Rear: latch **+** 2× 10×3 mm magnets. 5 mm lip flange, 0.2 mm face clearance.

### Cooling
Nose inlets → over battery → past ESC → tail-cone exits. Exit area ≈ 2× inlet area.

### Belly protection & grip
- 2 replaceable skid rails, 3 mm proud, stations ~60–540, dovetail or screwed — **TPU preferred**, else PETG
- Finger scallops at stations 420–480 (at CG) for launch grip

### Materials & print sections

| Section | Material |
|---|---|
| Nose 0–205 | PETG or PLA, 2 perimeters (crash zone) |
| Mid 205–390 | LW-PLA (PETG FC tray bonded in) |
| Rear 390–585 | PETG, 2–3 perimeters (wing bolts + boom loads) |
| Tail cone, hatch | LW-PLA |

Section joints at 205 and 390: 8 mm internal lip (0.15–0.2 mm clearance), 4× 3 mm pins, epoxy. Pod target weight: **~250 g** incl. hatch.

---

## 6. Balance & Ballast

| Parameter | Value |
|---|---|
| CG | **30% MAC = 60 mm behind wing root LE** (station ~450 from nose) |
| Wing root LE | Station 390 |
| Primary adjustment | Battery spacer blocks (±20 mm) |
| Nose ballast | ~**70 g** steel washers, screw-clamped on post in nose cap (station ~10–20). Rigid retention mandatory |
| FPV upgrade path | Camera + VTX (40–70 g) later replaces ballast ~1:1 in the same bay |

Rule: **nothing heavy is ever added aft of the wing.** Tail parts print at minimum weight; any trim weight goes in the nose cap.

### Weight budget

| Item | Target (g) |
|---|---|
| Battery | 430 |
| Motor + folding prop | 190 |
| ESC + wiring | 80 |
| Servos (4× 9g MG) | 40–55 |
| FC + GPS + RX | 60 |
| Boom (12×10 × 750) | ~42 |
| Wing spars + joiners | ~100 |
| Wing (printed, complete) | 450 |
| Pod (printed, complete) | 250 |
| Tail group | ≤120 |
| Nose ballast | ~70 |
| Hardware / misc | 50 |
| **AUW** | **~1,800–1,900** |

---

## 7. Print Tolerances (A1, quick reference)

| Fit | Dimension |
|---|---|
| Alignment pin holes | pin +0.2 mm |
| Section lip joints | 0.15–0.2 mm clearance |
| M3 heat-set boss holes | 4.0 mm |
| M4 nylon bolt clearance | 4.3 mm |
| Boom clamp bore (tail block) | 12.2 mm + slit (test-ring calibrate) |
| Boom socket bore (pod, epoxied) | 12.3 mm — 0.1–0.15 mm epoxy gap/side (test-ring calibrate) |
| CF spar glue sockets | tube OD +0.15 mm |
| Servo pocket (MG90S) | 23.2 × 12.4 mm |

LW-PLA parts: single perimeter (2 on ruddervators), 0 top/bottom layers where skinned, printed ribs instead of infill.

---

## 8. Setup & First-Flight Checklist

- Verify CG at 60 mm behind root LE with battery installed — adjust spacers, then washers
- V-tail mix, aileron differential 2:1, flaperon mode, 30% expo in FC/TX
- Throws per §3; cap combined ruddervator deflection at 28°
- Balance the folding prop; check boom for throttle-induced twist on a static run
- RX antennas 90° apart, clear of carbon and phase wires
- Maiden with APC 10×7E; switch to folding 11×6 after trim is dialed
- Shim motor plate ±2° only if a power-pitch couple shows up in flight

---

## 9. Airfoil Schedule (all flying surfaces)

**Trailing-edge convention (all sections):** every airfoil is truncated to a **0.8 mm straight vertical TE face**. Method: import the airfoil at the oversize "model-at" chord below, then make a vertical cut at the final chord. The model-at values are close approximations — the governing rule is: **cut at the final chord; the resulting TE face should be 0.8 ± 0.2 mm**. Adjust the import scale slightly if your cut face lands outside that. Movable surfaces (ailerons, ruddervators) inherit this TE as their own trailing edge.

| Surface / station | Airfoil | t/c | Final chord (mm) | Model-at chord (mm) |
|---|---|---|---|---|
| Wing — center section (constant, 700 mm span) | SD7037 | 9.2% (max at ~27% chord; camber 3.0%) | 220 | ~223 |
| Wing — outer panel root (y = 350 mm) | SD7037 | 9.2% | 220 | ~223 |
| Wing — tip (y = 900 mm) | SD7037 | 9.2% | 150 | ~153 |
| V-tail — panel root | NACA 0009 | 9.0% (max at 30%) | 150 | ~152.5 |
| V-tail — panel tip | NACA 0009 | 9.0% | 110 | ~113 |
| Winglet — root (blend off wing tip) | NACA 0008 | 8.0% (max at 30%) | 100 | ~103 |
| Winglet — tip | NACA 0008 | 8.0% | 50 | ~54 |

Notes:
- Intermediate wing stations: chord tapers linearly, chord(y) = 220 − (y − 350) × 70/550 for y = 350–900 mm; loft between root and tip sections
- Wing twist (2° washout) is applied linearly across the outer panel only, **rotating each section about the spar line (30% chord)** so the spar stays straight; center section 0° twist
- V-tail and winglet sections: no twist; V-tail lofts linearly root → tip
- Winglet blends from the wing-tip section over the blend radius; 2° toe-out applied to the whole winglet
- Coordinate files: SD7037 — http://airfoiltools.com/airfoil/details?airfoil=sd7037-il ; NACA 0009 / 0008 — generate at http://airfoiltools.com/airfoil/naca4digit
- The 0.8 mm TE prints cleanly in LW-PLA single-perimeter (≥ one extrusion width each side); do not attempt a sharper TE
