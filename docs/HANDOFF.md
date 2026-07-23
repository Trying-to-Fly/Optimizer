# HANDOFF — Plane Optimizer (updated 2026-07-24, end of fifth session)

Orientation for a fresh agent picking up this project. Read this, then
`EXECUTION_PLAN.md` (milestones), `MODEL_DETAILS.md` (per-module equations —
§7 fuselage, §8 tail, §9 wing dihedral family), and `FINDINGS.md` (§9 is the
latest champion).

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
  path. The other ~40 tests are fast (`.venv/bin/python -m pytest -q
  tests/test_configs.py tests/test_winglet.py tests/test_fuselage.py
  tests/test_shapereview.py tests/test_tail.py tests/test_wingcurve.py`).

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

**Fifth session (2026-07-24) — M4.7 done.** Committed and pushed:

- **Generic discrete studies**: `solve.optimize` enumerates any declared
  `discrete_options = {attr: [candidates]}` (fuselage topology + tail type
  both use it; run.json key `discrete_studies`; originals restored in the
  re-eval finally).
- **Tail phase** (MODEL_DETAILS §8): types vtail/conventional/ttail;
  per-dimension vars (t_span/t_c_root/t_taper/t_sweep, t_dihedral or
  fin_*, cs_frac 0.2–0.4); `tail_scale` retired; declared
  `pitch_control_name` threads through trim (no hardcoded "ruddervator");
  throw cap derived from hinge fraction (`trim_deflection_limit_deg` may be
  a callable of dv); declared `v_tail_volume_min = 0.030`; T-tail mount
  mass. Tail AC placed at tail_arm including sweep offset.
- **Wing arch v3** (MODEL_DETAILS §9, user decision): dihedral curve
  δ(η) = dihedral_tip·η^d_exp replaced per-panel d0–d3; straight-spar sag
  fit is a HARD constraint (0.70·t/c usable depth); per-break joiner mass
  deleted; continuous-cant study frees `tip_dihedral_max_deg` (renamed from
  d3_max_deg). CasADi gotcha: never evaluate η^q at η=0 symbolically (NaN
  in the exponent derivative) — z(0)=0 analytically.
- **Champion (run `20260724T052806`, FINDINGS §9): V-tail retained,
  109.3 min @ 2.2 m, AUW 1925 g.** Conventional −5.6, T-tail −8.5, boom
  re-adopted (+4.9), winglet re-rejected (−0.96). Wing converges to
  d_exp = 0 — SIMPLE dihedral (4.1° uniform) wins inside its own family;
  spar-fit inactive at the optimum. Vv floor pulled the V-angle to its 55°
  bound (steep-V handling costs unmodeled — treat the cap as a declared
  practice limit). Balance now via bay stretch (486 mm, battery at 102 mm,
  ballast 0); saddle constraint active (bay end exactly at 60% root chord)
  and visually verified in the three-view. Stall INACTIVE for the first
  time (7.81 vs 8.0) — gust margin sizes the wing. Pod fineness 10.7 is
  outside the shape review's 4–9 band (see FINDINGS §9 note).
- **STEP loader verified for real** (`uv sync --extra cad` done; needed
  `UV_HTTP_TIMEOUT=600`): fixed the station scan (tessellation vertex
  binning collapses on extrusions — now samples triangle-edge crossings at
  station boundaries). `test_step_loader_roundtrip` passes un-skipped.
- Tests: `tests/test_tail.py` (13) + `tests/test_wingcurve.py` (6) added;
  fast suite now `test_configs test_winglet test_fuselage test_shapereview
  test_tail test_wingcurve`. Aircraft is `vtail_sample_v1.4`.
- Known cosmetic gap: three-view/3D artifacts draw only lofted bodies, so
  the CF boom is invisible between pod and tail block.

Fourth-session state (all still true) through `d6f38cf`:

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
- **Wing-saddle carry-through added AFTER the champion run** (user saw the
  wing floating above the shrunken pod — unbuildable): bay start ≤ LE −
  10 mm, bay end ≥ LE + 0.60·c_root (`pod_bay_end` is now a variable, not a
  fixed anchor), pod top derived as `SADDLE_EMBED − h/2` so it always embeds
  6 mm into the wing root plane (MODEL_DETAILS §7.2). **No champion run
  includes these yet** — the 114.1 min figure predates them; expect the next
  run a few minutes lower (the pod must lengthen to carry the wing). Per the
  user: do NOT rerun for this alone — the tail-phase champion run validates
  it.

## 5. Next work

The tail phase (was item A here) and the wing dihedral-curve rework are
DONE — see §4. Remaining, roughly in order of readiness:

- When the user delivers their SolidWorks .STEP: wire the imported-fuselage
  NLP mode — `ImportedShape.body_dict` feeds the existing bodies contract;
  two scale variables (length, cross-section) with Swet/volume fitted smooth
  over a small scale grid (volume scales exactly as sx·syz²; fit Swet);
  scales pinnable to 1. Run the shape review + report both in the run
  artifacts. Note the fineness-band tension first (FINDINGS §9): the
  champion pod is f = 10.7 vs the review's 4–9 band — decide with the user
  whether to widen the band or constrain fineness in the NLP.
- Small items worth folding into any next code session: draw the CF boom in
  the viz twin (cosmetic gap, §4); consider whether the 55° V-angle cap
  deserves a declared handling rationale in DESIGN docs.
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
