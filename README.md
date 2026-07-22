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
report.html + inputs snapshot).

## Status

**M0 (scaffold)** — configs, objective registry, run/report pipeline, CLI.
No aero/propulsion evaluation yet; next is **M1**, the fixed-design Phase 1
validation gate (see `docs/EXECUTION_PLAN.md` section 6).
