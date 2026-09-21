# Design brief — vtail_sample_v1.6 / endurance_sample

Generated from `2026-07-27T07:57:40` run artifacts. Numbers below are the
model's optimum and the constraints that bound it — design around them,
and use the prices to judge deviations.

**Champion:** 123.5 min at V = 9.5 m/s, AUW 1.769 kg, static margin 0.080.

**Mass price:** 7.79 min per 100 g added anywhere on the aircraft (from the champion re-solve). Any wetted-area
or structure choice can be converted through this.

## Surfaces

| surface | airfoil | span (m) | area (m²) | root chord (mm) | tip chord (mm) |
| --- | --- | --- | --- | --- | --- |
| wing | sd7037 | 2.000 | 0.4016 | 245 | 140 |
| vtail | naca0009 | 0.437 | 0.0408 | 106 | 80 |

## Cross-section (front view)

- **inner floor (battery + 4 mm play):** 47 mm W x 37 mm H
- **wall + foam liner allowance, per side:** 4 mm
- **champion outer section:** 54 mm W x 70 mm H (rounded rectangle)

## Length budget (champion optimum)

- **nose (elliptical, floor 1.0 x d_eq):** 61 mm (floor 61 mm)
- **equipment bay (constant section):** 205 mm
- **boat-tail (floor 1.8 x d_eq):** 111 mm (floor 111 mm)
- **overall pod:** 377 mm
- **fineness (L / d_eq):** 6.14

## Balance — battery must reach these stations

- **bay interior spans:** 332 mm to 537 mm aft of nose datum
- **battery CG window (3 mm end margins):** 400 mm to 469 mm
- **champion battery CG:** 400 mm

## Fixed interfaces

- **wing saddle: full-section bay must span:** 380 mm to 537 mm (LE - 10 mm to 60% root chord); champion bay 332 mm to 537 mm
- **pod top embeds into wing root plane:** 6 mm
- **boom socket at tail cap (pod-boom topology):** 12 mm OD at station 648 mm
- **tail block station (champion tail arm):** 1322 mm
- **ESC / FC+GPS stack lengths:** 55 mm / 60 mm

## Deviation prices (mass route only — drag adds on top)

- **+0.01 m2 wetted area:** 1.14 objective units
- **+100 g anywhere:** 7.79 objective units

---

Import the finished CAD as .STEP (`planeopt` CAD round-trip): the app
verifies packaging, reviews the shape against drag rules, prices the
wetted-area delta, and re-optimizes the aircraft around it.
