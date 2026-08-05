# Equipment manifest — parts, placements, packing

**Status: implemented 2026-08-05.** `src/planeopt/equipment.py` (mechanism),
`aircraft/vtail_rcv2/` (the RC v2 data), `tests/test_equipment.py` (gates).

## The problem this closes

Every aircraft in this project carried its avionics as a handful of lumped point
masses at literal stations:

```python
PointMass("esc_wiring",   0.080, p["nose_tip"] + 0.3932 * p["length"]),
PointMass("fc_gps_rx",    0.060, p["nose_tip"] + 0.5128 * p["length"]),
PointMass("hardware_misc",0.050, 0.450),
```

Three defects, none of which any run would ever have reported:

1. **The fractions were read off a frozen 585 mm pod.** Once `pod_nose`,
   `pod_bay`, `pod_bay_end`, `pod_xs` and `pod_wh` became design variables,
   "0.3932 of the pod length" stopped meaning "on the left wall behind F2" and
   started meaning nothing in particular.
2. **No artifact reported a station for anything.** A `PointMass` is a
   (mass, station) pair and the CG is computed from it, but `run.json` recorded
   `{name: mass}` and threw the station away. The solver knew where the receiver
   went and no output said so.
3. **Packing was three envelopes and one stack length.** Nothing checked that
   the parts fit side by side, that the compass was clear of the ESC, or that a
   65 mm board would go in the nose at all.

## The four decisions (user, 2026-08-05)

| Question | Decision | Consequence |
| --- | --- | --- |
| Placement freedom | **A free station per item** | ~10 new NLP variables |
| Optional kit (Pi, airspeed, SiK) | **Fitted, and priced by a study** | one extra full re-solve |
| Mass basis | **Solve at max weights** | designs the 950 g electronics build |
| Where it lands | **New `aircraft/vtail_rcv2/`** | `vtail_sample` untouched |

Option 1 was taken against a recommendation. The concern was flat manifolds — a
1 g SD card with a design variable is a direction the objective is almost blind
to, and this project has been bitten by that before (`pod_wh` stayed locked for
exactly that reason until the drag model could see shape). Two things reduce the
risk to something acceptable, and one measurement will settle it:

- **Only items with real freedom get variables.** A card in a slot rides its
  reader (`Item.rides`); a servo in a wing pocket, a motor on a mount and a
  cable run's centroid come from structure (`derived_stations`). Ten items are
  genuinely free; nine more are placed without a variable because they have
  nowhere else to be. Inventing freedom an aeroplane does not have is not the
  same as giving the optimizer freedom it does.
- **The gradient is not zero.** Station enters the objective through nose
  ballast: the static-margin floor binds, `ballast_kg` is free, so moving mass
  forward buys ballast back and ballast is AUW. Small, but signed and real.
- **`active_bounds` will say.** Every placement variable that ends pinned at a
  lane end is reported by name. If they all pin, the freedom bought nothing and
  the lanes can collapse to derived packing — measured, then deleted, which is
  the same treatment the 1.8 d_eq boat-tail floor is on.

## The mechanism (`planeopt.equipment`)

Architecture-agnostic, per the iron rule. Nothing in it knows what a pod is.

- **`Item`** — one BOM line: mass (est and max), installed envelope, lane, order,
  `rides`, `fitted`, `airborne`, the requirement verbatim, and `unenforced`.
- **`Lane`** — a 1-D corridor with symbolic ends and an optional section. Items
  pack along it in declared `order`, fore to aft.
- **`Separation`** — a required fore/aft distance in a *declared direction*, so
  every row is a smooth one-sided inequality. `abs(x_a - x_b)` would put a kink
  in the middle of the feasible set; which part is forward of which is a build
  fact the layout already knows.
- **`SectionStack`** — lanes that coexist at the same stations, so their widths
  (or heights) add across the section. This is what ties a parts list to
  `pod_xs`/`pod_wh`.

Symbolic safety: stations and lane bounds may be design expressions; item sizes
and masses are declared floats, so every `max()` is a plain max over data and
never a branch on a design-variable value.

### What it deliberately does not model

3-D packing. Items in one lane never overlap in x, so a lane only has to admit
its widest occupant; lanes that *can* overlap in x are declared as a stack and
their occupants add. Anything finer would need the x-overlap test itself, which
is a branch on design-variable values.

Nor does it model any requirement that is not a function of a station — antenna
geometry, RF transparency, cooling paths, hatch access, orientation. Those are
carried verbatim in `unenforced` and printed in a column headed *not checked by
this model*. A requirement this model cannot see stays the builder's, and says so.

## The RC v2 data (`aircraft/vtail_rcv2`)

19 airborne parts + 4 ground items, from `Planes/RC/RC v2/ELECTRONICS_SPEC.xlsx`
v1.2. Lanes, mapped from the spec's station map onto the parametric loft:

| lane | corridor | contents (fore → aft) |
| --- | --- | --- |
| `bay_floor` | `bay_start` → `bay_end` | battery (station = `x_battery`, the balance knob) |
| `bay_left` | F2 → `bay_end` | ESC |
| `bay_right` | F2 → `bay_end` | SiK air unit |
| `bay_shelf` | F2 → `bay_end` | Pi, BEC, FC, RX, airspeed board |
| `bay_deck` | F2 + 80 mm → `bay_end` | GPS/compass, buzzer |
| `nose_bay` | first station that admits it → `bay_start` | Pi, BEC — **pusher only** |

**F2 is the battery's aft face**, i.e. `x_battery + 138/2`. That makes the
balance variable do double duty: pushing the pack aft for CG squeezes the
avionics. It is a real trade this aeroplane has and no previous model could see.

Not packed, because they have nowhere else to be: motor and prop (mount), four
servos (wing pockets at 65 % semi-span, tail root block), the pitot (outer wing
LE at 2/3 semi-span, 40 mm proud), and the two halves of the wiring run.

### Three findings from the transcription

1. **The sheet's stated max cap is 55 g light.** It says "≈ 895 cap"; its own
   Max-wt column sums to **950 g**. Since this package solves on the max basis,
   that is the difference between the aeroplane the sheet claims and the
   aeroplane it specifies. `tests/test_equipment.py` pins both numbers.
2. **The BOM was written for a pusher; this aeroplane is a puller.** Every
   placement note assumes the DESIGN_SPEC tail-pusher layout — nose bay free,
   "everything forward is clean". The pusher was priced twice and lost by
   9.5–10.7 min, so the nose is full of motor. The nose bay is still modelled
   and used under a pusher; under a puller the Pi and BEC take the fallback the
   BOM itself names ("beside FC tray"), and the pitot takes the wing LE, which
   the BOM lists first anyway.
3. **The 68 mm section is within a millimetre of not holding its own
   electronics.** ESC (8 mm, left wall) + FC (36 mm, shelf) + SiK (10.7 mm,
   right wall) + 6 mm play = 60.7 mm against 61.0 mm of interior width.

## What a run now reports

- `masses.components` — mass **and station** for every component, all aircraft.
- `masses.equipment` — group totals on both bases, `placements_mm`, the full row
  set, and a **closure check**: AUW and CG recomputed with every part at its
  heaviest legal substitute, at fixed placement. Not a re-optimization, and the
  artifact says so — a re-solve would move the wing and the ballast to absorb it.
- `performance.optimization.priced_options` — what dropping the optional kit is
  worth, **priced and never adopted**.
- `manufacturing/equipment_placement_*.csv` — the bench sheet, one row per BOM
  line, with the unchecked requirements in their own column.

## Open

- **Does the placement freedom pay?** Read `active_bounds` on the first battery.
  All-pinned means collapse the lanes to derived packing.
- **The pitot is not in the drag buildup.** A probe 40 mm proud at 2/3 semi-span
  is a parasite body this model does not carry. Small, but currently free.
- **The tail group is over its 120 g budget, and that is reported rather than
  enforced.** Everything aft of the tail block comes to **154.5 g** at the fixed
  design — printed V-tail 126.5 g plus two ruddervator servos. Writing it as a
  constraint would not discipline the design, it would delete the aeroplane, and
  what it would really be constraining is the printed-surface mass model, whose
  constants are uncalibrated until `tools/fit_profile.py` runs on slicer data.
  So `masses.equipment.tail_group` states the number with its own verdict and
  the reader decides whether the tail is heavy or the model is pessimistic.
