# HANDOFF — Plane Optimizer (written 2026-07-23, end of fourth session)

Orientation for a fresh agent picking up this project. Read this, then
`EXECUTION_PLAN.md` (milestones), `MODEL_DETAILS.md` (per-module equations —
§7 is the fuselage), and `FINDINGS.md` (§8 is the latest champion).

## 1. What this project is

General-purpose small-aircraft MDO app (AeroSandbox/IPOPT): co-optimize
geometry, mass, trim for mission-declared objectives. **Iron rule: the app is
general-purpose.** `aircraft/vtail_sample/` and `DESIGN_SPEC.md` are ONE test
fixture — nothing in `src/planeopt/` may assume its architecture, numbers, or
mission. New features enter as framework hooks + aircraft-declared data.

- Repo: `/mnt/c/Users/M0obo/Desktop/Planes/Plane Optimizer` (Windows mount —
  moved from ~/plane-optimizer at user request; that location is deleted).
- Remote: `https://github.com/Trying-to-Fly/Optimizer.git` (origin/main;
  push after every committed unit).
- `docs/` is canonical. `runs/` is gitignored artifacts.

## 2. Environment hazards (each one has already burned a session)

- **RAM:** one NLP solve peaks ~13 GB of WSL's 15 GB. NEVER run two heavy
  jobs (NLP solve, pytest suite) concurrently — the WSL OOM killer takes the
  whole session down. One heavy background job at a time.
- **uv lock:** `uv run` hangs silently (futex on `.venv/.lock`) when two uv
  invocations overlap on this drvfs mount. Launch background runs with
  `.venv/bin/planeopt` / `.venv/bin/python` directly; while ANY background
  run is alive, never issue a `uv` command (use `.venv/bin/python -m pytest`).
- **Kills:** stop background tasks only via the harness (TaskStop), never
  pkill/group kills.
- **Timing on /mnt/c:** one NLP solve ~5–6 min; full champion battery
  ~100 min; `tests/test_run.py::test_m3_optimize_smoke` runs optimize() and
  cannot finish in 30 min — don't wait on it; the champion run covers that
  path. The other 15+ tests are fast (`.venv/bin/python -m pytest -q
  tests/test_configs.py tests/test_winglet.py tests/test_fuselage.py
  tests/test_shapereview.py`).

## 3. How the user works (important)

Decisions are the user's. Map open modeling/design decisions, present
concrete options with trade-offs and one recommendation (AskUserQuestion
works well), get their call, THEN write docs and code to match. They answer
tersely and expect docs updated. Don't ask about things derivable from the
docs. They care that results look/are buildable (they rejected a boxy
fuselage on sight) and repeatedly stress: nothing arbitrary "fixed in stone" —
lengths, tails, booms are optimizable or enumerable; only genuine discrete
choices (tail type, topology) stay discrete, and even those get priced by
studies rather than assumed.

## 4. State as of this handoff

All committed and pushed through `d6f38cf`:

- **M0–M4.6 done.** M4.5 = projected-span cap (2.2 m) + winglet w/
  three-route on/off study (FINDINGS §7). M4.6 = fuselage phase: streamlined
  parametric loft (elliptical nose, Hermite boat-tail, proportion floors
  nose ≥ 1.0 d_eq / boat-tail ≥ 1.8 d_eq), packaging constraints from
  declared component envelopes, emergent boom (pod tail cap → tail block;
  mass + drag from that length), tail_arm freed to 0.40–1.20, topology study
  over a declared list (`fuselage_topologies`).
- **Champion (run `20260723T181336`, FINDINGS §8): 114.1 min @ 2.2 m** —
  fuselage freedom recovered the whole span-cap penalty. Pod pinned at every
  floor (54×70 mm section, nose 61 / bay 310 / boat-tail 111 mm, 482 mm).
  **CF boom adopted (+8.9 min over integrated).** Winglet re-rejected
  (−0.50 min). Multistart spread ~1e-9; NLP-vs-reeval gap ~1e-5.
  tail_arm 519 mm (old 0.55 bound had been binding); tail_scale pinned at
  its 0.70 floor → the tail parameterization is now the binding limitation.
- **CAD round-trip built** (MODEL_DETAILS §7.5): `planeopt brief <run> -a
  <aircraft>` renders `design_brief.md` (declared-data hook
  `design_brief(dv, shadow_per_g)`); `planeopt.cadimport.load_step` (.STEP,
  optional `cad` extra = cadquery, NOT yet installed); `planeopt.shapereview`
  rule checks (nose ≥ 1.0 d_eq, boat-tail ≤ 21°, fineness 4–9, Swet delta
  priced). Loft = recommendation engine; imported STEP = real design.
- Fuselage previews: `runs/fuselage_preview/interactive_3d.html` (champion
  pod + battery) and the run dir's `interactive_3d.html` (full aircraft).
  User had NOT yet confirmed the new shape passes their eyeball test.

## 5. Next work, in order

### A. Tail phase (user's decisions already given — do not re-ask)

Types **V-tail + conventional + T-tail**, declared list, enumerated like
fuselage topologies. Within a type free: tail span, root chord, taper,
**sweep**, V-/fin angle. Control surfaces: **hinge/chord fraction free
(~0.2–0.4); throw limit stays policy** (⅓ of available throw), no
servo-torque model. Retire the single `tail_scale` knob for per-dimension
variables. Only tail TYPE stays discrete.

Implementation notes scoped so far:
1. Generalize the discrete-study loop in `solve.optimize` (currently
   fuselage-only) into a generic mechanism over declared attrs, e.g.
   `discrete_options = {"fuselage_topology": [...], "tail_type": [...]}` —
   one full re-optimization per alternative, winner adopted, all priced in
   run.json. Keep restore-after-re-eval semantics (see current topology
   block).
2. Add a declared **vertical-tail-volume floor**: LL has no yaw axis, so
   without it conventional fins optimize to zero and V-tails shed angle.
   V-tail effective vertical area ≈ S_tail · sin²(Γ). Floor value is
   aircraft-declared data.
3. T-tail: declared fin structural mass penalty (stab-on-fin mount).
4. Before coding, READ: how `_solve_nlp` does symbolic explicit-deflection
   trim, and how `massmodel.build` maps `construction()` profiles to wing
   names — tail generators must produce consistent wing names + profiles per
   type. The pitch-trim control-surface name is currently hardcoded
   "ruddervator" in `aero._run_ll` — make it declared (e.g.
   `aircraft.pitch_control_name`) when adding conventional/T (surface
   "elevator").
5. After implementing: fast tests per type (geometry contract, mass mapping,
   v-volume floor math), then ONE champion run (background, venv binary,
   ~2 h+ with the tail-type study added), FINDINGS §9, commit, push.

### B. Gated / pending items

- `uv sync --extra cad` (installs cadquery) — run when NO background job is
  alive, then `tests/test_shapereview.py::test_step_loader_roundtrip`
  un-skips; verify it passes (the loader is written but never executed).
- When the user delivers their SolidWorks .STEP: wire the imported-fuselage
  NLP mode — `ImportedShape.body_dict` feeds the existing bodies contract;
  two scale variables (length, cross-section) with Swet/volume fitted smooth
  over a small scale grid (volume scales exactly as sx·syz²; fit Swet);
  scales pinnable to 1. Run the shape review + report both in the run
  artifacts.
- Optional warm-start flag (`--warm-start <run dir>` reading champion dv as
  inits) — only worth it for speed; multistart agreement is already perfect.
- Queued far-field: XFOIL spot-check AG35 vs SD7037 (FINDINGS §6), user
  slicing parts → `tools/fit_profile.py` mass calibration, M5 GUI.

## 6. Known gaps / caveats to carry forward

- VLM winglet cross-check degenerated at the high-dihedral champion
  (negative inviscid CD0, e_proj > 1) — the 3-point quadratic fit needs more
  alphas or a better regressor before it's quantitative again.
- All absolute minutes are uncalibrated (construction + propulsion);
  rankings and active constraint sets are the trustworthy outputs.
- Chain efficiency ±10% swings the objective ±10 min — dominant uncertainty.
- `structure_extras`/`fixed_equipment` in the sample still carry a few spec
  station constants (servo positions etc.) — fine for the fixture, but keep
  them out of framework code.
- Session memory files exist under the Claude project dir and mirror much of
  this; this file is the canonical handoff.
