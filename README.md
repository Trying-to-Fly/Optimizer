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
uv run planeopt info           # install report: version, packaged data, capabilities
uv run planeopt objectives     # list the objective library
uv run planeopt run missions/endurance_sample.py -a aircraft/vtail_sample
uv run planeopt gui            # desktop app (needs: uv sync --extra gui)
uv run planeopt timelapse <run-dir>   # replay a run's live frames to PNGs/MP4
```

The GUI (M5) browses and compares past runs, edits the mission as a form, and
queues runs with live progress — it reads the same artifacts and shells out to
the same CLI, so anything it does can be done from the command line too.

Runs write self-contained artifact directories under `runs/` (run.json +
report.html + an interactive 3D model (`interactive_3d.html`, rotatable in any
browser) + inputs snapshot).

Long commands print progress to stderr as each solve lands; `--quiet` silences
it. A single NLP solve takes minutes and peaks near 14.5 GB of RAM, and a full
`optimize` battery runs for hours.

RAM is what limits this app, not CPU — a solve uses one core and a lot of
memory. `--memory-budget-gb N` (or "Dedicate memory" in the GUI) says how much
of the machine the app may have, and independent solves within a batch then run
side by side, which is where the wall-clock saving comes from. It does not make
any single solve faster. Runs record their measured peak, so the estimate
improves as you use it; `planeopt info` reports RAM, the measured peak, and the
most concurrency this machine can support. POSIX only — Windows cannot fork,
and says so rather than ignoring the setting.

## Packaged build

`packaging/build_windows.ps1` freezes the app into `dist/planeopt/`
(PyInstaller, onedir), producing two executables: `planeopt.exe` (the console
CLI) and **`planeopt-gui.exe` — double-click this one** to open the desktop
app. The sample `aircraft/` and `missions/` are staged beside them, so a
double-click opens onto a working project; use Run ▸ Open project folder…
(Ctrl+O) to point it elsewhere, and `planeopt info` to see which folder it
resolved. See `packaging/README.md` for what the bundle contains
and its two deliberate limitations: no `--parallel > 1` (Windows has no fork)
and no STEP import (the `cad` extra is ~900 MB). Aircraft and mission inputs
are Python modules in a packaged build too — a form-driven input path is M5.

## Status

**M4.8 complete** — the champion battery co-optimizes wing, fuselage, tail, and
motor mount; see `docs/FINDINGS.md` §10 for the current champion and
`docs/HANDOFF.md` for state and next work. Milestones M0-M3 established:

- M1: fixed-design evaluation (LiftingLine trim, APC-proxy propulsion, printed-mass
  model); validated against real-aircraft bands in `docs/VALIDATION_ANCHORS.md`
- M2: wing NLP (span/chord/taper/cruise state) with multi-start, shadow prices,
  span-flatness sweep
- M3: full vehicle — pitch trim (declared pitch control), static-margin window,
  gust margin, continuous spar sizing, ballast/battery-position balance,
  free tail arm
- M4.5-M4.8: projected-span cap + parametric winglet with an on/off study and
  VLM cross-check; parametric fuselage loft with an emergent boom; tail types;
  the wing dihedral-curve family; motor mount as a priced discrete option.
  Discrete architecture choices are enumerated and priced by studies, never
  assumed (`docs/MODEL_DETAILS.md`, `docs/FINDINGS.md`)
- Wing v4: the planform is one smooth superellipse curve (a rectangular wing
  and a straight taper are exact members of it) with the leading-edge
  convention — straight LE, straight quarter-chord or straight TE — chosen by
  the optimizer as a continuous variable; the dihedral may take a single
  hard-cantable break, priced against the smooth curve by a study
  (`docs/MODEL_DETAILS.md` §9)
- Propulsion v2: propeller coefficients are fitted against advance ratio **and**
  blade Reynolds, `CT(J,Re)`, so there is no RPM window to pick and the model is
  as valid for a 5 in prop as a 22 in one (`docs/MODEL_DETAILS.md` §2.1.1). The
  whole published APC catalogue ships alongside the complete UIUC Propeller Data
  Site — **661 fitted tables**, browsable with `planeopt props` — so diameter and
  pitch are a design choice, not a data limit. 218 of those are wind-tunnel
  *measurement* rather than APC's simulation output, and 71 are folding blades

```sh
uv run planeopt optimize missions/endurance_sample.py -a aircraft/vtail_sample
```

A battery runs for hours and holds ~14.5 GB, so it can be stopped and continued:

```sh
uv run planeopt optimize ... --checkpoint runs/_ckpt --pause-file runs/_ckpt/PAUSE
touch runs/_ckpt/PAUSE     # stops at the next member boundary, frees the memory
# ...re-run the identical command to resume from the checkpoint
```

The pause waits for the solve in flight (bounded by `--solve-timeout-min`)
because IPOPT's internal state cannot be checkpointed — that wait is what makes
it lossless. The GUI exposes the same thing as a Pause button.

### Watching a solve

`--live-dir` makes the run record what it is shaping — the lifting line's own
panel mesh, one small gzip'd JSON per IPOPT iterate and a coloured, fully
annotated one per finished member. The desktop app opens a viewer on it
automatically; a finished run keeps its frames in `<run_dir>/frames/`, so it can
be replayed or re-rendered later.

```sh
uv run planeopt optimize ... --live-dir runs/_live/endurance
uv run planeopt timelapse runs/20260805T120000-endurance_sample-vtail_sample
```

Colours are local section **cl**, **stall margin** (`cl/cl_max` at the local
Reynolds number, on a fixed scale where 1.0 is the section limit — the
constraint the optimizer is actually fighting), circulation **Γ**, or **lift per
span**. There is no Cp and none is faked: the in-loop model is a lifting line
with one chordwise panel, so no chordwise pressure distribution exists. A
chordwise ΔCp from the out-of-loop VLM is possible and designed but not built —
`docs/LIVE_VIEWER_PLAN.md` §11.

Finished members also carry two overlays: **wake streamlines** traced through the
lifting line's own induced-velocity field, which is what makes the tip rollup
visible, and the **spanwise lift distribution** against an elliptical reference
of the same total lift and span.

The camera is chosen in the **New Run dialog before the run starts**, since the
point of a timelapse of a four-hour battery is not having to be there when it
ends. Seven presets — four three-quarter corners and the three elevations — and
the choice travels with the frames into the finished run. The live window can
override it, and so can the command line:

```sh
uv run planeopt timelapse <run-dir> --view plan --lift-dist --scalar stall_margin
uv run planeopt timelapse <run-dir> --yaw -120 --pitch 15 --no-streamlines
```

Iterate frames are geometry-only, because computing circulation *during* a solve
means evaluating it inside the Opti graph — the thing that peaks near 14.5 GB.
Doing it **afterwards** costs a plain numeric lifting line, about 0.2 s a frame,
so a whole run's iterates can be coloured for a couple of minutes of an idle
machine and nothing at all from the solve:

```sh
uv run planeopt recolour <run-dir>                      # pay once, keep the result
uv run planeopt timelapse <run-dir> --colour-iterates   # or just for this render
```

Those numbers are real but **untrimmed** — lift does not equal weight until the
solve says so — and every recoloured frame says so under its stats block.
Recolouring is refused outright if the aircraft's design vector does not match
the frames', so it cannot quietly draw a different aeroplane; a finished run
defaults to its own `inputs/` snapshot.

**M5.1 (desktop GUI)** is in: run browser, detail and compare views, mission
form, a sequential run queue, and the live solve viewer. Aircraft definitions
remain Python modules — a form over them is M5.2 and is the real gate on
non-programmer use.

Next: the imported-fuselage NLP mode for a user-supplied .STEP — see
`docs/HANDOFF.md` section 5. Construction-profile and propulsion
constants remain uncalibrated: rankings and active constraint sets are
trustworthy, absolute minutes are optimistic (see
`docs/VALIDATION_ANCHORS.md`).
