"""Fill in the aerodynamics on a finished run's ITERATE frames, after the fact.

M5.7 (`docs/LIVE_VIEWER_PLAN.md` section 13). An iterate frame is geometry-only
because colouring it DURING the solve is what the plan's S2 spike refused: the
circulation is deep inside the Opti graph, and evaluating it there costs a
CasADi Function over a graph that peaks near 14.5 GB — once per iteration.

But that is an argument about *when*, not about *whether*. The colours on a
candidate frame come from a plain NUMERIC `asb.LiftingLine` on floats, which
never touches the Opti graph at all — and an iterate frame already carries
everything that run needs: the full design vector, and the velocity, alpha and
deflection IPOPT was holding at that iterate. So the same aerodynamics can be
computed later, from frames on disk, with the solve long finished and the
machine idle.

Measured on the 2026-08-05 nominal solve: **0.22 s per iterate** (median of 21,
range 0.19-0.50), so a whole 21-iterate run recolours in 4.8 s and a 500-frame
battery in under two minutes. Frames grow from ~3.3 KB to ~12 KB. Against the
~3% of solver wall time the same work would cost inside the callback — plus
competing for memory with a 13 GB peak, plus being unrepeatable — offline wins
on every axis, which is why this is a separate pass and not a `--colour-iterates`
flag on `optimize`.

**What the numbers mean, and the one thing to be careful about.** A recoloured
iterate is the true aerodynamics of *that geometry at the operating point IPOPT
was holding*. It is NOT a trimmed aircraft: lift does not equal weight and Cm is
not zero until the solve has satisfied those constraints, so iterate 0 of the
sample run reports a perfectly real `Cm = -1.35`. Watching that go to zero is the
point. Frames therefore carry `"recoloured": true` and the stats block says so,
because a CL on an iterate must not be read as a performance claim.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import liveframe

log = logging.getLogger("planeopt")

#: Marks a frame whose aerodynamics were filled in after the solve. Read by the
#: renderer, which captions it — see the module docstring for why that caption
#: is not optional.
MARK = "recoloured"

#: What is copied from the original frame rather than recomputed. The identity of
#: the frame (which member, which iterate, when) belongs to the solve that wrote
#: it; only the aerodynamics is being added.
_PRESERVED = ("schema", "label", "key", "member_index", "t_member_s", "iter", "kind")


def snapshot_aircraft(source) -> Path | None:
    """The aircraft module a run SNAPSHOTTED, if `source` is a finished run.

    Every run copies its inputs into `<run_dir>/inputs/` for reproducibility
    (EXECUTION_PLAN section 3 rule 2), which makes that copy the only definition
    guaranteed to be the one those frames came from. The definition in the
    working tree is a moving target: on 2026-08-05 the sample aircraft gained six
    design variables between a run finishing and its frames being recoloured, and
    the snapshot is what makes that a non-event rather than a refusal.

    Not always loadable: `inputs/` snapshots the FILES that were passed, not the
    package around them, so an aircraft that imports a sibling construction
    profile (`from lwpla_a1 import ...`) will not import from the snapshot alone.
    That is the run artifact's shape, not something to paper over here — callers
    try the snapshot and fall back to asking for `--aircraft`.
    """
    source = Path(source)
    run_dir = source.parent if source.name == "frames" else source
    snapshot = run_dir / "inputs" / "aircraft.py"
    return snapshot if snapshot.is_file() else None


class AircraftMismatch(RuntimeError):
    """The aircraft given does not have the design vector these frames do.

    Refused rather than worked around. Recolouring frames with a different
    aircraft module than the one that produced them would rebuild a DIFFERENT
    aeroplane from the same numbers and paint it under the original's name — the
    same failure shape as the `restore()` bug in LIVE_VIEWER_PLAN section 3: it
    would converge, look perfect, and be a picture of something else.
    """


def check_aircraft(frames: list[dict], aircraft) -> None:
    """Refuse early if the aircraft cannot be the one that wrote these frames."""
    declared = set(getattr(aircraft, "DV_DEFAULTS", None) or {})
    if not declared:
        return  # an aircraft that declares no defaults cannot be checked, so is not
    for frame in frames:
        carried = set(frame.get("dv") or {})
        if carried and carried != declared:
            missing = sorted(declared - carried)
            extra = sorted(carried - declared)
            raise AircraftMismatch(
                f"these frames carry a design vector this aircraft does not: "
                f"{len(carried)} variables against {len(declared)}"
                + (f", missing {', '.join(missing[:4])}" if missing else "")
                + (f", unexpected {', '.join(extra[:4])}" if extra else "")
                + ". Recolouring would draw a different aeroplane under this "
                "run's name — point --aircraft at the definition the run used."
            )
        return  # one frame settles it; they all come from the same solve


def recolour_frame(frame: dict, aircraft, clmax_ab=None) -> dict:
    """One frame with its aerodynamics filled in. Raises if it cannot be done.

    A candidate frame is returned untouched: it was already computed this way, by
    the solve, at the converged operating point, and recomputing it would only
    introduce a chance of disagreeing with the artifact.
    """
    if frame.get("kind") != "iterate":
        return frame
    state = frame.get("state") or {}
    if "V_ms" not in state or "alpha_deg" not in state:
        raise ValueError("this iterate carries no operating point to solve at")
    payload = liveframe.candidate_payload(aircraft, {
        "dv": frame["dv"],
        "V_ms": state["V_ms"],
        "alpha_deg": state["alpha_deg"],
        "deflection_deg": state.get("deflection_deg", 0.0),
        # Iterate frames carry no CG — it only moves the moment reference, and
        # every per-strip quantity drawn here is independent of it. Cm is not,
        # so it is reported about the nose rather than about an invented CG.
        "x_cg_m": state.get("x_cg_m", 0.0),
        # Not in the frame either: it is a per-AIRCRAFT constant the solve fits
        # once, so the caller passes it down rather than each frame carrying it.
        "clmax_ab_used": clmax_ab,
    })
    # The frame stays an ITERATE. It is one — this only adds what the solver was
    # too busy to compute. IPOPT's own numbers (inf_pr, inf_du, the surrogate
    # objective) are kept: they are about the solve, and nothing here recomputes
    # them.
    payload |= {k: frame[k] for k in _PRESERVED if k in frame}
    payload["scalars"] = payload.get("scalars", {}) | (frame.get("scalars") or {})
    payload[MARK] = True
    return payload


def recolour(
    source,
    aircraft,
    out=None,
    in_place: bool = False,
    clmax_ab=None,
    progress=None,
) -> dict:
    """Recolour every iterate frame in `source`. Returns what happened.

    Writes to `out` (default: `<source>-coloured` beside it) unless `in_place`.
    Not in place by default because the original frames are the record of what
    the solver actually saw, and this pass depends on an aircraft module that may
    have moved on since — LIVE_VIEWER_PLAN's reason for keeping frames as data is
    that a better renderer can re-render an old run, which needs the old run to
    still be there.

    A frame that cannot be recoloured is COPIED THROUGH unchanged and counted,
    never dropped and never half-written: an infeasible iterate with a negative
    chord is an ordinary event during a solve, and the geometry-only frame that
    the solver wrote for it is still the truth about that iterate.
    """
    source = Path(source)
    # A run directory keeps its frames in `frames/`; a live directory IS one.
    # Accepting both is what makes this work on a finished run and on a paused
    # one, the same way `timelapse` does.
    if not liveframe.frame_paths(source) and (source / "frames").is_dir():
        source = source / "frames"
    paths = liveframe.frame_paths(source)
    if not paths:
        raise FileNotFoundError(f"no frames in {source}")

    frames = [liveframe.read_frame(p) for p in paths]
    check_aircraft(frames, aircraft)

    destination = source if in_place else Path(out) if out else (
        source.parent / f"{source.name}-coloured"
    )
    destination.mkdir(parents=True, exist_ok=True)
    if not in_place and (view := liveframe.read_view(source)):
        # The chosen camera travels with the frames, or the copy would render
        # from the default view while the original rendered from the run's.
        liveframe.write_view(destination, view)

    t0 = time.monotonic()
    done = skipped = passed_through = 0
    for index, (path, frame) in enumerate(zip(paths, frames)):
        if frame.get("kind") != "iterate":
            passed_through += 1
            body = frame
        else:
            try:
                body = recolour_frame(frame, aircraft, clmax_ab)
                done += 1
            except Exception as e:  # noqa: BLE001 — one frame, not the pass
                log.debug("recolour: %s left as it was (%s)", path.name, e)
                skipped += 1
                body = frame
        liveframe.write_frame(destination / path.name, body)
        if progress is not None and (index % 10 == 0 or index == len(paths) - 1):
            progress(f"recoloured {index + 1} of {len(paths)} frames")

    elapsed = time.monotonic() - t0
    return {
        "source": source,
        "out_dir": destination,
        "frames": len(paths),
        "recoloured": done,
        "skipped": skipped,
        "already_coloured": passed_through,
        "seconds": round(elapsed, 1),
        "per_frame_s": round(elapsed / max(1, done), 3) if done else None,
    }
