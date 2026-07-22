# Design Optimization Framework — Concept

Goal: a Python/AeroSandbox program that converges on a recommended aircraft design by
co-optimizing geometry, mass, and trim — replacing manual trial-and-error in XFLR5/flow5.
This document defines the *idea and formulation only*. Detailed per-module
formulations (equations, data, calibration) live in `MODEL_DETAILS.md`; execution
details (stack, code structure, interfaces, milestones) live in `EXECUTION_PLAN.md`.

**Scope: the program is general-purpose.** Aircraft-specific facts — hardware, geometry
architecture, construction method, mission — enter as input data (aircraft configuration
+ construction profile), never as code. The fully specced v1.2/v1.3 design in
`DESIGN_SPEC.md` (1800 mm V-tail pusher, motor behind the tail, 3D-printed, D3548
900kV + 4S 4000mAh, Bambu A1 256 mm bed, hand launch / belly land) is the **sample /
test aircraft** used to develop, calibrate, and validate the framework. For that
aircraft, its purchased hardware is declared as fixed equipment in the config —
not subject to optimization.

---

## 1. Why an optimizer instead of batch simulation

Aerodynamic analysis alone cannot pick a design: endurance is dominated by couplings
*between* disciplines (bigger wing → heavier structure → more lift needed → CG shift →
more ballast → heavier still). The design problem is the coupling. Therefore this is a
small MDO (multidisciplinary design optimization) program in which aerodynamics is one
module among several:

- Parameterized geometry (one design vector generates a complete, valid aircraft)
- Mass model (structure weight as a function of geometry, calibrated to real prints)
- Mass placement / CG model (extends naturally to weight-distribution studies later)
- Propulsion + energy model (prop × motor × ESC efficiency, usable battery energy)
- Aerodynamics (AeroSandbox VLM + airfoil models)
- Constraint set (what makes the output buildable and flyable)
- Mission layer (declared objective + operating points; the framework owns no objective)
- Optimizer (AeroSandbox's built-in gradient-based optimization)

Tool roles: **AeroSandbox is the core loop** (built for exactly this). **flow5 is the
validator** — champion designs get cross-checked there (and eventually flight-tested),
not iterated there.

## 2. Objective — declared by the mission, never hardcoded

The framework owns no objective. Each run's mission config selects it from an
**objective library** — endurance, range, max cruise speed, raw max speed, minimum
energy per distance; extensible (full definitions: `MODEL_DETAILS.md` §5). Two
principles bind every entry:

- **Never a proxy.** Optimize the real mission quantity — minutes, km, m/s, Wh/km —
  never "efficiency," L/D, or CL^1.5/CD as a stand-in. Classic results (best-endurance
  speed near max CL^1.5/CD, speed-to-fly shifting into a headwind) must *emerge* from
  the optimization, not be assumed into it.
- **The operating point is part of the design.** The speed/CL/trim state at which the
  objective is evaluated is co-optimized with geometry.

Wind treatment is objective-dependent, defined per library entry: a minimum-airspeed
constraint for time-aloft, part of the objective (ground speed) for range-class
missions, irrelevant for speed missions.

Competing objectives are handled by ε-constraint sweeps (true Pareto fronts) with a
normalized weighted-sum available as a quick look.

**Sample mission (test aircraft): endurance.**

> endurance = usable battery energy ÷ cruise power draw

- Usable energy: ~59 Wh pack × ~80% usable fraction.
- Cruise power: weight × airspeed ÷ (L/D), divided by propulsion-chain efficiency
  (realistically ~0.5–0.65 for the folding 11×6 at low speed).
- Wind: V_cruise ≥ mission wind + penetration margin — blocks the zero-wind
  optimizer's unflyable-floater failure mode.

## 3. Design variables

**Continuous (inner loop):**
- Span (~1.5–2.2 m bounds)
- Root chord and taper ratio
- Cruise speed / cruise CL (operating point)
- Tail arm and V-tail panel area (dihedral angle stays fixed at 38°)
- Battery tray position (±20 mm travel per fuselage spec) and nose ballast mass
  (ideally driven to zero)
- Spar sizing: outer diameter and wall thickness per spar segment, continuously sized
  against structural constraints (rounded to real catalog tubes in post-processing)
- Optional: washout, wing incidence

**Discrete (outer loop — enumerate, don't optimize):**
- Airfoil: run the full continuous optimization once per candidate
  (SD7037 baseline vs. e.g. AG35, E205, MH32-class), compare champions.
- Any future configuration question (e.g. revisiting tail type) is handled the same way.

**Fixed parameters (not variables):** motor, battery, ESC, prop (purchased hardware),
print bed, launch/landing method. Prop diameter/pitch is a cheap future addition.

## 4. Constraints

The constraints *are* the design knowledge; without them the answer is always
"infinite span, zero speed." Each is an explicit inequality:

| Constraint | Value / basis | Why it exists |
|---|---|---|
| Weight closure | AUW = fixed masses + structure(geometry) | Makes span cost grams; the coupling that makes the optimum finite. Calibrate vs. real printed parts (budgets: wing ~450 g, pod ~250 g, tail ≤130 g). |
| Stall speed | ≤ ~7–8 m/s | Hand launch, belly land, no runway. Often the active constraint that sizes wing area. |
| Static margin | ~8–15% MAC, using the CG the mass model *produces* | Protects the aft-heavy tail-motor layout; stops "free" tail-arm stretching paid for in nose lead. |
| Ballast | ≤ ~70 g (per adopted balance solution) | Or penalize in the objective and let it compete. |
| Trim | Moment equilibrium at cruise; ruddervator deflection well inside ±12/16 mm throws; CL_cruise ≥ ~30% below CL_max | Gust margin; keeps the trim state real. |
| Tip Reynolds | ≥ ~90k | Existing project rule, formalized; stops runaway taper. |
| Structure | Root bending stress ≤ allowable/SF at ~5 g limit load; tip-deflection cap — with spar dimensions as continuous design variables (sized-to-load) | Even a crude beam model blocks the glider-wing failure mode; the optimizer drives the spar to the constraint boundary. |
| Manufacturing | Chord ≤ print bed; panel section lengths; battery-bay volume | Buildability on the A1. |
| Min cruise speed | ≥ mission wind + penetration margin (~9–10 m/s for a 3–4 m/s wind) | Wind penetration — this constraint *is* the wind model; easy to forget, very real. |

## 5. Outputs to watch (diagnostics, not knobs)

The most informative result is not the design vector — it's the constraint activity
and sensitivities:

- **Active constraint set** — tells you where real-world effort should go
  (stall-limited → airfoil matters; weight-limited → engineer lighter prints).
- **Sensitivities / shadow prices** — minutes per gram of empty weight, per mm of span,
  per gram of ballast. Near-free from a gradient-based optimizer; the most useful
  numbers for every future decision on the airplane.
- **Per-candidate sanity checks** — span efficiency (~0.95–1.0 plausible), tip lift
  distribution (taper + washout adequacy), cruise CL vs. airfoil drag bucket at real
  Re (~150–200k), trim drag fraction, prop advance ratio at cruise (flag if far from
  where an 11×6 is happy).
- **Flatness of the optimum** — plot the objective (e.g. endurance) vs. span around the peak; on a plateau,
  prefer the smaller/stiffer/cheaper end. The last 2% is inside model error.

## 6. Phasing

Each phase is independently useful; stop whenever the payoff stops:

1. **Baseline evaluation first (no optimization):** run the existing v1.2/v1.3 spec
   through the framework as a fixed design. Debugs the mass/trim/aero models against
   trusted numbers and yields a baseline endurance prediction.
2. **Wing optimization:** fixed configuration and airfoil; free span/chord/taper/cruise
   speed with the simple weight model. Teaches most of the framework.
3. **Tail + balance:** add tail sizing, CG, static-margin and trim constraints
   (the V-tail/pusher balance problem).
4. **Airfoil selection:** discrete outer loop over candidates at the real Re range.
5. **Later:** fuselage refinement, weight-distribution studies, prop selection.

## 7. Risks and posture

- **Over-optimization amplifies model error.** The optimizer exploits every weakness in
  the models. Output is a *Pareto front / shortlist with visible trade-offs* to argue
  with — a recommendation engine, not an oracle.
- **Weakest model wins.** Great aero + hand-waved weight model = confident convergence
  on the wrong airplane. For 3D printing, weight is driven by infill/walls/spar more
  than planform — calibrate against real test prints early.
- **Fidelity ceiling unchanged.** VLM + 2D viscous corrections; the pusher prop in the
  tail's wake remains unmodeled. flow5 cross-checks and flight tests close that gap.
- **Decision framing:** the optimizer's job is to answer "how far from optimal is v1,
  and does the delta justify redesign?" — "v1 is within a few percent, build it" is a
  valid and valuable outcome.
