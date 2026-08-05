"""Replay a run's frames into PNGs (and an MP4) — M5.4, plan section 6.

Through the SAME `render3d` code path the live window uses, so an exported
timelapse and the window it was watched in cannot disagree. Nothing here is
widget code: it paints into a `QImage`, which is why it works headless under
`QT_QPA_PLATFORM=offscreen` and why it needs no display on a build machine.

It lives under `planeopt.gui` because it needs Qt, not because it needs a GUI —
`cli.timelapse` imports it lazily so a CLI-only install is unaffected until
someone actually asks for a video.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from ..liveframe import frame_paths, read_frame, read_view
from . import render3d

DEFAULT_FPS = 30
DEFAULT_SIZE = (1920, 1080)

#: How many times a CANDIDATE frame is repeated, so a finished member lingers
#: instead of flashing past between two hundred iterates. Half a second at 30
#: fps. This is what makes a battery timelapse readable rather than a blur.
DEFAULT_HOLD_CANDIDATE = 15

_FFMPEG_ARGS = (
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
)


def parse_size(text: str) -> tuple[int, int]:
    """'1920x1080' -> (1920, 1080), forced even.

    H.264 with 4:2:0 chroma cannot encode an odd dimension, and the failure is a
    wall of ffmpeg text at the end of a long render rather than at the start.
    """
    try:
        width, height = (int(part) for part in text.lower().split("x", 1))
    except ValueError:
        raise ValueError(f"size must look like 1920x1080, not {text!r}") from None
    if width < 160 or height < 120:
        raise ValueError(f"{text} is too small to render a stats block into")
    return width - width % 2, height - height % 2


def select(directory, kind: str = "all") -> list[Path]:
    """The frames to replay, in order. `kind` is all | iterate | candidate."""
    paths = frame_paths(directory)
    if kind == "all":
        return paths
    if kind not in ("iterate", "candidate"):
        raise ValueError(f"kind must be all, iterate or candidate — not {kind!r}")
    # The kind is in the filename (`__final` vs `__iNNNN`), so this needs no
    # decompression: on a 5,000-frame battery that is the difference between an
    # instant listing and reading 50 MB to answer a question about names.
    return [p for p in paths if (p.name.split("__")[-1].startswith("final")) == (kind == "candidate")]


def resolve_camera(
    source, view: str | None, yaw: float | None, pitch: float | None
) -> tuple["render3d.Camera", str]:
    """The camera to render from, and a one-phrase account of where it came from.

    Precedence, most explicit first: `--yaw/--pitch`, then `--view NAME`, then
    the `view.json` the GUI recorded beside the frames, then the default. The
    sidecar is last-but-one on purpose — it is what someone chose before the run
    began, and a flag typed now is a later opinion about the same thing.

    The provenance string is returned rather than logged here because this is
    also what the CLI prints: a timelapse that silently came out in an
    unexpected view is a five-minute render to find out why.
    """
    if yaw is not None or pitch is not None:
        base = render3d.camera_from_view(view) if view else render3d.DEFAULT_CAMERA
        camera = replace(
            base,
            yaw_deg=base.yaw_deg if yaw is None else float(yaw),
            pitch_deg=base.pitch_deg if pitch is None else float(pitch),
        )
        return camera, f"yaw {camera.yaw_deg:g}°, pitch {camera.pitch_deg:g}°"
    if view:
        if view not in render3d.VIEW_PRESETS:
            raise ValueError(
                f"unknown view {view!r} — choose one of "
                f"{', '.join(render3d.VIEW_PRESETS)}, or give --yaw/--pitch"
            )
        return render3d.camera_from_view(view), f"--view {view}"
    stored = read_view(source)
    if stored:
        name = stored.get("view")
        camera = replace(
            render3d.camera_from_view(name),
            **{
                key: float(stored[key])
                for key in ("yaw_deg", "pitch_deg", "zoom", "pan_x", "pan_y")
                if isinstance(stored.get(key), (int, float))
            },
        )
        known = render3d.view_of(camera)
        return camera, f"the view chosen for this run ({known or 'custom'})"
    return render3d.DEFAULT_CAMERA, f"the default view ({render3d.DEFAULT_VIEW})"


def ensure_application():
    """A `QGuiApplication`, creating one offscreen if there is no display.

    QImage painting still needs a QGuiApplication for font handling, and a
    headless machine has no platform plugin to give it unless told.
    """
    from PySide6.QtGui import QGuiApplication

    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QGuiApplication([])


def render(
    source,
    out_dir=None,
    fps: int = DEFAULT_FPS,
    size: tuple[int, int] = DEFAULT_SIZE,
    scalar: str = "cl",
    kind: str = "all",
    hold_candidate: int = DEFAULT_HOLD_CANDIDATE,
    streamlines: bool = True,
    lift_distribution: bool = False,
    view: str | None = None,
    yaw: float | None = None,
    pitch: float | None = None,
    recolour_with=None,
    progress=None,
) -> dict:
    """Render `source`'s frames to `out_dir`. Returns what was produced."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    source = Path(source)
    # A run directory holds its frames in `frames/`; a live directory IS the
    # frame directory. Accepting both means the same command works during a run
    # and months later, which is the whole reason frames are data.
    default_out = source.parent / f"{source.name}-timelapse"
    if not frame_paths(source) and (source / "frames").is_dir():
        # A run's timelapse belongs INSIDE that run, beside `figures/` and
        # `frames/` — it is an artifact of that run, and a sibling directory
        # would break the rule that a run is one self-contained folder.
        default_out = source / "timelapse"
        source = source / "frames"
    frames = select(source, kind)
    if not frames:
        raise FileNotFoundError(f"no {kind} frames in {source}")

    out_dir = Path(out_dir) if out_dir else default_out
    out_dir.mkdir(parents=True, exist_ok=True)
    ensure_application()

    width, height = size
    rect = QRectF(0, 0, width, height)
    camera, camera_from = resolve_camera(source, view, yaw, pitch)
    state = render3d.RenderState(
        scalar=scalar, camera=camera, show_streamlines=streamlines,
        show_lift=lift_distribution,
    )

    # Pre-pass for the camera fit ONLY. `ViewFit` grows as it is shown geometry,
    # which is right for a live window (it cannot see the future) and wrong for
    # an export: the first frames would be fitted to a smaller aeroplane than
    # the last, so the model would appear to shrink through the video. Reading
    # every frame twice costs a few seconds against minutes of drawing.
    #
    # The colour range is deliberately NOT pre-passed: it re-anchors per
    # candidate, so each member is coloured over its own values with a colorbar
    # that says so. One range across a whole battery would flatten every member
    # into the same two colours.
    for path in frames:
        try:
            frame = read_frame(path)
            if recolour_with is not None:
                from .. import recolour as recolour_mod

                try:
                    frame = recolour_mod.recolour_frame(frame, recolour_with)
                except Exception:  # noqa: BLE001
                    pass
            state.prepare(frame)
        except (OSError, ValueError):
            continue
    state.color_range = render3d.ColorRange()

    written = 0
    skipped = 0
    recoloured = 0
    for index, path in enumerate(frames):
        try:
            frame = read_frame(path)
        except (OSError, ValueError):
            skipped += 1
            continue
        if recolour_with is not None:
            # In MEMORY, persisting nothing: this is the "I just want the video to
            # have colours" path, and it must not quietly rewrite a run's frames
            # as a side effect of rendering one. `planeopt recolour` is the
            # version that pays once and keeps the result.
            from .. import recolour as recolour_mod

            try:
                frame = recolour_mod.recolour_frame(frame, recolour_with)
                recoloured += 1
            except Exception:  # noqa: BLE001 — an infeasible iterate stays grey
                pass
        image = QImage(width, height, QImage.Format_RGB32)
        painter = QPainter(image)
        render3d.render_frame(painter, rect, frame, state)
        painter.end()
        repeats = hold_candidate if frame.get("kind") == "candidate" else 1
        for _ in range(max(1, repeats)):
            image.save(str(out_dir / f"frame_{written:06d}.png"))
            written += 1
        if progress is not None and (index % 25 == 0 or index == len(frames) - 1):
            progress(f"rendered {index + 1} of {len(frames)} frames -> {written} images")

    result = {
        "source": source,
        "out_dir": out_dir,
        "source_frames": len(frames),
        "images": written,
        "unreadable": skipped,
        "fps": fps,
        "size": (width, height),
        "camera_from": camera_from,
        "recoloured": recoloured,
        "video": None,
        "ffmpeg_command": _ffmpeg_command(out_dir, fps),
    }
    result["video"] = _encode(out_dir, fps, progress)
    return result


def _ffmpeg_command(out_dir: Path, fps: int) -> str:
    return " ".join([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(out_dir / "frame_%06d.png"), *_FFMPEG_ARGS,
        str(out_dir / "timelapse.mp4"),
    ])


def _encode(out_dir: Path, fps: int, progress=None) -> Path | None:
    """Assemble the PNGs if ffmpeg is here; otherwise say what to run.

    ffmpeg is not a dependency and will not become one — it is 80 MB of codecs
    for a convenience, and the PNGs are the actual artifact. A missing encoder
    therefore prints the exact command rather than failing the render.
    """
    if shutil.which("ffmpeg") is None:
        return None
    target = out_dir / "timelapse.mp4"
    command = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(out_dir / "frame_%06d.png"), *_FFMPEG_ARGS, str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError) as e:
        if progress is not None:
            progress(f"ffmpeg failed ({e}); the PNGs are intact")
        return None
    return target
