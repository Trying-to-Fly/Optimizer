# Design brief — vtail_sample_v1.3 / endurance_sample

Generated from `2026-07-23T11:16:34` run artifacts. Numbers below are the
model's optimum and the constraints that bound it — design around them,
and use the prices to judge deviations.

**Champion:** 106.2 min at V = 9.5 m/s, AUW 2.008 kg, static margin 0.080.

**Mass price:** 7.44 min per 100 g added anywhere on the aircraft (from the champion re-solve). Any wetted-area
or structure choice can be converted through this.

## Cross-section (front view)

- **inner floor (battery + 4 mm play):** 47 mm W x 37 mm H
- **wall + foam liner allowance, per side:** 4 mm
- **champion outer section:** 68 mm W x 88 mm H (rounded rectangle)

## Length budget (champion optimum)

- **nose (elliptical, floor 1.0 x d_eq):** 30 mm (floor 77 mm)
- **equipment bay (constant section):** 380 mm
- **boat-tail (floor 1.8 x d_eq):** 175 mm (floor 139 mm)
- **overall pod:** 585 mm
- **fineness (L / d_eq):** 7.56

## Balance — battery must reach these stations

- **bay interior spans:** 30 mm to 410 mm aft of nose datum
- **battery CG window (3 mm end margins):** 98 mm to 342 mm
- **champion battery CG:** 95 mm

## Fixed interfaces

- **wing saddle (bay aft end, datum anchor):** 410 mm
- **pod centerline below wing datum:** 30 mm
- **boom socket at tail cap (pod-boom topology):** 12 mm OD at station 585 mm
- **tail block station (champion tail arm):** 1077 mm
- **ESC / FC+GPS stack lengths:** 55 mm / 60 mm

## Deviation prices (mass route only — drag adds on top)

- **+0.01 m2 wetted area:** 1.09 objective units
- **+100 g anywhere:** 7.44 objective units

---

Import the finished CAD as .STEP (`planeopt` CAD round-trip): the app
verifies packaging, reviews the shape against drag rules, prices the
wetted-area delta, and re-optimizes the aircraft around it.
