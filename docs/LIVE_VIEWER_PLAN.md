# M5.4 — Live solve viewer + timelapse (plan, 2026-08-05)

> **IMPLEMENTED 2026-08-05.** `src/planeopt/liveframe.py` (writer, Qt-free),
> `gui/render3d.py` (software 3D), `gui/liveview.py` (the popup),
> `gui/timelapse.py` + `planeopt timelapse` (export), `--live-dir` on
> `planeopt optimize`, wired through `gui/jobs.py`, `gui/newrun.py`,
> `gui/runner.py` and `gui/window.py`. Tests in `tests/test_liveframe.py` and
> `tests/test_liveview.py`. **Section 1's spike was run before coding and its
> results are recorded there; sections 3 and 4.2 record where the built thing
> deviates from this plan and why.** Read those notes before changing anything —
> two of them exist because the plan as written had a bug in it.
>
> **M5.5 is the second half of this file (sections 10-12), added 2026-08-05:**
> stall-margin colouring, wake streamlines and the lift distribution (built),
> ΔCp from the out-of-loop VLM (designed, not built — section 11 is the real
> answer to "show me pressure like XFLR5"), and choosing the timelapse view
> before the run starts.
>
> **M5.7 is the third part (sections 13-16), added 2026-08-05:** `recolour`,
> which computes an iterate's aerodynamics AFTER the solve so every frame of a
> timelapse can be coloured. Section 13 explains why that does not contradict
> S2's refusal — the objection was about *when*, and the candidate frame's
> aerodynamics never touched the Opti graph in the first place.

A popup window that shows the aircraft the optimizer is currently shaping —
XFLR5-style: dark background, 3D surfaces colored by spanwise loading, a
monospace stats block, a colorbar — updating **every IPOPT iteration**
(geometry) and **every finished candidate** (colored + full stats). Every frame
is persisted so a finished run can be replayed as a timelapse.

Two purposes, in priority order: **debugging** (seeing the solver wander
through infeasible geometry is diagnostic — a 52 mm winglet canted 86° would
have been visible in seconds, not found in a post-mortem; FINDINGS §18) and
**timelapse export** of full runs.

User decisions already taken (2026-08-05, all four were the recommended option):

| decision | choice |
|---|---|
| cadence | **both** — per-iteration geometry + per-candidate colored frame |
| renderer | **custom QPainter software 3D** (no Qt addons, no OpenGL, no new deps) |
| persistence | **JSON frames**, timelapse rendered on demand from them |
| window | **auto-open popup** when a run starts; closable without affecting the run |

## 0. Constraints that shape everything (read before coding)

1. **The GUI must not grow a solver path.** EXECUTION_PLAN §3: the GUI reads
   artifacts and spawns subprocesses; it must never import `aerosandbox`,
   CasADi, or an aircraft module. Therefore **frames carry the mesh**, already
   computed, and the viewer is a dumb renderer. This also keeps the ~14.5 GB /
   possibly-OOM-killed solve crash-isolated (rationale in `gui/jobs.py:1-8`).
2. **A viz failure must never fail a solve.** Every solver-side viz call is
   wrapped; on the first exception it logs one WARNING and disables itself for
   the rest of the run. Pinned by a test that injects a failing writer.
3. **No Cp exists and none can be faked.** The in-loop model is a lifting line
   with a single chordwise panel (`chordwise_resolution=1` — see AeroSandbox
   `lifting_line.py`), so there is no chordwise pressure distribution. The
   honest scalars are per-strip: local section **cl** (default — stall-relevant),
   circulation **Γ**, **lift per span**, and (M5.5) **stall margin**. Do not
   label anything "Cp". A chordwise ΔCp from the OUT-of-loop VLM is a different
   thing and is designed in §11; it may never enter the iterate path.
4. **The run directory does not exist until the run ends**
   (`report/assemble.py:20`, `write_run_dir`). Live frames therefore go to a
   GUI-chosen directory under `runs/_live/`, and are moved into
   `<run_dir>/frames/` when the run completes (§5).
5. **Qt addons stay excluded** (`pyproject.toml` comment): no Qt3D, no
   QtCharts, no QtOpenGLWidgets. QPainter + QImage only. This also makes the
   headless timelapse renderer trivial (`QT_QPA_PLATFORM=offscreen`).
6. **Iterates are frequently infeasible** — negative chords, negative boom
   lengths (`solve.py` `detect_simple_bounds` note, `geometry.smooth_floor`).
   `aircraft.geometry(dv)` on garbage floats must be tried and skipped on
   exception, never trusted to succeed.

## 1. Spike first (half a day, gates the iterate-frame design)

On the nominal solve (`Optimal Solution Found` in ~16 iterations / ~2 min,
HANDOFF issue 1), using `asb.Opti.solve(callback=...)`
(AeroSandbox `optimization/opti.py`, `callback: Callable[[int], Any]`):

- **S1.** Measure the cost of reading the design vector per iterate:
  `opti.debug.value(expr)` for each of the ~33 dv entries, or one stacked
  vector if cheaper. Target: **< 2% added wall time** on the nominal solve.
- **S2.** Try reading the lifting line's `vortex_strengths` the same way (they
  are implicit variables in the same Opti). If it works and is cheap,
  **iterate frames get live Γ coloring**; if not, iterate frames are
  geometry-only (flat fill + wireframe) and coloring appears only on candidate
  frames. Either outcome is fine; record which in this file when known.
- **S3.** Measure `aircraft.geometry(dv)` + `mesh_thin_surface` on plain floats
  (expected ~10–50 ms) and confirm it inside the callback doesn't disturb
  IPOPT (it shouldn't — the callback is between iterations).

If S1 fails the 2% target, throttle: write an iterate frame at most every N
iterations or T seconds (config constants, not CLI flags). Iterations on this
model take ~1.5 s on average (200 iters / 5 min), so per-iteration is the
expected outcome.

### 1.1 Spike results (measured 2026-08-05, before any of this was built)

**S1 — reading the design vector: 0.12 ms per iterate, and the "or one stacked
vector" was the whole question.** `opti.debug.value` builds a CasADi `Function`
per call, so 37 separate calls per iterate is 37 graph traversals; one
`cas.vertcat` of the dv symbols plus the four operating-point variables is a
single traversal over leaf nodes. First call 1.75 ms (building), steady state
0.12 ms. No throttle is needed and none was built.

**S2 — `vortex_strengths` was NOT attempted, and should not be.** The reasoning
that replaced the measurement: circulation is not a leaf of the Opti, it is deep
inside the aerodynamic graph, so `opti.debug.value` on it would build a Function
over the graph that makes a solve peak near 14.5 GB — once per iteration.
**Iterate frames are therefore geometry-only** (shaded fill + fuselage
wireframe) and every colour comes from candidate frames. This is the second
outcome the plan allowed for.

But the spike found something the plan did not expect, which pays for most of
what S2 would have bought: **`opti.debug.stats()` works DURING the solve**, and
its `iterations` dict already carries IPOPT's own `obj`, `inf_pr`, `inf_du`,
`mu` and `d_norm`. That is 0.08 ms of dict lookup for the numbers the plan
wanted most — watching primal infeasibility fall — with no graph evaluation at
all. `solve._IPOPT_ITERATION_FIELDS` is that list. It is also why the stats
block labels it "IPOPT obj*" with a footnote: it is the value of
`Objective.nlp_expression`, the monotone surrogate IPOPT minimizes, not the
reported objective in minutes.

**S3 — 12 ms per iterate frame, all in.** On the sample aircraft:
`aircraft.geometry(dv)` 7.1 ms, `mesh_of` (subdivide + `mesh_thin_surface`)
2.8 ms, `geometry.summarize` 2.3 ms. Against ~1.5 s iterations that is ~0.8%.

The one measurement that changed a decision: `outlines_of` (the fuselage/boom
wireframe) cost **11.4 ms** sampling ring points one at a time, which would have
doubled the per-iterate budget for decoration. Vectorising the ring —
`get_3D_coordinates(theta=array)`, one call per station instead of sixteen —
brought it under a millisecond, so **iterate frames carry the fuselage too**.
Worth it: `tail_arm` is a design variable, so watching the boom stretch is one
of the things this view exists to show, and a tail floating detached from the
wing is not a readable aeroplane.

**Still to measure: the end-to-end overhead against a real battery.** The
arithmetic above says ~1%, and the frame-writing path is the same one the tests
exercise, but the gate in section 9 is a measured number on a real run and this
is not it.

## 2. Frame files

### 2.1 Location and naming

- Live dir: `runs/_live/<job-stamp>-<mission>/` — created by the GUI (or by
  hand for CLI runs) and passed as **`--live-dir DIR`** on
  `planeopt optimize` (mirroring `--checkpoint`; wire in `cli.py` beside it,
  thread through `solve.optimize` → `_solve_many` → `_solve_nlp`).
- One file per frame: `f<seq:06d>__<label>__<key>__i<iter:04d>.json.gz`
  (candidate frames use `__final` in place of the iter part). `seq` is a
  global monotone counter, initialized to `max(existing)+1` on start so a
  paused-and-resumed battery keeps appending in order. Lexicographic sort of
  filenames == chronological order; that is the timelapse's ordering contract.
- **Write atomically**: tmp file in the same dir, then `os.replace` — same
  idiom as `_SolveCache.put` (`solve.py:146-157`). The GUI watcher must never
  see a half-written file.
- Format: gzip'd JSON (`gzip.open(..., "wt")`). With coordinates rounded to
  0.1 mm a frame is ~5–15 KB; a worst-case 5,000-iteration battery is
  ~25–75 MB. Backstop: after `MAX_ITERATE_FRAMES = 20_000` frames, stop
  writing iterate frames (log one line saying so); candidate frames always
  write.

### 2.2 Schema (`"schema": 1` in every frame; viewer ignores unknown fields)

```jsonc
{
  "schema": 1,
  "kind": "iterate",              // or "candidate"
  "label": "multistart",          // batch label, as in checkpoints
  "key": "nominal",               // member key
  "member_index": [2, 24],        // n of total, for the header line
  "iter": 42,                     // IPOPT iteration (iterate frames only)
  "t_member_s": 63.2,             // wall time since member start
  "dv": {"span": 2.0, ...},       // full named design vector (floats)
  "mesh": {
    "quads": [...],               // flat int array, len = 12*nquads,
                                  // units 0.1 mm: x0 y0 z0 x1 y1 z1 ... per quad
    "surface_of": [...],          // per-quad surface id (0 wing, 1 tail, ...)
    "surfaces": ["wing", "tail", "winglet"],
    "outlines": [...]             // optional: fuselage/boom loft silhouettes,
                                  // list of flat int polylines (candidate frames;
                                  // reuse the viz-twin lofts, solve.py:585-598)
  },
  "color": {                      // present when a scalar is available
    "name": "cl",                 // "cl" | "gamma" | "lift_per_span"
    "values": [...],              // per-quad floats
    "all": {"gamma": [...], "lift_per_span": [...]}  // candidate frames carry
                                  // all three so the viewer dropdown is free
  },
  "scalars": {                    // iterate frames: whatever is cheap —
    "objective": 118.2, "inf_pr": 5.6,
    // candidate frames: the full stats block, see §4.2
  }
}
```

Mesh quads come from the same source the solver meshes with —
`wing.mesh_thin_surface(method="quad")` per surface on the rebuilt
`asb.Airplane` — so what you watch is what the lifting line saw (spanwise
strips, one chordwise panel). Symmetric surfaces: mesh both sides (mirror y),
because the viewer should show the whole aeroplane like the screenshot.

## 3. Solver side — `src/planeopt/liveframe.py` (new, Qt-free)

One class, `FrameWriter(live_dir)`, holding the counter and the disable-on-
first-error latch. Public surface:

- `iterate(label, key, member_index, iter_n, dv_floats, gamma_or_none, t0)` —
  rebuild geometry, mesh, write frame. Skips silently (debug-level log) if
  `aircraft.geometry(dv)` raises on an infeasible iterate.
- `candidate(label, key, member_index, result, aircraft, t0)` — rebuild the
  airplane from `result["dv"]`, run one **numeric** `asb.LiftingLine` at the
  converged operating point (`V_ms, alpha_deg, deflection_deg, x_cg_m` are all
  in the result dict) to get per-strip Γ / cl / lift and CL, CD, Cm, e; call
  `geometry.summarize` for the planform stats; write the frame. ~1–2 s per
  member against 4–30 min solves.
- Everything above inside the try/except-disable wrapper (constraint 0.2).

Hook points:

- **Iterate**: in `_solve_nlp` (`solve.py:850-861`), pass
  `callback=lambda i: writer.iterate(...)` into `opti.solve(...)` when a
  writer is present. Reads via `opti.debug.value(...)` per the spike.
- **Candidate**: in `_solve_many`, right where a finished member already gets
  `_log_result` + `cache.put` (`solve.py:1099-1106`).
- **Forked-parallel path** (`--parallel > 1`, `solve.py:1114-1149`): workers
  own their solves, so each worker constructs its own `FrameWriter` (same dir
  — filenames are member-tagged and the seq counter can collide across
  processes, so in forked mode prefix seq with the member key ordinal, or use
  `os.getpid()` in the tmp name and take the counter from a scan; keep it
  simple, collisions only affect ordering granularity, and candidate frames
  written by the parent keep authoritative ordering). The parent writes the
  candidate frame (it holds the unpicklable aircraft object).

> **DEVIATION (2026-08-05): the WORKER writes its candidate frame, not the
> parent, and the sequential path writes it BEFORE `restore()`.**
>
> The plan's last sentence is a bug. `_solve_many` brackets each member with
> `prep(key)` / `restore()` so that a discrete study's candidate carries its own
> attribute — a prop, a tail type, a winglet. `restore()` runs the moment the
> member is handed off, so a candidate frame drawn afterwards would render the
> BASELINE aeroplane under the candidate's name. It would converge, look
> perfect, and be a picture of a different aircraft: the same failure shape as
> the 2026-08-05 flatness curve that characterised a superseded design.
>
> A forked worker inherits the attributes at fork and keeps them for its whole
> life, so it can always draw its own member correctly; the parent cannot.
> Pinned by `test_a_studys_candidate_frame_is_drawn_before_the_attribute_is_restored`.
>
> One more ordering rule fell out of it: `solve_minutes` is stamped BEFORE the
> candidate frame is built, because that frame runs its own lifting line and
> the run artifact's phase-minutes breakdown must not be charged for it
> (`test_the_candidate_frame_is_not_charged_to_the_solve`).
>
> Filenames need no pid: `f<seq>__<label>__<key>__<tail>` already carries the
> member, so two workers at the same seq write different names and neither
> clobbers the other. Only the global interleaving between members is coarse in
> forked mode, which is what the plan accepted.

CLI: `--live-dir` on `optimize` only. `run` (fixed-design) doesn't need it —
there is no iteration to watch; the existing `interactive_3d.html` covers it.

## 4. GUI side

### 4.1 Renderer — `src/planeopt/gui/render3d.py` (Qt only, no numpy needed)

Small, deliberate, ~300 lines:

- Camera: yaw/pitch orbit around the model centroid + zoom + pan, weak
  perspective (or orthographic — pick one, orthographic matches XFLR5 and
  makes depth-sort artifacts rarer). Default view ≈ the screenshot: from
  front-left-above (yaw ≈ −35°, pitch ≈ +25°).
- Painter's algorithm: sort quads by view-space centroid depth, far to near;
  fill `QPolygonF` with the colormap color; stroke edges 1 px in a darker
  shade of the fill (that's what gives the XFLR5 paneled look). Antialiasing
  on. ~300 quads → well under a millisecond of sorting; redraw budget is
  effectively the fill rate, fine at any window size.
- Colormap: a hardcoded 256-entry **turbo** LUT (perceptually ordered but
  reads like the classic rainbow, honoring the reference image). Color range:
  fixed per member (from the first frames' min/max, expanding never shrinking)
  so a timelapse doesn't flicker; a candidate frame re-anchors it.
- The renderer draws onto any `QPainter` — the widget hands it its own, the
  timelapse tool hands it a `QImage`'s. **One code path for both.** No
  Qt-widget state inside the renderer.

### 4.2 Window — `src/planeopt/gui/liveview.py`

`LiveViewWindow(QWidget)`, dark background matching the existing stylesheet
(`window.py:69-126`), laid out like the screenshot:

- 3D view fills the window; colorbar with numeric labels on the right;
  **stats block bottom-left, monospace**, two columns:
  - geometry (from `dv` + `summarize` in the frame): aircraft name + version,
    wing span, wing area, AUW, wing loading, tail volume(s), root chord, MAC,
    taper ratio, aspect ratio, twist at tip, LE shear, winglet length/cant if
    present;
  - state (from `scalars`): member `label [n/total] key`, IPOPT iter, V,
    alpha, CL, CD, L/D, oswald e, Cm, static margin, throttle %, P_elec,
    objective (min), and on iterate frames `inf_pr` — watching primal
    infeasibility fall is half the debugging value.
  - Iterate frames missing a value render `—`, never a stale number from the
    previous candidate.
- Header row: scalar dropdown (cl / Γ / lift per span), "follow latest"
  toggle (on by default; off freezes on the current frame and enables a frame
  slider for scrubbing what's on disk), camera reset, "Render timelapse…"
  button (§6).
- Mouse: left-drag rotate, wheel zoom, middle/shift-drag pan, double-click
  reset.
- **Watching**: `QFileSystemWatcher` on the job's live dir; on
  `directoryChanged`, scan for filenames > last seen seq, load only the
  **newest** (the rest are already safely on disk for scrubbing/timelapse).
  Loading = `gzip` + `json` on a few tens of KB — do it on the GUI thread,
  it's sub-millisecond; no worker threads.
- Multiple concurrent members (forked mode): "follow latest" shows whichever
  member wrote last; the header always names the member so it can't be
  misread.

> **DEVIATIONS (2026-08-05), all found by looking at the rendered result:**
>
> - **The frame slider is never disabled.** The plan gated it behind "follow
>   latest" being off. A permanently-greyed slider under a live run reads as a
>   broken progress bar, and it makes scrubbing a two-step gesture. Dragging it
>   IS the request to stop following; the checkbox reports the mode rather than
>   gating the control.
> - **The colorbar persists on uncoloured frames, faded and captioned "last
>   candidate".** Drawing it only when the current frame has values made the
>   whole right-hand side of the window blink as the run alternated between
>   iterates and candidates. Its strip is reserved from the first valid range
>   onward for the same reason — otherwise the model resized once per member,
>   which in a timelapse reads as the aeroplane pulsing.
> - **The camera fit is a bounding BOX, not a bounding sphere, and it is
>   projected with the current camera.** A sphere fitted to a 1.9 m span leaves
>   a 0.2 m tall aeroplane occupying a tenth of the window. The box still only
>   grows, so nothing pulses.
> - **The timelapse pre-passes every frame for the fit before rendering any.**
>   A live window cannot see the future and its monotone fit is correct; an
>   export can, and without the pre-pass the model visibly shrinks through the
>   video as later frames widen the box. The colour range is deliberately NOT
>   pre-passed — it re-anchors per candidate so each member is coloured over its
>   own values.
> - **A run's timelapse lands in `<run_dir>/timelapse/`**, inside the run, since
>   a run is meant to be one self-contained folder. A live directory's lands
>   beside it, because there is no run yet.

### 4.3 Wiring

- `gui/jobs.py`: `Job.live_dir: Path | None`; `program_and_args` appends
  `--live-dir`. `gui/newrun.py`: create it unasked next to the checkpoint
  block (`newrun.py:368-380`) — same reasoning as the comment there.
- `gui/runner.py` / `gui/window.py:143-147`: on job start, `MainWindow` opens
  (or retargets) the single `LiveViewWindow` instance at the job's live dir.
  Closing the window never touches the run; a "Live view" button in the
  progress-pane header reopens it, greyed out only when nothing is running
  **and** the selected run has no `frames/` dir (for finished runs it opens in
  scrub mode on `<run_dir>/frames/`).

## 5. End-of-run frame relocation

In `cli.py optimize`, after `solve.optimize` returns `run_dir`
(`cli.py:171-192`): move the live dir's frames into `<run_dir>/frames/` and
remove the live dir. On **pause**, frames stay in the live dir so resume
appends (the checkpoint dir has the same lifecycle). The viewer tolerates its
watched dir vanishing (run finished → it flips to scrubbing the run dir if it
can resolve it from the queue, else shows "run complete").

`runindex.py`'s stamp regex already excludes `runs/_live/` from the run list
(underscore prefix, same as `_checkpoints`). `frames/` inside a run dir is a
new artifact directory — mention it in the run-dir layout list in
EXECUTION_PLAN §2 if that list is updated.

## 6. Timelapse — `planeopt timelapse` (new CLI verb)

```
planeopt timelapse <run_dir | live_dir> [--out DIR] [--fps 30] [--size 1920x1080]
                   [--scalar cl] [--kind all|iterate|candidate] [--hold-candidate 15]
```

- Replays the frame stream **through the same `render3d` renderer** at the
  fixed default camera into numbered PNGs (`QImage` + offscreen platform; set
  `QT_QPA_PLATFORM=offscreen` when no display).
- `--hold-candidate N` repeats each candidate frame N times so finished
  members linger on screen — that is what makes a battery timelapse readable.
- If `ffmpeg` is on PATH, also assemble `timelapse.mp4` and say so; if not,
  leave the PNGs and **print the exact ffmpeg command** to run.
- The GUI's "Render timelapse…" button shells out to this verb as a
  subprocess (never in-process — rendering 5,000 frames must not freeze the
  GUI) and shows progress from its stdout in the log pane.

Because frames are data, not pixels, a better future renderer re-renders old
runs — that is why JSON-frames won the persistence decision.

## 7. Tests

Follow the existing conventions (`slow` marker for anything running a real
solve; suite is 257 passing — keep it green).

- **Frame writer**: atomicity (no non-`.json.gz` files ever visible after a
  crash mid-write, simulated); schema round-trip; seq resumes after a fake
  pause; degenerate dv (negative chord) skips without raising; the
  disable-on-first-error latch (inject a writer whose `open` raises → solve
  path continues, exactly one WARNING).
- **Never-kill-the-solve** is the one that matters most: a tiny NLP (reuse an
  existing fast solve fixture if one exists, else a 2-variable toy Opti) with
  a callback whose writer raises on frame 3 → solve still returns
  `Optimal Solution Found`.
- **Renderer**: pure-math tests for projection and depth order; a golden-image
  test rendering a canned frame to `QImage` offscreen and comparing against a
  committed PNG with a small per-pixel tolerance (this is also the pixel-
  perfection gate CLAUDE.md asks for — if the golden looks wrong, fix the
  renderer, don't re-bless the image casually).

  > **DEVIATION: pixel ASSERTIONS, not a committed golden.** Same offscreen
  > render, but what is checked is what the picture has to MEAN — the low quad
  > is the colormap's low colour, the near quad wins at the pixel where two
  > overlap (and still wins when their values are swapped, so a renderer with no
  > depth sort cannot pass), no model pixel lands behind the stats block, every
  > projected vertex is inside the widget. A golden PNG would be stricter on
  > paper and weaker in practice: font hinting and antialiasing differ across Qt
  > builds and platforms, so the tolerance would have to be loose enough to hide
  > a real regression or it would fail where nothing is wrong. The rule the
  > plan was protecting still holds — if a render looks wrong, fix the renderer.
- **Watcher**: write frames tmp+rename into a temp dir, assert the window
  model sees only complete frames and lands on the newest.
- **End-to-end** (`slow`): nominal solve with `--live-dir` → iterate frames
  strictly increasing in `iter`, exactly one candidate frame per member, stats
  block fields present, then `planeopt timelapse` over the result produces
  ≥ N PNGs.
- **Overhead** (spike artifact, not CI): nominal solve wall time with and
  without `--live-dir`, recorded in this file. Gate: < 2%.

## 8. Explicitly out of scope (so it isn't rediscovered)

- **Cp / chordwise pressure from the IN-LOOP model** — impossible
  (constraint 0.3). A chordwise-resolved ΔCp from the out-of-loop VLM is a
  different thing and is designed in section 11; it is not built, and it must
  never go in the iterate path.
- OpenGL / pyqtgraph / Qt3D (decision above).
- Live frames for `planeopt run` (fixed design — nothing iterates).
- Streaming frames over stderr — the file-watch transport was chosen because
  it also serves resumed runs, CLI runs, and scrubbing finished runs, with
  zero parsing protocol.

## 9. Milestone gate (mirrors the EXECUTION_PLAN row)

During a real battery launched from the GUI: the popup auto-opens, shows
geometry morphing per IPOPT iteration and a colored, fully-annotated frame per
finished candidate; solver wall-time overhead measured < 2%; a poisoned frame
writer cannot fail a member (test-pinned); after the run, `frames/` is in the
run dir and `planeopt timelapse` produces an MP4 (or PNGs + command) from it.

### 9.1 Where the gate stands (2026-08-05)

**Met, test-pinned** (`tests/test_liveframe.py`, `tests/test_liveview.py`,
46 tests): a poisoned writer cannot fail a member; iterates arrive in order with
at most one candidate frame each; frames relocate into `<run_dir>/frames/`;
`planeopt timelapse` produces PNGs and, without ffmpeg, the exact command.

**Met on a real solve.** A nominal `_solve_nlp` of the sample aircraft wrote 21
frames at **3.3 KB each** (the plan estimated 5–15 KB), with `inf_pr` falling
3.57 → 2.6e-11 across them and `span` walking 1.80 → 2.00 m. Replayed through
`planeopt timelapse` the last iterate reads, at a glance: span on its cap,
`le_shear` on its bound, `washout_tip` on its bound, and a **75 mm winglet
canted 87.5° against an 88° ceiling** — the FINDINGS §18 shape this view was
built to make visible. Known behaviour (HANDOFF issue 0b: the champion sits on
eight bounds), but it took one frame rather than a post-mortem, which is the
claim.

**The frames provably do not perturb the solve.** Cold and framed solves of the
same problem returned `119.93422` — identical to eight significant figures, and
`objective delta 0.000e+00`.

**NOT met: the overhead percentage, and watching a real battery.** Four nominal
solves were run in two ordered pairs, and the result is **unusable — the noise
floor of this machine is an order of magnitude larger than the effect.**

| order | 1st solve | 2nd solve |
|---|---|---|
| pair A | cold **5.726** | framed **4.726** |
| pair B | framed **5.065** | cold **5.778** |

Read it any way you like and it does not resolve: by treatment, framed
(4.73, 5.07) beat cold (5.73, 5.78) both times — a 12-17% *speedup* that writing
21 small files cannot possibly cause. By position, first (5.73, 5.07) against
second (4.73, 5.78) is a wash, so the warm-up hypothesis that pair A suggested
does not survive pair B either. What is left is ~1 minute of scatter on a ~5
minute solve from something else on the box — and **pair B's second solve
overlapped a full `pytest` run started in the same session, which was my error
and is enough on its own to void that cell.**

Two things can still be said, and they are the useful ones:

- **The frame work itself is measured, directly, and it is 12 ms per iterate**
  (section 1.1: geometry 7.1 + mesh 2.8 + summarize 2.3, plus a sub-millisecond
  gzip write). At 21 frames that is **0.25 s against a 286 s solve — 0.08%**,
  which is two orders of magnitude below the scatter above. That is why the
  end-to-end delta cannot be seen: there is nothing there to see.
- **The frames provably do not change the answer**: `119.93422` in all four
  solves, `objective delta 0.000e+00`.

To get the gate's number properly, someone needs an otherwise-idle machine and a
discarded warm-up solve, three solves minimum, with nothing else running — not
another pair like these.

---

# M5.5 — More to see: stall margin, wake, lift distribution, chosen views

> **IMPLEMENTED 2026-08-05**, except section 11 (ΔCp), which is designed and
> not built. The question that started it was "can you show pressure, like
> XFLR5?" — the answer is section 11's, and sections 10 and 12 are the three
> things that were both possible and more useful for an *optimizer* than a
> pressure plot is.

## 10. What a candidate frame carries now

All three are **candidate-only**. Nothing here can go on an iterate frame: each
needs solved circulation, and reading that during the solve is the 14.5 GB graph
evaluation section 1.1 (S2) exists to refuse.

### 10.1 Stall margin — `cl / cl_max(Re_local)`, on a FIXED 0→1 scale

The most useful colour this model can make, because it is the constraint the
solve is actually fighting: `_solve_nlp` bounds
`smooth_max(critical_section_ratios) <= 1` (MODEL_DETAILS 3.4), and this draws
that ratio on the aeroplane.

- `cl_max` comes from `result["clmax_ab_used"]` — the `A + B·ln(Re)` fit the
  solve **already made** for the wing root airfoil. No NeuralFoil call, and no
  possibility of quoting a different limit from the one the member satisfied.
  **No fit in the result → no channel**, rather than a second cl_max of our own.
- Two deliberate differences from the constraint, both toward a better picture:
  the local `cl` is the **lifting line's**, not Schrenk's approximation of it;
  and it is evaluated at the member's **converged cruise point**, not at the
  mission stall-speed limit — so a margin near 1.0 here is a much louder signal
  than the constraint being tight.
- **Main wing only.** `aero` treats `wings[0]` as the wing everywhere, and the
  fit is that airfoil's. Tail and winglet strips carry `None` and render in the
  plain uncoloured grey. That grey is the picture saying "different section, no
  honest number" — painting them dark blue would read as *margin 0*, the safest
  wing there is.
- **The scale is fixed at 0→1** (`render3d.SCALAR_FIXED_RANGE`), the only scalar
  that is. A fitted range would make a wing at 0.4 everywhere look exactly as
  alarming as one at 0.99. The colorbar says `· 1.0 = stall`, and `, >1 clipped`
  when anything exceeds it.

On the 2026-08-05 champion: 0.41 at the tips to 0.66 inboard. Comfortable, and
visibly so at a glance, which is the whole claim.

### 10.2 Wake streamlines

`LiftingLine.calculate_streamlines` — forward Euler through the same induced
velocity field `strip_loads` reads the forces from, so the lines cannot disagree
with the loading they are drawn beside. What this file chooses is only how many
and how far: **32 seeds × 28 steps**, against AeroSandbox's own 200 × 100, which
at this scale is a solid sheet and 20× the frame size. Length is
`max(0.5 · b_ref, 5 · c_ref)`.

This is the one thing a spanwise colour cannot show — the tip rollup. A winglet's
entire job is to move it, and FINDINGS §18 was a winglet artefact nobody could
see.

### 10.3 Lift distribution against elliptical

Sticks from each strip's quarter-chord up to a curve, with the elliptical
distribution of the **same total lift over the same span** dashed beside it.
Free: every number is already in `strip_loads`.

Height is normalised to 10% of span at the peak, so the **shape** is what reads.
That makes the height meaningless on its own, which is why `peak_n_per_m` and
`total_n` travel in the frame and the legend prints them. Wing only, for the same
reason as above — a tail's download would make the "elliptical" reference a
statement about nothing.

### 10.4 Three things the pictures forced

Found by rendering a real candidate frame (`runs/…-7`'s champion) rather than by
reasoning, which is why they are recorded:

- **The wake needs its own, stricter clip.** `ViewFit` guarantees the aeroplane
  lands inside `model_rect`; the wake deliberately does not, and from the plan
  view a 1 m wake behind a 0.9 m aeroplane ran off the canvas and straight
  through the stats block. Clipping *everything* to the stricter rectangle was
  the first fix and it cut the tail off. Hence two clips: `clip` for everything,
  `wake_clip` (`ink_rect`) for the streamlines alone.
- **The lift curve counts toward the camera fit; the wake does not.** The curve
  sits over the wing and would be cropped if ignored, and it counts whether or
  not it is being *drawn*, so toggling the overlay cannot resize the aeroplane —
  the fit is a property of the data. The wake runs half a span downstream and
  fitting it would shrink the model by a third to make room for air.
- **`Camera.basis` collapsed at the pole.** `orbit` clamps to ±88° so no dragging
  user could reach it, but the `plan` preset is exactly 90° and the basis went to
  zero — the whole model projected to a point. Guarded explicitly.

### 10.5 Cost, measured

One candidate frame on the sample aircraft, all three overlays included:
**0.59 s**, frame **10.4 KB** gzipped (3.3 KB before). Against a member solve of
4–30 minutes and a few dozen candidates per battery. Iterate frames are
untouched at 12 ms and ~3.3 KB.

## 11. ΔCp from the out-of-loop VLM — designed, NOT built

**This is the honest answer to "show me pressure like XFLR5".** XFLR5's own VLM
Cp view is panel **ΔCp** — the pressure jump across a lifting panel — not a
surface Cp with an upper and a lower side. That much is reachable: `aero.py:389`
already runs `asb.VortexLatticeMethod` with real chordwise panels. A true
surface Cp (the wrapped-around look of a 3D panel method) is not, and will not
be: it needs a solver this project does not have and should not grow.

Sketch, for whoever picks it up:

- One VLM run per **candidate**, at the member's converged operating point,
  ~1–3 s. Never per iterate.
- The frame carries a **second, finer mesh** (spanwise × chordwise) with its own
  per-quad ΔCp — not a relabelling of the lifting-line mesh, which has one
  chordwise panel and therefore nothing to resolve. Frame size goes to ~50 KB.
  The renderer needs nothing new; it is more quads.
- **The reliability gate is the load-bearing part.** HANDOFF 0a: individual VLM
  meshes blow up sporadically on high-cant geometries, and the blow-ups look
  perfectly physical in isolation (`CL = 113`, `k = -0.50`). `vlm_induced_check`
  answers this with an ensemble and a majority rule; a ΔCp field needs the same
  posture — shape-sanity checks, and **fall back to the `cl` colouring rather
  than paint a beautiful wrong picture**. A wrongly-coloured wing is worse than
  a grey one because it looks like an answer.
- Label it **ΔCp (VLM)**, never "Cp", and say in the colorbar that it is a
  second opinion — the VLM is *not* the model that drove the optimization.

## 12. Choosing the view before the run

A timelapse of a four-hour battery exists so that nobody has to be at the machine
when it finishes, which is why the camera is picked **in the New Run dialog**
rather than at render time.

Seven presets (`render3d.VIEW_PRESETS`): four three-quarter corners and the three
orthogonal elevations. A corner shows the aeroplane as an object, `plan` shows
planform and sweep, `front` shows dihedral, cant and tip washout, `side` shows
incidence and the boom. The default moved from **rear**-top-left to
**front**-top-left: the nose is the end worth seeing, and from behind, a
boom-tailed model is a tail with a wing behind it.

**Stored as a sidecar (`liveframe.VIEW_FILE`, `view.json`) beside the frames**,
not as a field in the queue — the same reasoning that made the frames files.
It travels into `<run_dir>/frames/` with them, so it still applies to a timelapse
rendered months later, for a run started from the CLI, and after the queue entry
is gone.

Precedence, most explicit first (`timelapse.resolve_camera`, and the CLI prints
which one it used, because an unexpected view is otherwise a five-minute render
followed by a hunt):

| source | how |
|---|---|
| `--yaw` / `--pitch` | arbitrary angle, overrides everything |
| `--view NAME` | a preset, by name; an unknown name fails **before** the render |
| the sidecar | what the New Run dialog recorded, or the live window adopted |
| the default | `front-top-left` |

The live window keeps its **own** camera: it opens at the run's stored view (and
double-click returns there, because "reset" means "back to how this opened"), but
orbiting is the user's to do and does not rewrite the run's choice. Its
**"Use for timelapse"** button is what does that, writing the camera on screen —
preset or arbitrary angle — into the sidecar.

---

# M5.7 — Colouring the iterates after the fact (recolour)

> **IMPLEMENTED 2026-08-05.** `src/planeopt/recolour.py`, `planeopt recolour`,
> `planeopt timelapse --colour-iterates`, the `recoloured` frame flag and its
> caption. Tests in `tests/test_liveframe.py` and `tests/test_liveview.py`.

## 13. Why this does not contradict S2

Section 1.1's S2 refused to colour iterates, and that refusal still stands — for
the reason it gave, which is about **when**, not whether. Circulation is deep
inside the Opti graph, so reading it *during* the solve builds a CasADi Function
over a graph that peaks near 14.5 GB, once per iteration.

But the colours on a candidate frame never came from that graph. They come from a
plain **numeric** `asb.LiftingLine` on floats (`liveframe.candidate_payload`),
and an iterate frame already carries everything that run needs: the full design
vector, and the V / alpha / deflection IPOPT was holding. So the same
aerodynamics is computable later, from frames on disk, with the solve finished.

### 13.1 Measured, on the 2026-08-05 nominal run

| | |
|---|---|
| per iterate | **0.22 s** median of 21 (range 0.19–0.50; the 0.50 is warm-up) |
| that whole run (21 iterates) | **4.8 s** |
| frame size | 3.3 KB → ~12 KB |
| failures | 0 of 21 |

Against the ~3% of solver wall time the same work costs inside the callback —
7 s iterations on that run — plus competing for memory with a 13 GB peak, plus
being unrepeatable. Offline wins on every axis, so this is a separate pass and
**not** a `--colour-iterates` flag on `optimize`.

The re-run agrees with the solve where it can be checked: iterate 20 recomputes
to CL 0.7759, identical to what the candidate frame reported.

## 14. The two honesty problems, and what was done about them

**A recoloured iterate is not trimmed.** Lift does not equal weight and Cm is not
zero until IPOPT has satisfied those constraints, so iterate 0 of the sample run
reports a perfectly real `Cm = -1.35`. Watching that go to zero is most of the
value. But CL/CD/L/D appearing where em dashes used to be reads as a result
unless something says otherwise, so frames carry `"recoloured": true` and the
stats block gains a second caption line (`liveframe.footnotes`). The caption is
not optional and `stats_block_size` reserves the row for it — a reservation that
disagreed with the drawing would put the line off the bottom edge.

Rows the lifting line cannot speak to — throttle, P_elec, AUW, the objective —
stay as em dashes. Recolour adds only what it can actually compute.

**Recolouring with the wrong aircraft would draw a different aeroplane.** Same
failure shape as the `restore()` bug in section 3: it would converge, look
perfect, and be a picture of something else. So `check_aircraft` compares the
frames' design vector against the aircraft's `DV_DEFAULTS` and **refuses** rather
than working around a mismatch.

This is not hypothetical. On 2026-08-05 the sample aircraft gained six design
variables (32 → 38) between a run finishing and its frames being recoloured, and
the guard caught it on the first real invocation. Hence `snapshot_aircraft`: a
run directory recolours against its own `inputs/aircraft.py` by default, which is
the only copy guaranteed to be the one those frames came from.

> **Known limit.** `inputs/` snapshots the FILES that were passed, not the package
> around them, so an aircraft importing a sibling construction profile
> (`from lwpla_a1 import ...`) will not load from the snapshot alone. That is the
> run artifact's shape, not something recolour should paper over — it reports
> which snapshot failed and asks for `--aircraft`. Widening the snapshot to the
> whole aircraft package would fix it for every consumer, and is worth doing if
> anything else ever needs to reconstruct a finished run's geometry.

## 15. The two entry points, and why both

- **`planeopt recolour <run|live-dir> [-a AIRCRAFT]`** — pays once and keeps the
  result, so the live window scrubs coloured iterates too and every later render
  is free. Writes to `<source>-coloured` by default; `--in-place` is opt-in,
  because the frames the solver wrote are the record of what it actually saw and
  this pass depends on an aircraft module that may have moved on since.
- **`planeopt timelapse … --colour-iterates`** — recolours in memory as it
  renders and persists nothing. This is the "I just want the video to have
  colours" path, and it must not rewrite a run's frames as a side effect of
  rendering one.

Both share `recolour.recolour_frame`. A frame that cannot be recoloured is
**copied through unchanged and counted**, never dropped: an infeasible iterate
with a negative chord is ordinary during a solve, and the geometry-only frame the
solver wrote for it is still the truth about that iterate. The count is printed —
"12 of 300 could not be drawn" is the difference between a thin timelapse and a
broken one.

Candidate frames pass through untouched. They were already computed this way, by
the solve, at the converged operating point; recomputing them could only
introduce a disagreement with the run artifact.

## 16. Not done

- **Parallelism.** Deliberately sequential. A battery is ~24 members × ~20
  iterates ≈ 500 frames ≈ under two minutes, and the 5,000-frame case is
  `MAX_ITERATE_FRAMES`' backstop rather than a run anyone has. Forked workers
  would follow the `_solve_worker` pattern if that ever changes; the measured
  0.22 s/frame is what to divide.
- **Recolouring during the live run**, in a second process watching the frame
  directory. Tempting — the window would fill in behind the solver — but it puts
  a second aerodynamics process on a machine already holding 13 GB, and the live
  view's job is to show the geometry moving. Do it after.
