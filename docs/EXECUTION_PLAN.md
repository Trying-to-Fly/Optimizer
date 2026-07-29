# Execution Plan

Companion to `OPTIMIZATION_CONCEPT.md` (idea/formulation) and `MODEL_DETAILS.md`
(module equations). This document covers how the program is actually built: stack,
repository layout, interfaces, run artifacts, milestones, and testing.

Decisions this plan encodes: **Python-module configs** (no YAML schema),
**CLI-first with a GUI later** (library-first architecture, thin CLI), **HTML + JSON
champion reports**, **uv-managed project**.

---

## 1. Stack

| Piece | Choice | Notes |
|---|---|---|
| Language / env | Python 3.12, managed by **uv** (`pyproject.toml` + lockfile) | `uv run planeopt ...` |
| Core | **AeroSandbox** (brings CasADi, NeuralFoil, numpy) | `Opti`, VLM, airfoil tools, `motor_electric_performance` |
| Plots | matplotlib, embedded into HTML as base64 PNG | plotly can replace later for GUI interactivity |
| Report templating | jinja2, single self-contained template | |
| CLI | typer (or argparse if kept minimal) | thin wrapper only — see §3 |
| Tests | pytest | |

The working directory is on `/mnt/c` (Windows filesystem via WSL) — fine for docs,
but the Python project should live on the Linux filesystem or tolerate slow I/O;
decide at scaffold time. Initialize git at scaffold time (`git init` + first commit
of the three docs).

## 2. Repository layout

```
plane-optimizer/
  pyproject.toml
  src/planeopt/
    types.py           # dataclasses: DesignVector, ConstructionProfile, MissionSpec,
                       #   OperatingPointResult, RunResult — the contracts between modules
    geometry.py        # design vector → asb.Airplane via the aircraft's architecture mapping
    massmodel.py       # MODEL_DETAILS §1: printed-surface terms, spar mass, (mass, CG) pairs
    structures.py      # §1.3: spar beam stress/deflection
    propulsion.py      # §2: prop table fits, motor circuit, thrust-match coupling
    aero.py            # §3: VLM + NeuralFoil strips + parasite buildup, trim, NP
    constraints.py     # §4: assembles all equalities/inequalities onto an Opti instance
    mission/           # §5: objective registry; one module per library entry
      endurance.py  range.py  energy_per_km.py  cruise_speed.py  max_speed.py
    solve.py           # §6: builds the NLP, multi-start, discrete outer loop,
                       #   ε-constraint sweeps, re-solve battery
    report/            # champion report: RunResult → run.json → report.html
      assemble.py  html.py  templates/report.html.j2
    data/props/        # fitted CT/CP coefficients — package data, ships with the app
    cli.py             # thin: parse args → library calls → print run dir
  aircraft/            # each aircraft = a package: definition + its construction profiles
    vtail_sample/
      aircraft.py      # the DESIGN_SPEC.md test aircraft
      lwpla_a1.py      # construction profile (calibration constants live here)
  missions/
    endurance_sample.py
  data/props/          # raw APC performance tables + fit-quality plots (source material)
  packaging/           # PyInstaller spec + Windows build script (.exe release)
  tools/               # offline scripts: prop-data ingest, slicer-calibration fitting
  tests/
  runs/                # gitignored; one directory per run
```

**Distribution rule:** anything read at run time lives under `src/planeopt/`.
A path resolved relative to the repo root works in a checkout and vanishes in a
wheel or a frozen build — `tests/test_packaging.py` guards the invariant.

## 3. Architecture rules (the GUI-later insurance)

1. **Library-first.** Every capability is a plain function/class returning dataclasses.
   The CLI contains zero logic — it parses arguments, calls the library, prints the
   run directory path. The M5 desktop GUI (`planeopt.gui`, PySide6) is the second
   thin client this bought: it reads the same run artifacts and launches runs as
   subprocesses of the same CLI, so it owns no solver path of its own. Its Qt-free
   modules (`runindex`, `missionfile`, `jobs`) hold the logic and are tested headless.
2. **Runs are artifacts.** Every run writes `runs/<stamp>-<name>/` containing:
   `run.json` (full machine-readable result: design vector, constraint activity,
   shadow prices, re-solve battery, diagnostics), `report.html` (self-contained,
   shareable), `figures/`, and an `inputs/` snapshot (copies of the aircraft, profile,
   and mission modules used — reproducibility). The GUI later is a browser over
   `runs/`; nothing needs re-architecting.
3. **Configs are code, with one hard rule.** Aircraft definitions and mission specs
   are Python modules building typed objects. Because everything runs inside CasADi's
   symbolic graph, config-supplied expressions must be **symbolic-safe**: no `if` on
   design values, no numpy branching, no non-smooth ops — MODEL_DETAILS §4's
   smoothness rule becomes a documented coding rule for config authors, enforced
   where possible by the types module.

## 4. Key interfaces (sketch level — signatures, not implementations)

- **`AircraftDefinition`** (each `aircraft/*/aircraft.py` provides one):
  - `design_variables(opti) -> DesignVector` — declares variables, bounds, scale
    hints, initial guesses (the sample plane's numbers).
  - `geometry(dv) -> asb.Airplane` — the architecture mapping (e.g. center section +
    tapered outer panels, V-tail at fixed dihedral, control surfaces attached).
  - `fixed_equipment() -> list[(mass, station)]`, `powertrain() -> PowertrainConfig`,
    `construction() -> {surface: ConstructionProfile}`.
- **`MissionSpec`** (each `missions/*.py` provides one): objective name (registry
  key), mission constraint values (stall limit, V_wind + margin, ballast cap, SM
  window), sweep requests (ε-constraint axes), report options.
- **Objective registry** (`mission/__init__.py`): maps name → evaluator
  `(op_point_outputs, energy) -> scalar` plus that objective's wind mode and required
  operating points — MODEL_DETAILS §5.1 as code.
- **`solve.run(aircraft, mission) -> RunResult`** — the one entry point both CLI and
  future GUI call.

CLI surface (initial): `planeopt run missions/endurance_sample.py --aircraft
aircraft/vtail_sample`, `planeopt sweep ...` (ε-constraint axis), `planeopt report
<run-dir>` (re-render HTML from run.json).

## 5. Data pipelines (offline, in `tools/`)

- **Prop ingest:** parse APC published performance files → smooth **CT(J,Re) /
  CP(J,Re)** fit coefficients into `src/planeopt/data/props/` (shipped package
  data, MODEL_DETAILS §2.1). `--fetch` pulls the published archive (~8 MB) and
  fits the **whole catalogue: 443 tables**, so prop diameter and pitch are a
  design choice rather than a data limit; the 67 MB of raw `.dat` stays out of
  git (`data/props/_apc_cache/`, regenerable). `planeopt props` lists/filters
  them. At run time `PLANEOPT_PROPS_DIR` prepends a user directory to the search
  path, so an end user adds a prop without touching the install.
- **Build document** (`report/manufacturing.py`, in-process not offline): every run
  writes `manufacturing/BUILD.md` plus `edges.csv`, `hinges.csv`, `surfaces.csv`
  and a CSV per tabular section. `report.html` says whether the design is good,
  `design_brief.md` says what to design around, this says **what to cut and what
  to hit** — spar stock and lengths with their as-built margins, hinge lines,
  LE/TE polylines, the mass budget and the CG window. Generic content is read off
  the analysed `asb.Airplane`; anything architecture-specific comes from the
  aircraft's optional `manufacturing(dv, auw_kg=None)` hook, whose list-valued
  sections become tables and CSVs automatically. Regenerate with `planeopt build`.
- **Construction-profile fitting:** takes slicer results for the 2–3 scaled sections
  (MODEL_DETAILS §1.4), regresses `k_skin`/`k_rib`/`k_joint`, and writes/updates the
  profile module with fitted values + fit metadata.

## 6. Milestones (mapping the concept doc's phasing onto code)

| Milestone | Delivers | Gate |
|---|---|---|
| **M0 — scaffold** | uv project, git init, types, sample aircraft/mission modules import cleanly, empty-report pipeline runs end-to-end | `planeopt run` produces a (trivial) run dir |
| **M1 — Phase 1 gate** | Fixed-design evaluation: geometry → mass/CG → aero (trimmed) → propulsion, full champion report, **no optimizer** | Sample plane lands inside plausibility bands built from real comparable aircraft (`VALIDATION_ANCHORS.md`); spec figures are weak priors only — MODEL_DETAILS §6.5 |
| **M2 — wing opt** | Endurance-mission NLP: span/chord/taper/speed free, mass closure, stall + min-speed + Re + manufacturing constraints, multi-start | Converges from perturbed starts to the same champion; shadow prices reported |
| **M3 — full vehicle** | Tail sizing, CG/ballast/battery-position, static margin, explicit-deflection trim, continuous spar sizing + structure constraints | Full §4 constraint set active-set report is sane |
| **M4 — decision engine** | Discrete airfoil outer loop, re-solve battery (mass ±10%, η ±10%, tripped polars), flatness sweep, ε-constraint Pareto sweeps, weighted-sum quick look | Complete champion report per MODEL_DETAILS §6.4 |
| **M4.5 — winglet + span cap** | Projected-span cap (arc-length panels, `b_ref` = projected span), explicit winglet surface (separate Wing, 5 vars), winglet on/off study + VLM induced check + continuous-cant cross-check in the champion battery (MODEL_DETAILS §3.6) | Champion respects the manufacturing cap; winglet kept only if it pays through the paired study |
| **M4.6 — fuselage loft** | Parametric superellipse pod loft (lengths + cross-section vars, loft's own integrals feed drag/Munk/mass), symbolic packaging constraints from declared component envelopes, pod-boom vs integrated topology study in the champion battery (MODEL_DETAILS §7) | `dv=None` fixture keeps the frozen M1 numbers; defaults reproduce the spec pod; topology adopted only if its full re-optimization wins |
| **M4.7 — tail + wing family** | Generic declared discrete-study loop (`discrete_options`); tail types (V / conventional / T) with per-dimension variables (`tail_scale` retired), declared pitch-control name, derived throw-limit policy, vertical-tail-volume floor, T-tail mount mass (MODEL_DETAILS §8); wing dihedral curve family replacing per-panel dihedrals, straight-spar fit constraint (§9) | Fast per-type tests (geometry contract, mass mapping, Vv math, symbolics); one champion run prices tail types and validates the wing-saddle + curve constraints |
| **M4.8 — span 2.0 + motor mount** | Projected-span cap lowered to 2.0 m; pusher/puller as declared discrete candidates — exact motor-mass placement plus declared installation factors (pusher prop-in-wake derate, puller pod-scrubbing drag; MODEL_DETAILS §2.4), study ordered first (biggest CG lever) | Champion battery prices the mount at the 2.0 m cap; rankings comparable within-run (absolute minutes drop ~5% vs pre-derate runs) |
| **M5.1 — desktop GUI** | Native desktop app (PySide6, `planeopt gui`): browse `runs/`, run detail, multi-run compare, a form over the mission, and a sequential run queue with live progress and cancel. Web UI was the original sketch; a desktop app was chosen instead (user decision 2026-07-25) | Reads run.json only for browsing; runs execute as subprocesses of the same CLI, so the GUI adds no solver path of its own |
| **M4.9 — wing v4 + RAM budget** | Wing planform as one smooth superellipse chord curve (`taper`, `fullness`) replacing the three chord ratios and their equal-width panels, LE convention as one continuous variable (`le_shear`: straight LE / straight c/4 / straight TE), free joint station (`eta_break`, inheriting `center_width`'s freedom), true area-weighted AC placement, and a `wing_dihedral_form: [curve, polyhedral2]` study with the outer panel cantable to 60° and its joiner block charged (MODEL_DETAILS §9). Plus `--memory-budget-gb` / GUI "Dedicate memory": measured per-solve peak RSS recorded per run and divided into a declared budget to set the concurrency width (`memory.py`) | A rectangular wing and a straight taper are EXACT members of the family; `dv=None` fixture reproduces 91.48 min / 1933 g unchanged; NaN-free Jacobian across a 384-corner bound sweep in both dihedral forms; one champion battery prices the kink |
| **M5.2 — aircraft input (later)** | Form over the aircraft's *declaration* surface (hardware, span cap, tail type, bounds, discrete options). Needs a declarative data layer beneath `aircraft.py`, which is the real gate on non-programmer use — see §3 rule 3 | The sample aircraft round-trips through the data layer with identical champion numbers |
| **M5.3 — two-stage discrete studies (next, user ask 2026-07-29)** | A discrete study costs one full NLP re-solve per candidate, which caps a shortlist at a handful — so the prop study priced 3 of the 443 shipped tables and adopted a prop that screens **119th of 441** (FINDINGS §12). Fix the cost, not the shortlist: **screen** every candidate cheaply through the existing evaluation path at the incumbent's operating point (`propulsion.solve`, seconds, no NLP), then full-re-solve only the top N plus the incumbent. Generic over `discrete_options`, so any attribute with a large candidate set benefits, not just props | The prop study searches the whole catalogue and still costs ~5 solves; the screen's top-N contains the eventual champion on a re-run of the 2026-07-29 battery |
| **M6 — powertrain as a design variable (later, user request 2026-07-28)** | Motor and battery become **priced candidates** rather than declared constants, the same way the prop became a discrete study on 2026-07-27. Motor: a candidate list of (Kv, R, I0, mass, can size) re-solved per member — Kv especially, since it sets the rpm the prop is asked to turn and therefore trades directly against pitch, so motor and prop want to be judged *jointly*, not in sequence. Battery: cell count (bus voltage), capacity and mass as a continuous or discrete family, which couples straight into the endurance objective (`E_usable`) and into CG through the battery-position variable that already exists | A battery/motor study reproduces the current hardware exactly when its candidate list is a single member; joint motor+prop study beats sequential selection on the sample plane, or is shown not to |

**Not scheduled on purpose.** M6 is deferred at the user's request (2026-07-28):
the motor and battery are hardware already on hand, so treating them as fixed is
the correct model of the actual decision today. The note exists so that when the
hardware is genuinely open, the coupling above is not rediscovered from scratch.

Each milestone is independently useful, matching the concept doc's "stop whenever the
payoff stops" posture.

## 7. Testing

- **Unit, per module:** mass model reproduces hand-computed term values; prop fits
  match raw table points within tolerance; motor circuit against datasheet points;
  trim residual → 0 on a symmetric case; NP position sane vs. textbook approximation
  for a simple wing+tail.
- **Integration:** M1's Phase-1 gate encoded as a pytest with tolerance bands — it is
  both the scientific validation and the regression net.
- **Golden runs:** a small `run.json` snapshot diffed on CI-less local test runs to
  catch silent numerical drift (tolerance-aware comparison, not byte equality).
- **Symbolic-safety:** a test that builds every shipped config through `Opti`
  symbolically — catches accidental numpy branching in config code immediately.
