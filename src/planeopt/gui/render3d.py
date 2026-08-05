"""Software 3D for the live viewer — QPainter only, no Qt addons, no OpenGL.

M5.4 (`docs/LIVE_VIEWER_PLAN.md` section 4.1). Qt3D, QtOpenGLWidgets and
QtCharts are all excluded from the bundle on purpose (`pyproject.toml`,
`packaging/planeopt.spec`), and none of them is needed: the model is a few
hundred flat quads, so a painter's-algorithm projector is a page of arithmetic
and draws faster than the window can ask for it.

Two properties are worth more than the code that buys them:

- **One code path for the widget and for the timelapse.** Everything here draws
  onto a `QPainter` and knows nothing about widgets, so the live window hands it
  its own painter and `planeopt timelapse` hands it a `QImage`'s. What you watch
  and what you export cannot drift apart.
- **The camera fit and colour range only ever GROW.** Re-fitting per frame makes
  a timelapse where the aeroplane pulses and the colours flicker, which reads as
  the design changing when it is only the normalisation. `ViewFit` and
  `ColorRange` are therefore stateful and monotone — a candidate frame re-anchors
  the colours (see `ColorRange.anchor`), nothing else shrinks them.

Depth handling is a painter's algorithm: quads sorted far-to-near by centroid
depth. It is exact for the separated surfaces of an aeroplane and can only
misorder quads that interpenetrate, which these do not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF

from ..liveframe import (
    MISSING,
    footnotes,
    header_text,
    lift_overlay,
    outline_points,
    quad_points,
    stats_columns,
    streamline_points,
)

# --- palette ---------------------------------------------------------------
# Matches the app stylesheet (`gui/window.py`) rather than inventing a second
# dark theme: the viewer is a window of the same application.
BACKGROUND = QColor("#131316")
PANEL_UNCOLORED = QColor("#5b6675")
WIREFRAME = QColor("#6e7686")
TEXT = QColor("#e4e4e7")
TEXT_DIM = QColor("#9a9aa0")
#: Overlays. Streamlines are cool and dim so the wake reads as air rather than
#: as structure; the lift curve is warm and bright because it is a measurement,
#: and its elliptical reference is deliberately colourless — the reference is not
#: a second result, it is the ruler the result is held against.
STREAMLINE = QColor("#7d8dd6")
LIFT_CURVE = QColor("#ffcf5c")
LIFT_STICK = QColor("#8a6f2a")
LIFT_REFERENCE = QColor("#9a9aa0")
#: For a value this frame does not carry, and for the footnote. Dim enough to
#: recede, light enough to READ — an em dash at #2a2a30 on #131316 is invisible,
#: which turns "this frame does not know that" into "that row is blank".
TEXT_FAINT = QColor("#6b6b74")
GRID = QColor("#3a3a42")

#: `turbo`, sampled at 33 anchors and interpolated to a 256-entry LUT. Turbo is
#: perceptually ordered — unlike `jet`, which has a false luminance peak in the
#: cyan and a dark band in the green — while still reading as the classic rainbow
#: an XFLR5 user expects on a loading plot. The anchors are matplotlib's own
#: values, so this is the real colormap and not an eyeballed lookalike.
_TURBO_ANCHORS = (
    ( 48,  18,  59), ( 57,  42, 115), ( 64,  64, 162), ( 68,  86, 199),
    ( 70, 107, 227), ( 70, 128, 246), ( 66, 148, 255), ( 55, 168, 250),
    ( 40, 188, 235), ( 28, 205, 216), ( 24, 221, 194), ( 31, 233, 175),
    ( 50, 242, 152), ( 78, 249, 125), (109, 254,  98), (139, 255,  75),
    (164, 252,  60), (185, 246,  53), (205, 236,  52), (223, 223,  55),
    (238, 207,  58), (248, 190,  57), (253, 172,  52), (254, 150,  43),
    (251, 126,  33), (244, 102,  23), (235,  80,  14), (223,  63,   8),
    (208,  47,   5), (190,  33,   2), (169,  22,   1), (146,  11,   1),
    (122,   4,   3),
)


def _build_turbo() -> list[QColor]:
    lut = []
    last = len(_TURBO_ANCHORS) - 1
    for i in range(256):
        pos = i / 255 * last
        lo = min(int(pos), last - 1)
        t = pos - lo
        a, b = _TURBO_ANCHORS[lo], _TURBO_ANCHORS[lo + 1]
        lut.append(QColor(*(round(a[k] + (b[k] - a[k]) * t) for k in range(3))))
    return lut


TURBO = _build_turbo()


def turbo(fraction: float) -> QColor:
    """Colour at `fraction` of the range, clamped to the ends."""
    if not math.isfinite(fraction):
        return PANEL_UNCOLORED
    return TURBO[max(0, min(255, int(fraction * 255)))]


# --- what the scalar dropdown offers ---------------------------------------
#: Name, label, unit. There is deliberately no "Cp" here: the IN-LOOP model is a
#: lifting line with one chordwise panel, so no chordwise pressure distribution
#: exists to plot (`liveframe`'s module docstring). A chordwise-resolved ΔCp from
#: an out-of-loop VLM is designed in LIVE_VIEWER_PLAN section 11 and would arrive
#: here as a fourth entry with its own mesh — not as a relabelling of these.
SCALARS = (
    ("cl", "local section cl", ""),
    ("stall_margin", "stall margin cl/cl_max", ""),
    ("gamma", "circulation Γ", "m²/s"),
    ("lift_per_span", "lift per span", "N/m"),
)
SCALAR_LABEL = {name: label for name, label, _ in SCALARS}
SCALAR_UNITS = {name: unit for name, _, unit in SCALARS}

#: Scalars whose range is FIXED rather than fitted to the data. Stall margin is
#: the only one, and it is the reason the channel is worth having: 1.0 is the
#: section limit, so the colour at a given margin has to mean the same thing in
#: every frame of every member. Fitting the range would make a wing at 0.4
#: everywhere look exactly as alarming as one at 0.99. Values above the range are
#: clipped to the top colour and the colorbar says so.
SCALAR_FIXED_RANGE = {"stall_margin": (0.0, 1.0)}


# --- camera ----------------------------------------------------------------


@dataclass(frozen=True)
class Camera:
    """An orbit camera with an ORTHOGRAPHIC projection.

    Orthographic rather than perspective for two reasons: it matches how XFLR5
    and every other panel-method viewer draws a wing, and it makes the
    painter's-algorithm artefacts rarer, because a quad's depth ordering no
    longer depends on where it sits in the frame.
    """

    #: Defaults are `VIEW_PRESETS[DEFAULT_VIEW]` — front-top-left. Model axes are
    #: x AFT, so an eye with negative x is ahead of the nose: yaw -145° puts it
    #: forward and to port, pitch +22° above. It was -35° (behind the tail) until
    #: 2026-08-05; the nose is the end of an aeroplane worth seeing, and from
    #: behind, a boom-tailed model is a tail with a wing behind it.
    yaw_deg: float = -145.0
    pitch_deg: float = 22.0
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    def basis(self) -> tuple[tuple, tuple, tuple]:
        """(screen right, screen up, toward-eye) in model axes.

        Model axes are AeroSandbox's: x aft, y right (starboard), z up.
        """
        yaw, pitch = math.radians(self.yaw_deg), math.radians(self.pitch_deg)
        eye = (
            math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw),
            math.sin(pitch),
        )
        # right = normalize(world_up x eye); world up is +z, so this is exact
        # everywhere except straight down the z axis, where every azimuth is the
        # same view and "right" has to be picked. `orbit` clamps short of the
        # pole so a dragging user cannot reach it — but the `plan` preset is
        # exactly 90°, and without this the basis collapses to zero and the model
        # projects to a single point.
        rx, ry = -eye[1], eye[0]
        norm = math.hypot(rx, ry)
        if norm < 1e-9:
            rx, ry, norm = -math.sin(yaw), math.cos(yaw), 1.0
        right = (rx / norm, ry / norm, 0.0)
        up = (
            eye[1] * right[2] - eye[2] * right[1],
            eye[2] * right[0] - eye[0] * right[2],
            eye[0] * right[1] - eye[1] * right[0],
        )
        return right, up, eye

    def orbit(self, d_yaw: float, d_pitch: float) -> "Camera":
        # Pitch is clamped short of the poles: at +-90 the "right" vector above
        # is undefined and the model would spin about nothing.
        return replace(
            self,
            yaw_deg=(self.yaw_deg + d_yaw) % 360.0,
            pitch_deg=max(-88.0, min(88.0, self.pitch_deg + d_pitch)),
        )

    def zoomed(self, factor: float) -> "Camera":
        return replace(self, zoom=max(0.15, min(12.0, self.zoom * factor)))

    def panned(self, dx: float, dy: float) -> "Camera":
        return replace(self, pan_x=self.pan_x + dx, pan_y=self.pan_y + dy)


#: The views offered in the New Run dialog, in the live window and to
#: `planeopt timelapse --view`. Name -> (label, camera).
#:
#: Four three-quarter corners and the three orthogonal elevations, because those
#: are the questions actually asked of this picture: a corner shows the aeroplane
#: as an object, `plan` shows planform and sweep, `front` shows dihedral, cant
#: and washout at the tip, `side` shows incidence and the boom. Model axes are x
#: AFT / y STARBOARD / z UP, so a negative-x eye is ahead of the nose.
#:
#: `plan` sits exactly on the pole, which `Camera.basis` handles explicitly. Its
#: yaw of 0 is what puts the nose at the top of the screen rather than sideways.
VIEW_PRESETS: dict[str, tuple[str, "Camera"]] = {
    "front-top-left": ("Front · top · left", Camera(yaw_deg=-145.0, pitch_deg=22.0)),
    "front-top-right": ("Front · top · right", Camera(yaw_deg=145.0, pitch_deg=22.0)),
    "rear-top-left": ("Rear · top · left", Camera(yaw_deg=-35.0, pitch_deg=22.0)),
    "rear-top-right": ("Rear · top · right", Camera(yaw_deg=35.0, pitch_deg=22.0)),
    "plan": ("Plan (from above)", Camera(yaw_deg=0.0, pitch_deg=90.0)),
    "front": ("Front elevation", Camera(yaw_deg=180.0, pitch_deg=0.0)),
    "side": ("Side elevation", Camera(yaw_deg=-90.0, pitch_deg=0.0)),
}

DEFAULT_VIEW = "front-top-left"
DEFAULT_CAMERA = VIEW_PRESETS[DEFAULT_VIEW][1]


def camera_from_view(name: str | None) -> Camera:
    """The camera for a preset name. Unknown or missing name -> the default."""
    entry = VIEW_PRESETS.get(name or "")
    return entry[1] if entry else DEFAULT_CAMERA


def view_of(camera: Camera) -> str | None:
    """The preset name this camera IS, or None if it has been orbited off one.

    Zoom and pan are ignored: a preset names a direction, and someone who zoomed
    in on the plan view is still looking at the plan view.
    """
    for name, (_, preset) in VIEW_PRESETS.items():
        if (
            abs((camera.yaw_deg - preset.yaw_deg + 180) % 360 - 180) < 0.05
            and abs(camera.pitch_deg - preset.pitch_deg) < 0.05
        ):
            return name
    return None


@dataclass
class ViewFit:
    """The model's bounding box, remembered across frames so it does not pulse.

    Grows only. A wing that shrinks over a solve would otherwise be re-fitted to
    fill the window at every iterate, so the one thing you are watching for —
    the geometry changing — would be normalised away.

    A BOX rather than a bounding sphere, because an aeroplane is nothing like a
    sphere: fitting the sphere to a 1.9 m span leaves a 0.2 m tall model
    occupying a tenth of the window's height. The box's eight corners are
    projected with the current camera, which fills the frame in the view
    actually on screen and still cannot pulse, since the box itself only grows.
    """

    box: list[list[float]] | None = None  # [[xmin,xmax],[ymin,ymax],[zmin,zmax]]

    def observe(self, points) -> None:
        points = list(points)
        if not points:
            return
        found = [
            [min(p[axis] for p in points), max(p[axis] for p in points)]
            for axis in range(3)
        ]
        if self.box is None:
            self.box = found
            return
        for axis in range(3):
            self.box[axis][0] = min(self.box[axis][0], found[axis][0])
            self.box[axis][1] = max(self.box[axis][1], found[axis][1])

    @property
    def centre(self) -> tuple[float, float, float]:
        if self.box is None:
            return (0.0, 0.0, 0.0)
        return tuple((lo + hi) / 2 for lo, hi in self.box)

    def corners(self) -> list[tuple[float, float, float]]:
        if self.box is None:
            return [(0.0, 0.0, 0.0)]
        (x0, x1), (y0, y1), (z0, z1) = self.box
        return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]

    def reset(self) -> None:
        self.box = None


@dataclass
class ColorRange:
    """The value range the colormap spans, held steady across a member.

    Expands with what it is shown and never contracts, so consecutive frames are
    comparable; a CANDIDATE frame re-anchors it, because that is the first frame
    of a member whose values are trustworthy and the point at which a stale range
    inherited from a previous member should stop applying.
    """

    lo: float | None = None
    hi: float | None = None

    def observe(self, values) -> None:
        finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
        if not finite:
            return
        self.lo = min(finite) if self.lo is None else min(self.lo, min(finite))
        self.hi = max(finite) if self.hi is None else max(self.hi, max(finite))

    def anchor(self, values) -> None:
        self.lo = self.hi = None
        self.observe(values)

    @property
    def valid(self) -> bool:
        return self.lo is not None and self.hi is not None and self.hi > self.lo

    def fraction(self, value: float) -> float:
        if not self.valid:
            return 0.5
        return (value - self.lo) / (self.hi - self.lo)


# --- projection ------------------------------------------------------------


class _Projector:
    """Model metres -> device pixels, plus the depth used to sort by."""

    #: Fraction of the drawing rectangle the model's projected extent fills at
    #: zoom 1, per axis. Not 1.0: rotating a filled-to-the-edge model clips it
    #: the instant it turns, and the margin is where the header and colorbar
    #: caption sit.
    FILL = 0.88

    def __init__(self, camera: Camera, fit: ViewFit, rect: QRectF) -> None:
        self.right, self.up, self.eye = camera.basis()
        self.centre = fit.centre
        flat = [self._flatten(c) for c in fit.corners()]
        width = max(p[0] for p in flat) - min(p[0] for p in flat)
        height = max(p[1] for p in flat) - min(p[1] for p in flat)
        self.scale = camera.zoom * self.FILL * min(
            rect.width() / max(width, 1e-6), rect.height() / max(height, 1e-6)
        )
        # Centre on the projected box, not on the 3D centroid: for a swept or
        # boom-tailed aeroplane those are not the same point, and it is the
        # picture that has to look centred.
        mid_x = (max(p[0] for p in flat) + min(p[0] for p in flat)) / 2
        mid_y = (max(p[1] for p in flat) + min(p[1] for p in flat)) / 2
        self.cx = rect.center().x() + camera.pan_x - mid_x * self.scale
        self.cy = rect.center().y() + camera.pan_y + mid_y * self.scale

    def _flatten(self, p) -> tuple[float, float]:
        dx = p[0] - self.centre[0]
        dy = p[1] - self.centre[1]
        dz = p[2] - self.centre[2]
        return (
            dx * self.right[0] + dy * self.right[1] + dz * self.right[2],
            dx * self.up[0] + dy * self.up[1] + dz * self.up[2],
        )

    def point(self, p) -> QPointF:
        sx, sy = self._flatten(p)
        # Screen y grows downward, model "up" grows upward.
        return QPointF(self.cx + sx * self.scale, self.cy - sy * self.scale)

    def depth(self, p) -> float:
        return (
            (p[0] - self.centre[0]) * self.eye[0]
            + (p[1] - self.centre[1]) * self.eye[1]
            + (p[2] - self.centre[2]) * self.eye[2]
        )


def _shade(color: QColor, factor: float) -> QColor:
    return QColor(
        max(0, min(255, int(color.red() * factor))),
        max(0, min(255, int(color.green() * factor))),
        max(0, min(255, int(color.blue() * factor))),
    )


def _lambert(quad, eye) -> float:
    """A mild diffuse term from the panel normal, for UNCOLORED frames only.

    An iterate frame has no scalar (that would cost a lifting-line run per IPOPT
    iteration), so without shading a wing is a flat silhouette and the dihedral,
    washout and cant — the things worth watching change — are invisible.
    A coloured frame is never shaded: darkening a colormap by geometry makes two
    panels of the same cl read as different values.
    """
    ax, ay, az = (quad[2][i] - quad[0][i] for i in range(3))
    bx, by, bz = (quad[3][i] - quad[1][i] for i in range(3))
    nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    if norm < 1e-12:
        return 0.85
    facing = abs((nx * eye[0] + ny * eye[1] + nz * eye[2]) / norm)
    return 0.62 + 0.38 * facing


# --- the one drawing entry point -------------------------------------------


#: Pens for the line layers, by tag. Segments of a streamline or a lift curve go
#: into the same depth-sorted list as the panels, so the wake passes BEHIND the
#: wing where it is behind it — a wake drawn as an afterthought on top is the
#: single thing that makes a 3D viewer read as a diagram.
_LINE_PENS = {
    "outline": (WIREFRAME, 1.0, Qt.SolidLine),
    "stream": (STREAMLINE, 1.0, Qt.SolidLine),
    "stick": (LIFT_STICK, 1.0, Qt.SolidLine),
    "lift": (LIFT_CURVE, 1.8, Qt.SolidLine),
    "reference": (LIFT_REFERENCE, 1.2, Qt.DashLine),
}


def _centroid(points):
    return tuple(sum(p[axis] for p in points) / len(points) for axis in range(3))


def _segments(polyline):
    """A polyline as consecutive pairs, so each piece sorts by its own depth.

    A streamline runs half a span downstream and a lift curve runs the whole
    span, so sorting either by one centroid puts the entire line in front of or
    behind the whole aeroplane. Segments cost a few hundred extra list entries
    and are the difference between a wake that wraps the wing and one that is
    painted over it.
    """
    return [polyline[i:i + 2] for i in range(len(polyline) - 1)]


def draw_model(
    painter: QPainter,
    rect: QRectF,
    frame: dict,
    camera: Camera,
    fit: ViewFit,
    values: list | None = None,
    color_range: ColorRange | None = None,
    show_streamlines: bool = True,
    show_lift: bool = False,
    clip: QRectF | None = None,
    wake_clip: QRectF | None = None,
) -> None:
    """Paint one frame's aeroplane into `rect`. Nothing else — no chrome.

    Two clips, because two things need protecting from each other. `clip` bounds
    everything and defaults to `rect`; the model, its outlines and the lift curve
    are all inside it by construction, since `ViewFit` is what `rect` was sized
    from. `wake_clip` is stricter and applies to the STREAMLINES alone — they are
    the one layer that deliberately runs past the model's own extent, so they are
    the one layer that has to be kept off the stats block. Clipping everything to
    the stricter rectangle would cut the tail off instead.
    """
    quads = quad_points(frame)
    if not quads:
        return
    projector = _Projector(camera, fit, rect)
    colored = bool(values) and color_range is not None and len(values) == len(quads)

    # Panels and every line layer go into ONE depth-sorted list.
    drawable = [(projector.depth(_centroid(q)), i, "quad", q) for i, q in enumerate(quads)]

    def add_lines(tag: str, polylines) -> None:
        for polyline in polylines:
            for segment in _segments(polyline):
                drawable.append((projector.depth(_centroid(segment)), None, tag, segment))

    add_lines("outline", outline_points(frame))
    if show_streamlines:
        add_lines("stream", streamline_points(frame))
    lift = lift_overlay(frame) if show_lift else None
    if lift:
        add_lines("stick", lift["sticks"])
        if lift["elliptical"]:
            add_lines("reference", [lift["elliptical"]])
        # The measurement goes in last of the lift layers, so where it coincides
        # with its own reference the answer is what you see.
        add_lines("lift", [lift["curve"]])

    # `depth` grows toward the eye, so ascending order paints the back of the
    # aeroplane first and lets the front overwrite it. The tie-break keeps the
    # order deterministic (two coincident panels must not swap between frames).
    drawable.sort(key=lambda entry: (entry[0], entry[1] is None, entry[1] or 0))

    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.save()
    model_clip = clip if clip is not None else rect
    clips = {"stream": wake_clip if wake_clip is not None else model_clip}
    # Set once per RUN of same-clip items rather than per item: the layers are
    # interleaved by depth, but in practice the wake sorts into a few blocks, so
    # this is a handful of clip changes and not one per segment.
    active = None
    for _, index, tag, points in drawable:
        want = clips.get(tag, model_clip)
        if want is not active:
            painter.setClipRect(want)
            active = want
        if tag != "quad":
            color, width, style = _LINE_PENS[tag]
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, width, style))
            painter.drawPolyline(QPolygonF([projector.point(p) for p in points]))
            continue
        value = values[index] if colored else None
        if value is None or not isinstance(value, (int, float)):
            # Either an uncoloured frame, or a strip this scalar does not apply
            # to — the stall margin is the wing airfoil's cl_max, so the tail and
            # the winglets have no honest value and are left plainly grey.
            fill = _shade(PANEL_UNCOLORED, _lambert(points, projector.eye))
        else:
            fill = turbo(color_range.fraction(value))
        # The 1 px darker stroke is what produces the paneled look — without it
        # adjacent quads of similar value merge into an unreadable wash.
        painter.setPen(QPen(_shade(fill, 0.62), 1.0))
        painter.setBrush(fill)
        painter.drawPolygon(QPolygonF([projector.point(p) for p in points]))
    painter.restore()


# --- chrome ----------------------------------------------------------------

MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "Monospace"]


def mono_font(size: int = 9) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(size)
    return font


COLORBAR_WIDTH = 16
COLORBAR_MARGIN = 14
COLORBAR_TICKS = 6


def draw_colorbar(
    painter: QPainter, rect: QRectF, color_range: ColorRange, scalar: str,
    stale: bool = False, over: bool = False,
) -> None:
    """Vertical colorbar with numeric labels, high value at the top.

    `stale` means this frame is UNCOLOURED (an iterate) and the scale belongs to
    the last member that converged. It is still drawn, faded and captioned as
    such: a bar that vanishes and returns as the run alternates between iterates
    and candidates makes the whole right-hand side of the window flicker, and
    the panels being plainly grey is what says the scale is not about them.
    """
    if not color_range.valid:
        return
    painter.setOpacity(0.4 if stale else 1.0)
    font = mono_font(8)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    height = max(80.0, rect.height() * 0.5)
    top = rect.top() + (rect.height() - height) / 2

    # ONE format across all the ticks, chosen from the range's own magnitude.
    # Per-tick `%g` gives "+0.5322" above "+0.413", which is a ragged column that
    # reads as inconsistent precision rather than as evenly spaced values.
    span = abs(color_range.hi - color_range.lo)
    biggest = max(abs(color_range.lo), abs(color_range.hi), span)
    if biggest >= 1000 or (biggest and biggest < 0.01):
        fmt = "{:+.2e}"
    else:
        fmt = "{:+.%df}" % max(1, min(4, 3 - int(math.floor(math.log10(span))) if span else 3))

    ticks = [
        (t / (COLORBAR_TICKS - 1),
         color_range.hi - (t / (COLORBAR_TICKS - 1)) * (color_range.hi - color_range.lo))
        for t in range(COLORBAR_TICKS)
    ]
    widest = max(metrics.horizontalAdvance(fmt.format(v)) for _, v in ticks)
    x = rect.right() - COLORBAR_MARGIN - widest - 6 - COLORBAR_WIDTH

    for i in range(int(height)):
        painter.setPen(QPen(turbo(1.0 - i / max(1.0, height - 1)), 1.0))
        painter.drawLine(QPointF(x, top + i), QPointF(x + COLORBAR_WIDTH, top + i))
    painter.setPen(QPen(GRID, 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(x, top, COLORBAR_WIDTH, height))

    painter.setPen(TEXT_DIM)
    for fraction, value in ticks:
        text = fmt.format(value)
        painter.drawText(
            QPointF(
                x + COLORBAR_WIDTH + 6 + widest - metrics.horizontalAdvance(text),
                top + fraction * height + metrics.ascent() / 2 - 1,
            ),
            text,
        )
    painter.setPen(TEXT)
    unit = SCALAR_UNITS.get(scalar, "")
    caption = SCALAR_LABEL.get(scalar, scalar)
    if unit:
        caption = f"{caption} [{unit}]"
    if scalar in SCALAR_FIXED_RANGE:
        # What the scale is ANCHORED to, because the ends of this bar are not
        # the ends of the data: a wing that never passes 0.66 must not read as
        # having reached the top of the colormap.
        caption = f"{caption} · 1.0 = stall"
        if over:
            caption = f"{caption}, >1 clipped"
    if stale:
        caption = f"{caption} — last candidate"
    painter.drawText(
        QPointF(
            min(x, rect.right() - COLORBAR_MARGIN - metrics.horizontalAdvance(caption)),
            top - 10,
        ),
        caption,
    )
    painter.setOpacity(1.0)


LEGEND_MARGIN = 14
LEGEND_SWATCH = 22


def draw_lift_legend(painter: QPainter, rect: QRectF, frame: dict) -> None:
    """Top-left key for the lift overlay, with what its height is worth.

    The curve is normalised to a fixed fraction of span so its SHAPE is what
    reads, which means the height is not a measurement until something says what
    the peak is. This is that something — without it the overlay is a picture of
    a distribution with no scale, and two members with very different loading
    would draw the same curve.
    """
    lift = lift_overlay(frame)
    if not lift:
        return
    font = mono_font(9)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    x = rect.left() + LEGEND_MARGIN
    y = rect.top() + LEGEND_MARGIN + metrics.ascent()
    peak, total = lift.get("peak_n_per_m"), lift.get("total_n")
    rows = (
        (LIFT_CURVE, 1.8, Qt.SolidLine,
         "lift/span" + (f" — peak {peak:.1f} N/m" if peak else "")
         + (f", wing total {total:.1f} N" if total else "")),
        (LIFT_REFERENCE, 1.2, Qt.DashLine, "elliptical — same lift, same span"),
    )
    for color, width, style, text in rows:
        painter.setPen(QPen(color, width, style))
        painter.drawLine(
            QPointF(x, y - metrics.ascent() / 3),
            QPointF(x + LEGEND_SWATCH, y - metrics.ascent() / 3),
        )
        painter.setPen(TEXT_DIM)
        painter.drawText(QPointF(x + LEGEND_SWATCH + 8, y), text)
        y += metrics.height()


STATS_MARGIN = 14
STATS_COLUMN_GAP = 26


def draw_stats(painter: QPainter, rect: QRectF, frame: dict) -> None:
    """The monospace block, bottom-left: geometry on the left, state on the right.

    A value this frame does not carry renders as an em dash rather than as the
    previous frame's number — an iterate has no CL, and showing the last
    candidate's beside a geometry that has moved since would be inventing one.
    """
    geometry, state = stats_columns(frame)
    font = mono_font(9)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    line = metrics.height()

    def column_width(rows):
        if not rows:
            return 0.0
        return (
            max(metrics.horizontalAdvance(label) for label, _ in rows)
            + 10
            + max(metrics.horizontalAdvance(value) for _, value in rows)
        )

    # Laid out from the BOTTOM up, so the block hugs the corner at any window
    # size and the 3D view keeps every pixel the text does not need.
    captions = footnotes(frame)
    footnote_y = rect.bottom() - STATS_MARGIN - line * (len(captions) - 1)
    last_row_y = footnote_y - line * 1.5
    rows = max(len(geometry), len(state))
    left = rect.left() + STATS_MARGIN
    left_w = column_width(geometry)

    for column, start, width in (
        (geometry, left, left_w),
        (state, left + left_w + STATS_COLUMN_GAP, column_width(state)),
    ):
        for i, (label, value) in enumerate(column):
            y = last_row_y - (len(column) - 1 - i) * line
            painter.setPen(TEXT_DIM)
            painter.drawText(QPointF(start, y), label)
            painter.setPen(TEXT if value != MISSING else TEXT_FAINT)
            painter.drawText(
                QPointF(start + width - metrics.horizontalAdvance(value), y), value
            )

    painter.setPen(TEXT)
    painter.drawText(
        QPointF(left, last_row_y - rows * line - line * 0.4), header_text(frame)
    )
    painter.setPen(TEXT_FAINT)
    for i, caption in enumerate(captions):
        painter.drawText(QPointF(left, footnote_y + i * line), caption)


def stats_block_size(painter: QPainter, frame: dict) -> tuple[float, float]:
    """How much room `draw_stats` will want, as (width, height) in pixels.

    Measured rather than guessed, so `render_frame` can hand the model a
    rectangle that the text will not land on. The block is monospace and its row
    count depends on which design variables this aircraft declares, so a
    constant would be wrong for every aircraft but one.
    """
    geometry, state = stats_columns(frame)
    metrics = QFontMetricsF(mono_font(9))

    def column_width(rows):
        if not rows:
            return 0.0
        return (
            max(metrics.horizontalAdvance(label) for label, _ in rows)
            + 10
            + max(metrics.horizontalAdvance(value) for _, value in rows)
        )

    rows = max(len(geometry), len(state))
    captions = footnotes(frame)
    width = max(
        column_width(geometry) + STATS_COLUMN_GAP + column_width(state),
        # A recoloured frame's second caption is a sentence, not a column, and it
        # is what sets the block's width — measure it rather than let it run out
        # under the model.
        max(metrics.horizontalAdvance(c) for c in captions),
    )
    # rows + header + footnotes, plus the gaps draw_stats leaves around them
    height = metrics.height() * (rows + 1.9 + len(captions)) + STATS_MARGIN
    return width + 2 * STATS_MARGIN, height


@dataclass
class RenderState:
    """Everything a repeated render must carry between frames."""

    camera: Camera = DEFAULT_CAMERA
    fit: ViewFit = field(default_factory=ViewFit)
    color_range: ColorRange = field(default_factory=ColorRange)
    scalar: str = "cl"
    show_streamlines: bool = True
    show_lift: bool = False

    def prepare(self, frame: dict) -> list | None:
        """Update the monotone fit/range for `frame` and return its values.

        IDEMPOTENT, deliberately: `observe` only ever widens and `anchor` resets
        to the same values, so calling this on the same frame twice changes
        nothing. That is what lets the live window update its range the moment a
        frame arrives while `render_frame` still calls it for the timelapse,
        without the two paths having to coordinate.
        """
        from ..liveframe import scalar_values

        quads = quad_points(frame)
        self.fit.observe([p for quad in quads for p in quad])
        self.fit.observe([p for line in outline_points(frame) for p in line])
        # The lift curve counts toward the fit whether or not it is being DRAWN,
        # because the fit is a property of the data and toggling an overlay must
        # not resize the aeroplane. Streamlines deliberately do not: they run
        # half a span downstream, so fitting them would shrink the model by a
        # third to make room for air.
        lift = lift_overlay(frame)
        if lift:
            self.fit.observe(lift["curve"])
        values = scalar_values(frame, self.scalar)
        fixed = SCALAR_FIXED_RANGE.get(self.scalar)
        if fixed is not None:
            self.color_range.lo, self.color_range.hi = fixed
        elif values:
            if frame.get("kind") == "candidate":
                self.color_range.anchor(values)
            else:
                self.color_range.observe(values)
        return values


#: How much of the stats block's height the MODEL is asked to stay out of. Less
#: than all of it on purpose: the block is a bottom-left corner, so a model
#: centred above its full height sits too high, and the aeroplane's own bounding
#: box keeps it clear of the text in practice. Ink that is NOT the aeroplane —
#: the wake, which spans the whole width — gets the full reservation instead.
_MODEL_STATS_RESERVE = 0.78


def model_rect(
    painter: QPainter, rect: QRectF, frame: dict, has_colorbar: bool,
    stats_reserve: float = _MODEL_STATS_RESERVE,
) -> QRectF:
    """The part of `rect` the aeroplane gets, once the chrome has had its share.

    The stats block and the colorbar are opaque text over a dark background, so
    a model drawn into the whole rectangle is centred on a point the reader
    cannot see and half-covered by numbers. Reserving their space first is what
    makes the aeroplane sit in the middle of the space it actually has.
    """
    stats_w, stats_h = stats_block_size(painter, frame)
    bar = 0.0
    if has_colorbar:
        metrics = QFontMetricsF(mono_font(8))
        bar = COLORBAR_MARGIN + COLORBAR_WIDTH + 6 + metrics.horizontalAdvance("+0.00000")
    return QRectF(
        rect.left(),
        rect.top(),
        max(80.0, rect.width() - bar),
        max(80.0, rect.height() - stats_h * stats_reserve),
    )


def ink_rect(painter: QPainter, rect: QRectF, frame: dict, state: "RenderState") -> QRectF:
    """Where drawing may leave ink: `rect` minus every piece of chrome, in full.

    Distinct from `model_rect`, which is only what the model is SIZED against.
    The wake runs past the model's own extent by design, so without a stricter
    clip it crosses the stats block — and the plan view, where a 1 m wake sits
    behind a 0.9 m aeroplane, is where that stopped being theoretical.
    """
    box = model_rect(painter, rect, frame, state.color_range.valid, stats_reserve=1.0)
    if not state.show_lift or not lift_overlay(frame):
        return box
    top = LEGEND_MARGIN + 2 * QFontMetricsF(mono_font(9)).height()
    return QRectF(box.left(), box.top() + top, box.width(), max(80.0, box.height() - top))


def render_frame(painter: QPainter, rect: QRectF, frame: dict, state: RenderState) -> None:
    """The whole picture: background, model, colorbar, stats.

    This is what the live widget paints and what the timelapse writes into a
    QImage, so the two cannot diverge.
    """
    painter.fillRect(rect, BACKGROUND)
    values = state.prepare(frame)
    # The colorbar's strip is reserved from the moment the range becomes valid
    # and never given back, even on the uncoloured iterate frames in between.
    # Reserving it per-frame instead would resize the model every time the run
    # crossed from an iterate to a candidate, which in a timelapse reads as the
    # aeroplane pulsing once per member.
    draw_model(
        painter, model_rect(painter, rect, frame, state.color_range.valid), frame,
        state.camera, state.fit, values, state.color_range,
        show_streamlines=state.show_streamlines, show_lift=state.show_lift,
        wake_clip=ink_rect(painter, rect, frame, state),
    )
    over = bool(values) and state.color_range.valid and any(
        isinstance(v, (int, float)) and v > state.color_range.hi for v in values
    )
    draw_colorbar(
        painter, rect, state.color_range, state.scalar, stale=not values, over=over
    )
    if state.show_lift:
        draw_lift_legend(painter, rect, frame)
    draw_stats(painter, rect, frame)
