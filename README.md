# planeopt

General-purpose small-aircraft MDO: co-optimize geometry, mass, and trim for a
mission-declared objective. Built on AeroSandbox (CasADi + NeuralFoil).

The docs are the spec, in reading order:

1. `docs/OPTIMIZATION_CONCEPT.md` — the idea and formulation
2. `docs/MODEL_DETAILS.md` — per-module equations, data, calibration
3. `docs/EXECUTION_PLAN.md` — this codebase's structure and milestones
4. `docs/DESIGN_SPEC.md` — the sample/test aircraft (a fixture, not the scope)

## Quick start

```sh
uv run pytest                  # test suite
uv run planeopt objectives     # list the objective library
uv run planeopt run missions/endurance_sample.py -a aircraft/vtail_sample
```

Runs write self-contained artifact directories under `runs/` (run.json +
report.html + an interactive 3D model (`interactive_3d.html`, rotatable in any
browser) + inputs snapshot).

## Status

**M3 (full-vehicle optimization)** — milestones M0-M3 complete:

- M1: fixed-design evaluation (LiftingLine trim, APC-proxy propulsion, printed-mass
  model); validated against real-aircraft bands in `docs/VALIDATION_ANCHORS.md`
- M2: wing NLP (span/chord/taper/cruise state) with multi-start, shadow prices,
  span-flatness sweep
- M3: full vehicle — pitch trim (explicit ruddervator), static-margin window,
  gust margin, continuous spar sizing, ballast/battery-position balance,
  tail arm + tail scale
- M4.5: projected-span manufacturing cap (2.2 m on the sample) + parametric
  winglet (separate surface, length/cant/chords/toe), with a winglet on/off
  study, VLM induced-drag cross-check, and continuous-cant check in the
  champion battery (`docs/MODEL_DETAILS.md` section 3.6)

```sh
uv run planeopt optimize missions/endurance_sample.py -a aircraft/vtail_sample
```

Next: **M4** decision engine (airfoil outer loop, re-solve battery, epsilon-constraint
Pareto sweeps) — see `docs/EXECUTION_PLAN.md` section 6. Construction-profile and
propulsion constants remain uncalibrated: rankings are trustworthy, absolute
minutes are optimistic (see `docs/VALIDATION_ANCHORS.md`).
