"""Live solve frames: what the optimizer is shaping, written to disk as DATA.

M5.4 (`docs/LIVE_VIEWER_PLAN.md`). Two things wanted this, in priority order:

1. **Debugging.** Watching the solver wander through infeasible geometry is
   diagnostic in a way a post-mortem is not — the 2026-08-01 winglet artefact
   (a 52 mm panel canted 86 degrees riding a lifting-line hole to an L/D of 889,
   FINDINGS section 18) would have been visible in seconds.
2. **Timelapse** of a finished battery.

Four rules shape everything here:

- **Frames carry the mesh, already computed.** The GUI must never import
  aerosandbox or CasADi (EXECUTION_PLAN section 3 rule 1, and the ~14.5 GB solve
  stays crash-isolated in a child process). So the solver meshes and the viewer
  is a dumb renderer. This module is therefore the only half that knows about
  geometry; the reading half below it is plain stdlib, which is what lets the GUI
  import this module without dragging the solver in. **Every aerosandbox import
  is function-local for exactly that reason — do not hoist one to the top.**
- **A viz failure must never fail a solve.** Every entry point is wrapped; the
  first exception logs one WARNING and disables the writer for the rest of the
  run. `tests/test_liveframe.py` pins it with a poisoned writer.
- **There is no Cp and none can be faked.** The in-loop model is a lifting line
  with ONE chordwise panel (`LiftingLine.run`, `chordwise_resolution=1`), so no
  chordwise pressure distribution exists. The honest per-strip scalars are local
  section **cl** (stall-relevant, the default), circulation **gamma**, **lift per
  unit span**, and **stall margin** (`cl / cl_max(Re)`, the constraint the solver
  is actually fighting). Nothing here is ever labelled "Cp". A chordwise-resolved
  DELTA-Cp is possible from an out-of-loop VLM and is designed but not built —
  `docs/LIVE_VIEWER_PLAN.md` section 11.
- **Iterates are frequently infeasible.** An interior-point method reaches the
  solution through negative chords and negative boom lengths (see
  `geometry.smooth_floor`), so `aircraft.geometry(dv)` on garbage floats is tried
  and skipped, never trusted. It does not usually RAISE on garbage — it returns
  an aeroplane with nonsense dimensions — so the mesh is checked for finiteness
  and plausible size before a frame is written.

The mesh is the one the lifting line actually saw: each wing subdivided
`LIVE_SPANWISE_RESOLUTION`-ways and meshed with `chordwise_resolution=1`, which
is `LiftingLine._run_wings` verbatim. Panel order matches it exactly, which is
what lets a candidate frame's per-strip colours be attached to the quads without
a mapping table (checked by length before use, and dropped rather than
mis-coloured if it ever stops matching).
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import re
import time
from pathlib import Path

log = logging.getLogger("planeopt")

#: Bumped only for a breaking change. Readers ignore unknown fields, so adding
#: one is not a break.
SCHEMA = 1

#: Coordinates are stored as integers in units of 0.1 mm. A frame is then
#: 5-15 KB gzipped instead of 40-60 KB, and 0.1 mm is two orders of magnitude
#: finer than anything this project can build to.
COORD_SCALE = 10_000.0

#: Spanwise subdivision per wing section. MUST equal `asb.LiftingLine`'s default
#: `spanwise_resolution`, which is what `aero`'s in-loop runs use — the whole
#: point is that you are watching the mesh the solver's aerodynamics ran on, not
#: a prettier one drawn beside it.
LIVE_SPANWISE_RESOLUTION = 4

#: Stop writing ITERATE frames past this many. A 5,000-iteration battery is
#: ~25-75 MB of frames, which is fine; a runaway is not. Candidate frames are
#: never capped — there are at most a few dozen and they are the ones a report
#: would want.
MAX_ITERATE_FRAMES = 20_000

#: How many wake streamlines a candidate frame carries, and how many forward-
#: Euler steps each one is traced for. Seeds are spread evenly over the panel
#: trailing edges. 32 x 28 is ~2.7k coordinates — a few KB gzipped, against the
#: 200 x 100 AeroSandbox's own `calculate_streamlines` defaults to, which would
#: be 60k coordinates for a picture no one can read individual lines in.
LIVE_STREAMLINE_SEEDS = 32
LIVE_STREAMLINE_STEPS = 28

#: How far downstream the wake is traced, as a fraction of reference span and as
#: a multiple of mean chord — whichever is longer. A 2 m glider wants half a span
#: (the tip rollup is the point); a stubby wing wants the chord-based floor.
LIVE_STREAMLINE_SPANS = 0.5
LIVE_STREAMLINE_CHORDS = 5.0

#: Height of the lift-distribution overlay's peak above the wing, as a fraction
#: of wing span. The overlay is a SHAPE against an elliptical reference, so the
#: height is chosen to be readable rather than to mean metres; the legend prints
#: the peak in N/m so the scale is never guessed at.
LIFT_CURVE_SPAN_FRACTION = 0.10

#: A meshed iterate whose largest dimension exceeds this many metres is not an
#: aeroplane, it is the solver a long way from feasibility. Frames are skipped
#: rather than clamped: a frame that says nothing is better than one that claims
#: a 400 m wing (and it would flatten the camera fit for every frame after it).
MAX_PLAUSIBLE_SPAN_M = 100.0

FRAME_SUFFIX = ".json.gz"
_SEQ_RE = re.compile(r"^f(\d{6})__")

#: The camera a timelapse of these frames should be rendered from, chosen in the
#: New Run dialog before the run starts and overridable from the live window.
#:
#: A SIDECAR beside the frames rather than a field in the queue, for the same
#: reason the frames themselves are files: it travels into `<run_dir>/frames/`
#: when the run finishes, so `planeopt timelapse` picks it up months later, for a
#: run started from the CLI, and after the queue entry is long gone. It is
#: advice, never a constraint — `--view` on the command line overrides it, and a
#: missing or corrupt one costs the default view and nothing else.
VIEW_FILE = "view.json"


# --------------------------------------------------------------------- reading
# Plain stdlib, deliberately: the GUI and the timelapse renderer import these,
# and neither may pull aerosandbox in behind them.


def frame_paths(directory) -> list[Path]:
    """Every frame in `directory`, in chronological order.

    Lexicographic filename order IS chronological order — that is the ordering
    contract the naming scheme exists to provide (`_Member._write`), and it is
    what makes the timelapse a directory listing rather than a sort by parsed
    timestamps. Half-written files cannot appear: frames land by `os.replace`
    from a `.part` temp in the same directory.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.name.endswith(FRAME_SUFFIX) and _SEQ_RE.match(p.name)
    )


def read_frame(path) -> dict:
    """One frame, decompressed and parsed. Raises on a corrupt file."""
    with gzip.open(Path(path), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def quad_points(frame: dict) -> list[list[tuple[float, float, float]]]:
    """The mesh as metres: one list of four (x, y, z) per quad.

    The wire format is a flat integer array in units of 0.1 mm (`COORD_SCALE`),
    which is compact but not something a renderer should have to know about.
    """
    flat = ((frame.get("mesh") or {}).get("quads")) or []
    out = []
    for i in range(0, len(flat) - 11, 12):
        out.append([
            (flat[i + 3 * k] / COORD_SCALE,
             flat[i + 3 * k + 1] / COORD_SCALE,
             flat[i + 3 * k + 2] / COORD_SCALE)
            for k in range(4)
        ])
    return out


def _polylines(encoded) -> list[list[tuple[float, float, float]]]:
    out = []
    for line in encoded or []:
        out.append([
            (line[i] / COORD_SCALE, line[i + 1] / COORD_SCALE, line[i + 2] / COORD_SCALE)
            for i in range(0, len(line) - 2, 3)
        ])
    return out


def outline_points(frame: dict) -> list[list[tuple[float, float, float]]]:
    """The fuselage/boom wireframe polylines, as metres."""
    return _polylines((frame.get("mesh") or {}).get("outlines"))


def streamline_points(frame: dict) -> list[list[tuple[float, float, float]]]:
    """Wake streamlines, as metres. Candidate frames only, and possibly empty."""
    return _polylines((frame.get("overlays") or {}).get("streamlines"))


def lift_overlay(frame: dict) -> dict | None:
    """The spanwise lift distribution as drawable geometry, or None.

    Three polyline sets in metres — `sticks` (one two-point segment per strip,
    from the wing up to the curve), `curve` (the tops, in spanwise order) and
    `elliptical` (the same-lift, same-span reference) — plus `peak_n_per_m` and
    `total_n`, which are what make the height mean something.
    """
    overlay = (frame.get("overlays") or {}).get("lift")
    if not overlay or not overlay.get("curve"):
        return None
    return {
        "sticks": _polylines(overlay.get("sticks")),
        "curve": _polylines([overlay["curve"]])[0],
        "elliptical": (_polylines([overlay["elliptical"]]) or [[]])[0]
        if overlay.get("elliptical") else [],
        "peak_n_per_m": overlay.get("peak_n_per_m"),
        "total_n": overlay.get("total_n"),
    }


def scalar_values(frame: dict, name: str) -> list[float] | None:
    """Per-quad values of the named scalar, or None if this frame has none.

    Candidate frames carry all three under `color.all`, so switching the
    viewer's dropdown re-reads what is already in hand rather than asking the
    solver for anything.
    """
    color = frame.get("color") or {}
    if not color:
        return None
    if name == color.get("name"):
        return color.get("values")
    return (color.get("all") or {}).get(name)


#: The stats block, as (label, key, format, source) rows. Kept here rather than
#: in the renderer because it is pure formatting over a frame dict, which means
#: it is testable without a display — the same split `runindex` and `jobs` use
#: (EXECUTION_PLAN section 3 rule 1).
#:
#: `ipopt_objective` is labelled for what it is. IPOPT minimizes whatever
#: `Objective.nlp_expression` handed it, which for endurance is a monotone
#: surrogate and not minutes; calling it "objective" beside a candidate frame
#: that reports real minutes would put two different quantities under one name.
_GEOMETRY_ROWS = (
    ("span", "geometry.span_m", "{:.3f} m"),
    ("span (proj)", "geometry.span_projected_m", "{:.3f} m"),
    ("area", "geometry.area_m2", "{:.4f} m2"),
    ("aspect ratio", "geometry.aspect_ratio", "{:.2f}"),
    ("mean chord", "geometry.mean_chord_m", "{:.4f} m"),
    ("root chord", "dv.c_root", "{:.4f} m"),
    ("taper", "dv.taper", "{:.3f}"),
    ("fullness", "dv.fullness", "{:.3f}"),
    ("LE shear", "dv.le_shear", "{:.3f}"),
    ("washout tip", "dv.washout_tip", "{:+.2f} deg"),
    ("tail arm", "dv.tail_arm", "{:.3f} m"),
    ("winglet len", "geometry.winglet.length_m", "{:.3f} m"),
    ("winglet cant", "geometry.winglet.cant_deg", "{:.1f} deg"),
    ("AUW", "scalars.auw_kg", "{:.3f} kg"),
    ("wing loading", "@wing_loading", "{:.1f} g/dm2"),
)
_STATE_ROWS = (
    ("V", "state.V_ms", "{:.2f} m/s"),
    ("alpha", "state.alpha_deg", "{:+.2f} deg"),
    ("deflection", "state.deflection_deg", "{:+.2f} deg"),
    ("CL", "scalars.CL", "{:.4f}"),
    ("CD", "scalars.CD", "{:.5f}"),
    ("L/D", "scalars.L_over_D", "{:.2f}"),
    ("oswald e", "scalars.oswald_e", "{:.3f}"),
    ("Cm", "scalars.Cm", "{:+.5f}"),
    ("static margin", "scalars.static_margin", "{:.4f}"),
    ("throttle", "@throttle_pct", "{:.1f} %"),
    ("P_elec", "scalars.P_elec_w", "{:.1f} W"),
    ("objective", "scalars.objective_value", "{:.4g}"),
    ("IPOPT obj*", "scalars.ipopt_objective", "{:.6g}"),
    ("inf_pr", "scalars.inf_pr", "{:.3e}"),
    ("inf_du", "scalars.inf_du", "{:.3e}"),
)

#: What a row shows when this frame does not carry it. Never a stale number from
#: the previous frame: an iterate frame has no CL, and showing the last
#: candidate's would be inventing one for a geometry that has moved since.
MISSING = "—"


def _dig(frame: dict, path: str):
    node = frame
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _derived(frame: dict, name: str):
    if name == "wing_loading":
        auw = _dig(frame, "scalars.auw_kg")
        area = _dig(frame, "geometry.area_m2")
        return auw * 1000.0 / (area * 100.0) if auw and area else None
    if name == "throttle_pct":
        frac = _dig(frame, "scalars.throttle_frac")
        return frac * 100.0 if frac is not None else None
    return None


def _rows(frame: dict, spec) -> list[tuple[str, str]]:
    out = []
    for label, path, fmt in spec:
        value = _derived(frame, path[1:]) if path.startswith("@") else _dig(frame, path)
        if value is None:
            # A row that never applies to this aircraft (no winglet, no fullness
            # variable) is dropped; a row that applies but is unknown in THIS
            # frame keeps its place with an em dash, so the block does not
            # reflow between an iterate and a candidate.
            if path.startswith("dv.") or path.startswith("geometry."):
                continue
            out.append((label, MISSING))
            continue
        try:
            out.append((label, fmt.format(float(value))))
        except (TypeError, ValueError):
            out.append((label, str(value)))
    return out


def stats_columns(frame: dict) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The two-column stats block: (geometry rows, state rows)."""
    return _rows(frame, _GEOMETRY_ROWS), _rows(frame, _STATE_ROWS)


#: What is written under the stats block, and why each line has to be there.
FOOTNOTE_IPOPT = "* IPOPT obj is the minimized form, not the reported objective"
FOOTNOTE_RECOLOURED = (
    "aerodynamics filled in after the solve, at this iterate's V and alpha — "
    "the aircraft is not trimmed here, so CL and Cm are real but not a result"
)


def footnotes(frame: dict) -> list[str]:
    """The caption lines this frame needs.

    A RECOLOURED iterate gets a second one, and it is not optional. Filling the
    aerodynamics in after the solve puts CL, CD, L/D and Cm on a frame that had
    em dashes before — and on an iterate those are the true numbers for an
    aircraft IPOPT has not finished trimming. Iterate 0 of the sample run reports
    `Cm = -1.35`, which is correct and would be alarming read as a result.
    """
    lines = [FOOTNOTE_IPOPT]
    if frame.get("recoloured"):
        lines.append(FOOTNOTE_RECOLOURED)
    return lines


def header_text(frame: dict) -> str:
    """The one line that says WHICH member and iterate this is.

    Always present and always naming the member, because in forked (parallel)
    mode the newest frame can belong to any of the members in flight, and a
    stats block that could silently be about a different aeroplane is worse than
    no stats block.
    """
    index = frame.get("member_index") or [0, 0]
    where = f"[{index[0]}/{index[1]}]" if len(index) == 2 and index[1] else ""
    tail = (
        f"iter {frame['iter']}" if frame.get("kind") == "iterate" and "iter" in frame
        else "converged"
    )
    return (
        f"{frame.get('label', '?')} {where} {frame.get('key', '?')}  ·  {tail}"
        f"  ·  t+{frame.get('t_member_s', 0):.0f} s"
    )


def write_view(directory, view: dict) -> Path | None:
    """Record the timelapse camera for a frame directory. Best-effort.

    Creates the directory if it does not exist yet, which is the normal case:
    the GUI writes this when a job is queued and the solver only creates the
    directory when it writes its first frame.
    """
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / VIEW_FILE
        tmp = directory / f"{VIEW_FILE}.{os.getpid()}.part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"schema": SCHEMA, **view}, fh, indent=1)
        os.replace(tmp, path)
        return path
    except (OSError, TypeError, ValueError) as e:
        log.debug("could not record the timelapse view in %s: %s", directory, e)
        return None


def read_view(directory) -> dict | None:
    """The recorded timelapse camera, or None. Never raises."""
    try:
        with open(Path(directory) / VIEW_FILE, encoding="utf-8") as fh:
            view = json.load(fh)
        return view if isinstance(view, dict) else None
    except (OSError, ValueError):
        return None


def relocate(live_dir, run_dir) -> Path | None:
    """Move a finished run's frames into `<run_dir>/frames/`.

    The run directory does not exist until the run ENDS (`report.assemble.
    write_run_dir`), which is why frames are written to a live directory in the
    first place. This is the other half of that: once the artifacts exist the
    frames belong with them, so a finished run can be replayed months later from
    one self-contained directory.

    Best-effort by construction — losing the frames must never be what fails a
    battery that has already succeeded. Returns the destination, or None.
    """
    live_dir, run_dir = Path(live_dir), Path(run_dir)
    frames = frame_paths(live_dir)
    if not frames:
        return None
    dest = run_dir / "frames"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for path in frames:
            os.replace(path, dest / path.name)
        # The view sidecar travels with the frames, so the run's timelapse comes
        # out in the view that was chosen for it however long afterwards it is
        # rendered. It is advice: its absence costs the default view.
        if (live_dir / VIEW_FILE).is_file():
            os.replace(live_dir / VIEW_FILE, dest / VIEW_FILE)
        # Anything else in there is a `.part` from a killed write; the directory
        # only goes away if it is genuinely empty.
        for leftover in live_dir.iterdir():
            if leftover.is_file() and leftover.name.endswith(".part"):
                leftover.unlink()
        live_dir.rmdir()
    except OSError as e:
        log.warning("could not move live frames from %s into %s: %s", live_dir, dest, e)
        return dest if dest.is_dir() else None
    log.info("moved %d live frame(s) into %s", len(frames), dest)
    return dest


# --------------------------------------------------------------------- meshing


def _slug(text) -> str:
    out = "".join(c if c.isalnum() or c in "-._" else "_" for c in str(text))
    return out[:48] or "_"


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def mesh_of(airplane) -> dict | None:
    """The lifting line's own panel mesh, as a compact wire-format dict.

    Returns None when the geometry is not one that can be drawn — a NaN
    coordinate from an infeasible iterate, or a hundred-metre wing. Both are
    ordinary during a solve and neither is worth a frame.

    Symmetric surfaces are meshed on BOTH sides, because `mesh_thin_surface`
    mirrors them itself and because the viewer should show the whole aeroplane.
    """
    quads: list[int] = []
    surface_of: list[int] = []
    surfaces: list[str] = []
    extent = 0.0
    for index, wing in enumerate(airplane.wings):
        sub = (
            wing.subdivide_sections(ratio=LIVE_SPANWISE_RESOLUTION)
            if LIVE_SPANWISE_RESOLUTION > 1 and len(wing.xsecs) > 1
            else wing
        )
        points, faces = sub.mesh_thin_surface(
            method="quad", chordwise_resolution=1, add_camber=False
        )
        surfaces.append(str(getattr(wing, "name", f"surface {index}")))
        for face in faces:
            for vertex in face:
                for axis in range(3):
                    value = float(points[vertex][axis])
                    if not math.isfinite(value):
                        return None
                    extent = max(extent, abs(value))
                    quads.append(int(round(value * COORD_SCALE)))
            surface_of.append(index)
    if not surface_of or extent > MAX_PLAUSIBLE_SPAN_M:
        return None
    return {"quads": quads, "surface_of": surface_of, "surfaces": surfaces}


#: How many points go round each fuselage station ring, and how many longitudinal
#: lines connect them. Enough to read as a body from any angle, few enough that
#: the outlines stay a rounding error next to the panel mesh.
_FUSELAGE_RING_POINTS = 16
_FUSELAGE_LONGERONS = 8


def outlines_of(lofts) -> list[list[int]]:
    """Wireframe polylines for the fuselage/boom lofts.

    Station rings plus longerons — enough to place the wing on a body without
    pretending the viewer is a surface renderer. The lofts are the SAME ones the
    three-view and `interactive_3d.html` are drawn from (`solve.run`'s viz twin),
    so nothing new is being modelled here.

    On ITERATE frames as well as candidates, which is why the whole ring is
    sampled in one vectorised `get_3D_coordinates` call rather than one call per
    point: per-point it cost 11.4 ms, which would have doubled the per-iterate
    budget for decoration. The boom is worth the remaining millisecond — its
    length is the design variable `tail_arm`, so watching it stretch is one of
    the things the live view exists to show, and a tail floating in space
    detached from the wing is not a readable aeroplane.
    """
    import numpy as np

    lines: list[list[int]] = []

    def encode(points) -> list[int] | None:
        flat: list[int] = []
        for x, y, z in points:
            for value in (x, y, z):
                if not math.isfinite(value):
                    return None
                flat.append(int(round(value * COORD_SCALE)))
        return flat

    thetas = np.linspace(0, 2 * math.pi, _FUSELAGE_RING_POINTS, endpoint=False)
    for loft in lofts or []:
        rings = []
        for xsec in getattr(loft, "xsecs", []):
            x, y, z = xsec.get_3D_coordinates(theta=thetas)
            rings.append([
                (float(a), float(b), float(c))
                for a, b, c in zip(np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z))
            ])
        if not rings:
            continue
        for ring in rings:
            encoded = encode([*ring, ring[0]])
            if encoded:
                lines.append(encoded)
        step = max(1, _FUSELAGE_RING_POINTS // _FUSELAGE_LONGERONS)
        for k in range(0, _FUSELAGE_RING_POINTS, step):
            encoded = encode([ring[k] for ring in rings])
            if encoded:
                lines.append(encoded)
    return lines


def strip_loads(lifting_line, alpha_deg: float, velocity: float) -> dict:
    """Per-strip circulation, lift per unit span and local section cl.

    Read off a lifting-line run that has already happened, from the same
    quantities its own force integration uses: the bound-vortex strength gamma,
    the local velocity at the bound leg's centre, and Kutta-Joukowski
    (`F = rho * (V x l) * gamma`). Dividing that force's LIFT component by the
    bound-leg length gives lift per span, and dividing by `q * chord` gives the
    section cl the stall constraint is actually about.

    `sum(lift_per_span * span) == L` to within the profile-drag contribution to
    lift (~0.06% on the sample aircraft), which is the check that this is
    reading the model rather than paraphrasing it.

    Also returns the INDUCED drag, which the inviscid part of the same force is
    by definition, so a span efficiency can be quoted without inventing one.
    """
    import numpy as np

    gamma = np.array(lifting_line.vortex_strengths).ravel()
    velocities = lifting_line.get_velocity_at_points(lifting_line.vortex_centers)
    rho = lifting_line.op_point.atmosphere.density()
    forces = rho * np.cross(velocities, lifting_line.vortex_bound_leg) * gamma.reshape(-1, 1)

    # Wind axes about the x-z plane (beta is 0 everywhere in this project's
    # trim). Verified against `LiftingLine.run`'s own L: 15.505 vs 15.495 N.
    a = math.radians(float(alpha_deg))
    lift_dir = np.array([-math.sin(a), 0.0, math.cos(a)])
    drag_dir = np.array([math.cos(a), 0.0, math.sin(a)])

    span = np.linalg.norm(lifting_line.vortex_bound_leg, axis=1)
    span = np.where(span > 1e-9, span, 1e-9)
    lift_per_span = (forces @ lift_dir) / span
    q = 0.5 * rho * float(velocity) ** 2
    chords = np.array(lifting_line.chords).ravel()
    chords = np.where(chords > 1e-9, chords, 1e-9)
    return {
        "gamma": [float(v) for v in gamma],
        "lift_per_span": [float(v) for v in lift_per_span],
        "cl": [float(v) for v in lift_per_span / (q * chords)],
        "induced_drag_n": float((forces @ drag_dir).sum()),
        # Not drawn, but the two things every derived quantity below needs: the
        # local chord sets the strip's Reynolds number and the bound-leg length
        # is what turns lift-per-span back into newtons.
        "chord_m": [float(v) for v in chords],
        "strip_span_m": [float(v) for v in span],
    }


def stall_margins(loads: dict, velocity: float, clmax_ab, wing_panels, rho: float) -> list:
    """Per-strip `cl / cl_max(Re_local)` — 1.0 is the section's stall limit.

    The most useful colour this model can produce, because it is the constraint
    the optimizer is actually fighting: `_solve_nlp` bounds
    `smooth_max(critical_section_ratios) <= 1` (MODEL_DETAILS 3.4), and this is
    that ratio drawn on the aeroplane.

    Two honest differences from the constraint, both in the direction of being
    a better picture rather than a different model:

    - the local `cl` here is the LIFTING LINE's, not Schrenk's approximation of
      it, so this is the loading the rest of the solve used;
    - it is evaluated at the CRUISE point the member converged to, not at the
      mission's stall-speed limit, so a margin near 1.0 in cruise is a much
      louder signal than the constraint being tight.

    `clmax_ab` is the `(A, B)` of `cl_max ~ A + B*ln(Re)` that the solve already
    fitted for the wing's root airfoil and reports as `clmax_ab_used` — so this
    costs no NeuralFoil calls and cannot disagree with the constraint's limit.

    Strips outside the main wing get None: the fit is the WING airfoil's, and
    painting a tail with it would be a number about a different section. The
    renderer draws a None strip in the uncoloured grey, which is the picture
    saying so.
    """
    from .aero import SECTION_FACTOR

    A, B = (float(clmax_ab[0]), float(clmax_ab[1]))
    mu = 1.81e-5
    out: list[float | None] = []
    for i, cl in enumerate(loads["cl"]):
        chord = loads["chord_m"][i]
        if not wing_panels[i] or chord <= 0:
            out.append(None)
            continue
        re = rho * float(velocity) * chord / mu
        clmax = SECTION_FACTOR * (A + B * math.log(max(re, 1.0)))
        out.append(float(cl) / clmax if clmax > 0 else None)
    return out


def streamlines_of(lifting_line, seeds: int = LIVE_STREAMLINE_SEEDS,
                   steps: int = LIVE_STREAMLINE_STEPS) -> list[list[int]]:
    """Wake streamlines traced downstream from the panel trailing edges.

    `LiftingLine.calculate_streamlines` already does this — forward Euler on the
    induced velocity field, which is the same field `strip_loads` reads the
    forces from — so nothing new is being modelled and the lines cannot disagree
    with the loading they are drawn beside. What is chosen here is only how MANY
    and how FAR: AeroSandbox's defaults (200 lines, 100 steps) are a solid sheet
    at this scale and 20x the frame size.

    This is what makes the tip vortex visible, which is the one thing a spanwise
    colour cannot show: a winglet's whole job is to move that rollup, and
    FINDINGS section 18 was a winglet artefact nobody could see.
    """
    import numpy as np

    left = getattr(lifting_line, "back_left_vertices", None)
    right = getattr(lifting_line, "back_right_vertices", None)
    if left is None or right is None or len(left) == 0:
        return []
    midpoints = (np.asarray(left) + np.asarray(right)) / 2
    # Evenly spread over the panels rather than the first N: a wing's panels are
    # in spanwise order, so taking the first 32 of 60 would seed one wing half
    # and leave the other bare.
    take = np.unique(np.linspace(0, len(midpoints) - 1, min(seeds, len(midpoints))).round().astype(int))
    airplane = lifting_line.airplane
    length = max(
        LIVE_STREAMLINE_SPANS * float(airplane.b_ref),
        LIVE_STREAMLINE_CHORDS * float(airplane.c_ref),
    )
    traced = lifting_line.calculate_streamlines(
        seed_points=midpoints[take], n_steps=max(2, steps), length=length
    )
    lines: list[list[int]] = []
    for line in np.asarray(traced):  # (seed, 3, step)
        flat: list[int] = []
        for step in range(line.shape[1]):
            point = line[:, step]
            if not all(math.isfinite(float(v)) for v in point):
                break  # a filament that fell into a singularity: keep what is good
            flat.extend(int(round(float(v) * COORD_SCALE)) for v in point)
        if len(flat) >= 6:
            lines.append(flat)
    return lines


def lift_distribution(lifting_line, loads: dict, wing_panels, span_m: float) -> dict | None:
    """The spanwise lift distribution as drawable geometry, against elliptical.

    The classic view, and the one that answers "how much did the taper and the
    washout actually cost": sticks rising from each strip's quarter-chord to a
    curve, with the elliptical distribution of the SAME total lift over the SAME
    span dashed beside it. Everything comes from `strip_loads`, so it is free —
    no extra aerodynamics runs, and it cannot disagree with the colours.

    Main wing only. A tail's download and a winglet's side force are lift in the
    same sense and would make the curve unreadable and the "elliptical" reference
    meaningless.

    The height is normalised (`LIFT_CURVE_SPAN_FRACTION` of span at the peak) so
    the SHAPE is what reads; `peak_n_per_m` and `total_n` travel with it so the
    viewer's legend can say what the height is worth.
    """
    import numpy as np

    centres = np.asarray(lifting_line.vortex_centers)
    lift = np.asarray(loads["lift_per_span"], dtype=float)
    widths = np.asarray(loads["strip_span_m"], dtype=float)
    keep = [i for i in range(min(len(centres), len(lift))) if wing_panels[i]]
    if len(keep) < 2:
        return None
    keep.sort(key=lambda i: float(centres[i][1]))  # spanwise, so the curve does not zigzag

    ys = np.array([float(centres[i][1]) for i in keep])
    ls = lift[keep]
    total = float((ls * widths[keep]).sum())
    y_mid = (ys.min() + ys.max()) / 2
    b = float(span_m) if span_m and span_m > 0 else float(ys.max() - ys.min())
    if b <= 0:
        return None
    # Elliptical of equal lift and equal span: l(y) = 4L/(pi*b) * sqrt(1-(2y/b)^2).
    eta = np.clip(2 * (ys - y_mid) / b, -1.0, 1.0)
    ell = (4 * total / (math.pi * b)) * np.sqrt(np.maximum(0.0, 1 - eta**2))

    peak = float(max(np.abs(ls).max(), np.abs(ell).max()))
    if not math.isfinite(peak) or peak <= 0:
        return None
    scale = (LIFT_CURVE_SPAN_FRACTION * b) / peak

    def encode(points) -> list[int] | None:
        flat: list[int] = []
        for point in points:
            for value in point:
                if not math.isfinite(float(value)):
                    return None
                flat.append(int(round(float(value) * COORD_SCALE)))
        return flat

    anchors = [tuple(float(v) for v in centres[i]) for i in keep]
    tops = [
        (a[0], a[1], a[2] + float(ls[k]) * scale) for k, a in enumerate(anchors)
    ]
    ell_tops = [
        (a[0], a[1], a[2] + float(ell[k]) * scale) for k, a in enumerate(anchors)
    ]
    curve = encode(tops)
    if curve is None:
        return None
    sticks = [s for s in (encode([anchors[k], tops[k]]) for k in range(len(keep))) if s]
    return {
        "sticks": sticks,
        "curve": curve,
        "elliptical": encode(ell_tops) or [],
        "peak_n_per_m": float(np.abs(ls).max()),
        "total_n": total,
    }


# --------------------------------------------------------------------- writing


def _next_seq(directory: Path) -> int:
    """One past the highest sequence number already on disk.

    A paused-and-resumed battery keeps appending in order rather than
    overwriting the frames the first half wrote — the same lifecycle the
    checkpoint directory has.
    """
    highest = -1
    for path in frame_paths(directory):
        match = _SEQ_RE.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


class FrameWriter:
    """Frames for one run, with the disable-on-first-error latch.

    The latch is the load-bearing part: a solve is 5-30 minutes and a battery is
    hours, and no picture is worth losing one. Anything that raises — a full
    disk, a read-only mount, a geometry mapping that does not survive a garbage
    iterate — costs exactly one WARNING and then nothing at all.
    """

    def __init__(self, live_dir, aircraft=None) -> None:
        self.dir = Path(live_dir)
        self.aircraft = aircraft
        self.disabled = False
        self.seq = 0
        self.iterate_frames = 0
        self.capped = False
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.seq = _next_seq(self.dir)
        except OSError as e:
            self.fail(e)

    def fail(self, exc: BaseException) -> None:
        """Give up on frames, once, out loud."""
        if self.disabled:
            return
        self.disabled = True
        log.warning(
            "live frames disabled for the rest of this run (%s: %s). The solve is "
            "unaffected — frames are a view of it, never a part of it.",
            type(exc).__name__, exc,
        )

    def member(self, label: str, key, index: int, total: int) -> "_Member":
        """A writer bound to one member solve, holding its own wall clock."""
        return _Member(self, label, key, index, total)


class _Member:
    """Frame writing for one member solve — the object the solver holds."""

    def __init__(self, writer: FrameWriter, label: str, key, index: int, total: int) -> None:
        self.writer = writer
        self.label = label
        self.key = key
        self.index = index
        self.total = total
        self.t0 = time.monotonic()

    # --- the two hooks the solver calls ---------------------------------

    def iterate(self, iter_n: int, dv: dict, state: dict, scalars: dict) -> None:
        """One IPOPT iterate: geometry only, no aerodynamics.

        Deliberately colourless. Colouring an iterate would mean a lifting-line
        run per iteration (~0.4 s against a ~1.5 s iteration) or reading the
        implicit circulation back through a CasADi function built over the whole
        14.5 GB graph. Neither is worth 2% of a battery to watch a number that
        changes shape anyway — the geometry morphing IS the diagnostic, and the
        finished candidate carries the colours.
        """
        writer = self.writer
        if writer.disabled or writer.aircraft is None:
            return
        if writer.iterate_frames >= MAX_ITERATE_FRAMES:
            if not writer.capped:
                writer.capped = True
                log.info(
                    "live frames: %d iterate frames written — no more will be "
                    "(candidate frames continue)", MAX_ITERATE_FRAMES,
                )
            return
        try:
            if not all(_finite(v) for v in dv.values()):
                return  # an iterate with a NaN in it: nothing to draw, not an error
            airplane = writer.aircraft.geometry(dv)
            mesh = mesh_of(airplane)
            if mesh is None:
                log.debug("live frames: iterate %d is not drawable, skipped", iter_n)
                return
            self._add_outlines(mesh, dv)
            self._write(
                {
                    "kind": "iterate",
                    "iter": int(iter_n),
                    "dv": {k: float(v) for k, v in dv.items()},
                    "state": {k: float(v) for k, v in state.items() if _finite(v)},
                    "geometry": _summarize(airplane),
                    "mesh": mesh,
                    "scalars": {k: float(v) for k, v in scalars.items() if _finite(v)},
                },
                iter_n=iter_n,
            )
            writer.iterate_frames += 1
        except Exception as e:  # noqa: BLE001 — a view of the solve, never part of it
            self.writer.fail(e)

    def candidate(self, result: dict) -> None:
        """A finished member: the full aeroplane, coloured, with its stats block.

        Costs one numeric lifting-line run at the converged operating point
        (~0.4 s) plus the loft outlines, against a member solve measured in
        minutes. Everything it needs — V, alpha, deflection, x_cg — is already in
        the result dict, so nothing is re-derived and nothing can disagree with
        what the optimizer reported.
        """
        writer = self.writer
        if writer.disabled or writer.aircraft is None:
            return
        if "failed" in result or not result.get("dv"):
            return  # a member that did not converge has no aeroplane to draw
        try:
            self._write(self._candidate_payload(result), iter_n=None)
        except Exception as e:  # noqa: BLE001
            self.writer.fail(e)

    # --- construction ---------------------------------------------------

    def _add_outlines(self, mesh: dict, dv: dict) -> None:
        add_outlines(self.writer.aircraft, mesh, dv)

    def _candidate_payload(self, result: dict) -> dict:
        return candidate_payload(self.writer.aircraft, result)

    def _write(self, payload: dict, iter_n: int | None) -> None:
        writer = self.writer
        seq = writer.seq
        writer.seq += 1
        tail = "final" if iter_n is None else f"i{int(iter_n):04d}"
        name = f"f{seq:06d}__{_slug(self.label)}__{_slug(self.key)}__{tail}{FRAME_SUFFIX}"
        write_frame(
            writer.dir / name,
            {
                "schema": SCHEMA,
                "label": self.label,
                "key": str(self.key),
                "member_index": [self.index, self.total],
                "t_member_s": round(time.monotonic() - self.t0, 2),
                **payload,
            },
        )


def add_outlines(aircraft, mesh: dict, dv: dict) -> None:
    """Attach the fuselage/boom wireframe, if this aircraft declares one.

    Decoration, so it is allowed to fail on its own without costing the frame —
    a body loft is the part of an aircraft definition most likely to object to an
    infeasible iterate (negative nose length, inverted bay).
    """
    if not hasattr(aircraft, "fuselage_lofts"):
        return
    try:
        lines = outlines_of(aircraft.fuselage_lofts(dv))
    except Exception as e:  # noqa: BLE001
        log.debug("live frames: fuselage outlines unavailable: %s", e)
        return
    if lines:
        mesh["outlines"] = lines


def candidate_payload(aircraft, result: dict) -> dict:
    """Everything a COLOURED frame is made of, for a design at an operating point.

    Module-level and public because two callers need it and only one of them is a
    running solve: `_Member.candidate` writes it when a member converges, and
    `recolour` builds the same thing for a finished ITERATE frame, offline, from
    the design vector and operating point that frame already carries.

    Costs one numeric `asb.LiftingLine` — floats in, floats out, never touching
    the Opti graph, which is why it is ~0.2 s and not the 14.5 GB the plan's S2
    spike refused (LIVE_VIEWER_PLAN section 1.1).
    """
    import aerosandbox as asb

    from . import aero

    dv = {k: float(v) for k, v in result["dv"].items()}
    airplane = aircraft.geometry(dv)
    mesh = mesh_of(airplane)
    if mesh is None:
        raise ValueError("the champion's own geometry did not mesh")

    control = getattr(aircraft, "pitch_control_name", "ruddervator")
    deflected = airplane.with_control_deflections(
        {control: float(result["deflection_deg"])}
    )
    lifting_line = asb.LiftingLine(
        airplane=deflected,
        op_point=asb.OperatingPoint(
            velocity=float(result["V_ms"]), alpha=float(result["alpha_deg"])
        ),
        xyz_ref=[float(result["x_cg_m"]), 0, 0],
        vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS,
    )
    run = lifting_line.run()
    loads = strip_loads(
        lifting_line, float(result["alpha_deg"]), float(result["V_ms"])
    )

    color = None
    overlays: dict = {}
    n_quads = len(mesh["surface_of"])
    if len(loads["cl"]) == n_quads:
        # Panel index -> "is this strip on the main wing?". `aero` treats
        # `wings[0]` as the wing everywhere (stall, gust, span efficiency),
        # and both the stall margin and the lift distribution are statements
        # about that surface alone.
        wing_panels = [surface == 0 for surface in mesh["surface_of"]]
        channels = {k: loads[k] for k in ("cl", "gamma", "lift_per_span")}
        margins = _stall_margins(result, loads, lifting_line, wing_panels)
        if margins is not None:
            channels["stall_margin"] = margins
        color = {"name": "cl", "values": loads["cl"], "all": channels}
        overlays = _overlays(lifting_line, loads, wing_panels, airplane)
    else:
        # The panel-order correspondence is the one assumption this file
        # makes about AeroSandbox internals. If it ever stops holding, say so
        # and ship the frame uncoloured — a wrongly-coloured wing is worse
        # than a grey one, because it looks like an answer.
        log.warning(
            "live frames: %d lifting-line strips against %d mesh quads — "
            "shipping this candidate frame without colours",
            len(loads["cl"]), n_quads,
        )

    add_outlines(aircraft, mesh, dv)
    return {
        "kind": "candidate",
        "overlays": overlays,
        "dv": dv,
        "state": {
            k: float(result[k])
            for k in ("V_ms", "alpha_deg", "deflection_deg", "rpm")
            if _finite(result.get(k))
        },
        "geometry": _summarize(airplane),
        "mesh": mesh,
        "color": color,
        "scalars": _candidate_scalars(result, run, loads, airplane),
    }


def _stall_margins(result: dict, loads: dict, lifting_line, wing_panels) -> list | None:
    """The stall-margin channel, or None if this solve did not fit cl_max.

    `clmax_ab_used` comes back from `_solve_nlp` for every optimize member,
    but a frame written from a checkpoint, a hand-built result or a future
    caller may not carry it — and inventing a cl_max here (a NeuralFoil sweep
    of our own) would be a second, quietly different stall limit from the one
    the solve was constrained against. No fit, no channel.
    """
    clmax_ab = result.get("clmax_ab_used")
    try:
        if not clmax_ab or len(clmax_ab) < 2:
            return None
        return stall_margins(
            loads, float(result["V_ms"]), clmax_ab, wing_panels,
            float(lifting_line.op_point.atmosphere.density()),
        )
    except Exception as e:  # noqa: BLE001 — one channel, not the frame
        log.debug("live frames: stall margin unavailable: %s", e)
        return None


def _overlays(lifting_line, loads: dict, wing_panels, airplane) -> dict:
    """Wake streamlines and the lift distribution, each allowed to fail alone.

    Decoration on top of a frame that is already complete without them, and
    streamline tracing is the one thing here that steps through a
    near-singular velocity field. So each is tried separately and a failure
    costs that overlay, not the candidate frame and certainly not the solve.
    """
    overlays: dict = {}
    try:
        lines = streamlines_of(lifting_line)
        if lines:
            overlays["streamlines"] = lines
    except Exception as e:  # noqa: BLE001
        log.debug("live frames: streamlines unavailable: %s", e)
    try:
        span = float(airplane.wings[0].span()) if airplane.wings else 0.0
        lift = lift_distribution(lifting_line, loads, wing_panels, span)
        if lift:
            overlays["lift"] = lift
    except Exception as e:  # noqa: BLE001
        log.debug("live frames: lift distribution unavailable: %s", e)
    return overlays


def _candidate_scalars(result: dict, run: dict, loads: dict, airplane) -> dict:
    """The stats block's right-hand column, all measured at this design."""
    scalars = {
        k: float(result[k])
        for k in (
            "objective_value", "auw_kg", "x_cg_m", "static_margin", "P_elec_w",
            "motor_current_a", "throttle_frac", "drag_n", "J", "solve_minutes",
        )
        if _finite(result.get(k))
    }
    cl, cd = float(run["CL"]), float(run["CD"])
    scalars |= {"CL": cl, "CD": cd, "Cm": float(run["Cm"])}
    if cd > 0:
        scalars["L_over_D"] = cl / cd
    induced = loads.get("induced_drag_n")
    aspect = float(airplane.b_ref**2 / airplane.s_ref) if airplane.s_ref else 0.0
    if induced and aspect > 0:
        q = 0.5 * 1.225 * float(result["V_ms"]) ** 2
        cdi = induced / (q * float(airplane.s_ref))
        if cdi > 0:
            # Span efficiency wrt PROJECTED span, so a winglet's payoff shows
            # up as e > 1 rather than being hidden in the reference area.
            scalars["oswald_e"] = cl**2 / (math.pi * aspect * cdi)
    return scalars

def write_frame(path, body: dict) -> None:
    """One frame to disk, atomically.

    Write-then-rename, same idiom as `_SolveCache.put`: a reader must never see a
    half-written frame, and `frame_paths` only ever matches the frame pattern,
    which `.part` does not. The pid in the temp name is what lets two forked
    workers write into the same directory at once.

    Shared with `recolour`, which rewrites finished frames long after the solve —
    a second implementation of "land a frame safely" is exactly the kind of thing
    that stays correct in one place and rots in the other.
    """
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(body, fh, separators=(",", ":"))
    os.replace(tmp, path)


def _summarize(airplane) -> dict:
    """`geometry.summarize`, but never able to fail a frame.

    It is pure attribute arithmetic on a built aeroplane, so it costs well under
    a millisecond — but it is also the one call here that reaches into an
    aircraft-authored geometry mapping, and an infeasible iterate is exactly
    where such a mapping produces a value it cannot describe.
    """
    from . import geometry

    try:
        return geometry.summarize(airplane)
    except Exception:  # noqa: BLE001
        return {}
