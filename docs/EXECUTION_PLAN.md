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
   shareable), `figures/`, `frames/` (M5.4: the live viewer's gzip'd JSON frames,
   moved here from `runs/_live/` when the run ends — data, not pixels, so a
   better renderer can re-render an old run; M5.5 adds `view.json` beside them,
   the camera this run's timelapse is rendered from), `timelapse/` (once one has
   been rendered), and an `inputs/` snapshot (copies of the aircraft, profile,
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
| **M5.3 — two-stage discrete studies — DONE 2026-08-01** | A discrete study cost one full NLP re-solve per candidate, which capped the shortlist at 8 of 661 shipped tables. `solve.screen_discrete` ranks candidates at the champion's operating point through `propulsion.solve` with no NLP, charges each one's mass delta at the run's own measured shadow price, and hands the optimizer the top N. Opt-in per attribute (`discrete_screen = {attr: n}`), because the screen is only valid where the attribute changes nothing the airframe solve fixed — true of a propeller, false of a tail type | **MET.** 65 candidates ranked in 0.5 s; the screen's first pick is the prop eight full re-solves adopted on the 2026-07-31 battery, priced at 141.56 min against their 141.43. `PROP_CANDIDATES` is now a rule over the catalogue (66 measured folding tables, was 8) — FINDINGS §17 |
| **M5.4 — live solve viewer + timelapse — BUILT 2026-08-05, gate part-met** | An XFLR5-style popup during optimize runs: 3D panel mesh of the current candidate colored by spanwise loading (local cl / Γ / lift-per-span — no Cp exists on a one-chordwise-panel lifting line), monospace stats block, colorbar. Updates every IPOPT iteration (geometry via `Opti` callback + `opti.debug.value`) and every finished member (colored, via a ~0.4 s numeric LiftingLine re-run). Solver writes atomic gzip'd JSON frames to `--live-dir` (`runs/_live/…`, relocated to `<run_dir>/frames/` at completion); GUI watches with `QFileSystemWatcher` **plus a 0.9 s poll**, because `/mnt/c` is a 9p mount where inotify does not fire for another process's writes. Renders with a custom QPainter software projector — no Qt addons, no new deps, no solver imports in the GUI. `planeopt timelapse` replays frames through the same renderer into PNGs/MP4. `liveframe.py` (writer), `gui/render3d.py`, `gui/liveview.py`, `gui/timelapse.py`. Plan, spike results and deviations: `docs/LIVE_VIEWER_PLAN.md` | **PART-MET.** Poisoned writer cannot fail a member and per-iterate frames arrive in order with one candidate per member: test-pinned (`test_liveframe.py`, `test_liveview.py`, 46 tests). Timelapse produces PNGs + the ffmpeg command from a finished run's `frames/`. Verified on a real solve: 21 frames at 3.3 KB, `inf_pr` falling 3.57 → 2.6e-11, and the champion's eight active bounds (span on its cap, a 75 mm winglet at 87.5° against an 88° ceiling — the FINDINGS §18 shape) readable at a glance from the replay. Frames provably do not change the answer: `119.93422` across four solves, delta exactly 0. **NOT met: the overhead percentage, and watching a real battery.** Four timed solves scattered by ~1 minute on a ~5 minute solve in both orderings, which is 10x the effect being looked for, so the end-to-end delta is unresolvable here; the frame work is separately measured at **12 ms per iterate = 0.25 s on a 286 s solve (0.08%)**. See `docs/LIVE_VIEWER_PLAN.md` §9.1 before re-measuring — it needs an idle machine and a discarded warm-up solve |
| **M5.5 — what a frame can show, and from where — BUILT 2026-08-05** | Three more things on a candidate frame, all free of any new aerodynamics: **stall margin** `cl/cl_max(Re_local)` on a fixed 0-1 scale, read from the `clmax_ab_used` fit the solve already made, wing-only (a tail is a different section and gets no borrowed limit); **wake streamlines** through the lifting line's own induced-velocity field, 32x28 against AeroSandbox's 200x100; and the **spanwise lift distribution** against an elliptical reference of equal lift and span. Plus the timelapse **camera chosen in the New Run dialog** before the run starts — seven presets, stored as a `view.json` sidecar that travels with the frames, overridable from the live window and by `planeopt timelapse --view/--yaw/--pitch`. Default view moved from behind the tail to ahead of the nose. `docs/LIVE_VIEWER_PLAN.md` sections 10-12 | **MET.** 385 tests pass (was 350). Verified by writing a real candidate frame from the 2026-08-05 champion and looking at it: stall margin 0.41 at the tips to 0.66 inboard, wing lift 17.85 N against 17.54 N of weight (the V-tail carries the download), wake rolling up at the tips. **0.59 s and 10.4 KB per candidate frame** (3.3 KB before) against member solves of 4-30 minutes; iterate frames untouched at 12 ms. Two defects were found by looking at the renders and not by reasoning — the wake painting over the stats block, and `Camera.basis` collapsing at the `plan` preset's exact pole — both fixed and test-pinned. **ΔCp from the out-of-loop VLM is designed and NOT built** (section 11): it is reachable, it is what XFLR5's VLM view actually shows, and it needs the same ensemble/majority guard `vlm_induced_check` has, because HANDOFF 0a's blow-ups look perfectly physical in isolation |
| **M5.6 — fuselage afterbody drag — Tier 1 BUILT 2026-08-05** | The drag buildup could not see afterbody SHAPE: the whole path from fuselage geometry to the objective was wetted area, length, fineness and volume, so a well-faired body and a badly separated one scored identically — and the champion was exploiting it, running a 20.1° closure half-angle against a 12–15° separation onset with `pod_tail` pinned on the geometric floor that stood in for the missing physics. `fuselage.afterbody_terms` charges separation as an **effective base** (one mechanism, closed-form for the Hermite boat-tail, ramped through onset so IPOPT can walk across it), `aero.body_cd0` adds it outside the excrescence factor, a fineness ceiling ships with it so the exploit cannot move from the tail cone to the whole pod, and the end cap is derived from the boom socket it actually is. Plus, at the user's request, the rows that stop the optimizer shrinking the pod below its own motor. Plan, magnitudes and departures: `docs/FUSELAGE_DRAG_PLAN.md`, MODEL_DETAILS §7.3, HANDOFF. **Section shape unlocked on the back of it** (user decision): `pod_wh` is the width:height ratio, orthogonal to `pod_xs` so `d_eq` — which every proportion floor, the fineness ceiling and the afterbody term are written against — depends on size alone | **PART-MET — the measurement is the next battery.** 386 tests pass (15 new), including the closed-form angle finite-differenced against the real loft, monotonicity in `tail_len`, continuity across onset, and a CasADi grid at iterates outside the box — which found a NaN pole at `r_cap = 1` and a NaN *gradient* where the guard floored a discriminant to exactly zero. At the champion's vector: +34% on body drag, +2.0% on total drag. **NOT met: whether the `1.8·d_eq` floor is now inactive.** It ships untouched for one battery on purpose — with an uncalibrated constant and no floor, the first run's boat-tail would be set entirely by a number nobody has validated |
| **M5.7 — recolour: aerodynamics on the iterates, after the solve — BUILT 2026-08-05** | An iterate frame is geometry-only because reading circulation DURING a solve means evaluating it inside the Opti graph (LIVE_VIEWER_PLAN S2, the 14.5 GB objection). But the candidate frame's colours never came from that graph — they come from a plain NUMERIC `asb.LiftingLine` on floats, and an iterate frame already carries the design vector and the V/alpha/deflection IPOPT was holding. So the same aerodynamics is computable later, offline, from frames on disk. `planeopt recolour <run>` pays once and keeps the result; `planeopt timelapse --colour-iterates` does it in memory for one render. `src/planeopt/recolour.py`; plan sections 13-16 | **MET.** **0.22 s per iterate** (median of 21 real ones, range 0.19-0.50), 4.8 s for a whole 21-iterate run, frames 3.3 KB -> ~12 KB, zero failures. Against ~3% of solver wall time for the same work in the callback, competing with a 13 GB peak and unrepeatable — hence a separate pass, not a flag on `optimize`. Agrees with the solve where checkable: iterate 20 recomputes to CL 0.7759, identical to the candidate frame's. **Two honesty guards, both load-bearing.** Recoloured numbers are UNTRIMMED (iterate 0 reports a real `Cm = -1.35`), so frames carry `recoloured: true` and the stats block gains a caption saying so, with the row reserved by `stats_block_size`. And recolouring with the wrong aircraft would draw a different aeroplane under the run's name, so a design-vector mismatch is REFUSED — which caught a real one on its first invocation, the sample aircraft having gained six variables (32 -> 38) between the run and the recolour; a finished run therefore defaults to its own `inputs/` snapshot. 395 tests pass |
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
