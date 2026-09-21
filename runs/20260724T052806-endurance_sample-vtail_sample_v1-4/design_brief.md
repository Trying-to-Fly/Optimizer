# Design brief — vtail_sample_v1.4 / endurance_sample

Generated from `2026-07-24T05:28:06` run artifacts. Numbers below are the
model's optimum and the constraints that bound it — design around them,
and use the prices to judge deviations.

**Champion:** 109.3 min at V = 9.5 m/s, AUW 1.925 kg, static margin 0.080.

**Mass price:** 6.53 min per 100 g added anywhere on the aircraft (from the champion re-solve). Any wetted-area
or structure choice can be converted through this.

## Cross-section (front view)

- **inner floor (battery + 4 mm play):** 47 mm W x 37 mm H
- **wall + foam liner allowance, per side:** 4 mm
- **champion outer section:** 54 mm W x 70 mm H (rounded rectangle)

## Length budget (champion optimum)

- **nose (elliptical, floor 1.0 x d_eq):** 61 mm (floor 61 mm)
- **equipment bay (constant section):** 486 mm
- **boat-tail (floor 1.8 x d_eq):** 111 mm (floor 111 mm)
- **overall pod:** 658 mm
- **fineness (L / d_eq):** 10.71

## Balance — battery must reach these stations

- **bay interior spans:** 34 mm to 520 mm aft of nose datum
- **battery CG window (3 mm end margins):** 102 mm to 452 mm
- **champion battery CG:** 102 mm

## Fixed interfaces

- **wing saddle: full-section bay must span:** 380 mm to 520 mm (LE - 10 mm to 60% root chord); champion bay 34 mm to 520 mm
- **pod top embeds into wing root plane:** 6 mm
- **boom socket at tail cap (pod-boom topology):** 12 mm OD at station 631 mm
- **tail block station (champion tail arm):** 1050 mm
- **ESC / FC+GPS stack lengths:** 55 mm / 60 mm

## Deviation prices (mass route only — drag adds on top)

- **+0.01 m2 wetted area:** 0.96 objective units
- **+100 g anywhere:** 6.53 objective units

---

Import the finished CAD as .STEP (`planeopt` CAD round-trip): the app
verifies packaging, reviews the shape against drag rules, prices the
wetted-area delta, and re-optimizes the aircraft around it.
