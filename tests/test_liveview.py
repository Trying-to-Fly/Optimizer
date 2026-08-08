"""The live viewer's Qt half — renderer, window model, timelapse.

Runs offscreen (`QT_QPA_PLATFORM=offscreen`), so there is no display anywhere in
here. That is the same property the timelapse renderer needs to work on a build
machine, so testing it this way is also testing that.

The image tests sample PIXELS rather than comparing against a committed golden
PNG. A golden would be the stricter gate on paper and the weaker one in
practice: font hinting and antialiasing differ between Qt builds and platforms,
so it would either need a tolerance loose enough to hide a real regression or it
would fail on machines where nothing is wrong. What is asserted instead is what
the picture has to MEAN — this quad is this colour, the near surface wins over
the far one, the model is inside its rectangle.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="the live viewer needs the `gui` extra")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planeopt import liveframe  # noqa: E402
from planeopt.gui import render3d, timelapse  # noqa: E402

SIZE = (640, 480)


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


# --- canned frames (no aerosandbox: this half must not need a solver) -----

#: One quad in the z = 0 plane out at y > 0, and one directly behind it in x.
#: Two panels is enough to test ordering, colouring and projection, and keeping
#: the fixture hand-written keeps these tests independent of any aircraft.
def _frame(kind="candidate", values=(0.2, 0.8), **overrides) -> dict:
    def quad(x0, y0):
        return [
            (x0, y0, 0.0), (x0 + 0.2, y0, 0.0),
            (x0 + 0.2, y0 + 0.4, 0.0), (x0, y0 + 0.4, 0.0),
        ]

    flat = []
    for corners in (quad(0.0, 0.1), quad(0.0, -0.5)):
        for point in corners:
            flat += [int(round(c * liveframe.COORD_SCALE)) for c in point]
    frame = {
        "schema": 1, "kind": kind, "label": "multistart", "key": "nominal",
        "member_index": [1, 3], "t_member_s": 12.0,
        "dv": {"c_root": 0.2, "taper": 0.7},
        "state": {"V_ms": 11.0, "alpha_deg": 4.0},
        "geometry": {"span_m": 1.0, "area_m2": 0.16, "aspect_ratio": 6.25},
        "mesh": {"quads": flat, "surface_of": [0, 0], "surfaces": ["wing"]},
        "scalars": {"CL": 0.6, "CD": 0.03, "L_over_D": 20.0, "auw_kg": 1.5},
    }
    if kind == "iterate":
        frame["iter"] = 4
        frame["scalars"] = {"inf_pr": 0.05, "ipopt_objective": -118.0}
    elif values is not None:
        frame["color"] = {
            "name": "cl", "values": list(values),
            "all": {
                "cl": list(values),
                "gamma": [v * 2 for v in values],
                "lift_per_span": [v * 10 for v in values],
            },
        }
    frame.update(overrides)
    return frame


def _write(directory: Path, name: str, frame: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(frame, fh)
    return path


def _render(frame, state=None, size=SIZE) -> QImage:
    image = QImage(size[0], size[1], QImage.Format_RGB32)
    painter = QPainter(image)
    render3d.render_frame(
        painter, QRectF(0, 0, size[0], size[1]), frame, state or render3d.RenderState()
    )
    painter.end()
    return image


# --- projection and camera maths (no painting) ----------------------------


def test_the_camera_basis_is_orthonormal():
    for yaw, pitch in ((-35.0, 22.0), (0.0, 0.0), (140.0, -60.0), (315.0, 88.0)):
        right, up, eye = render3d.Camera(yaw_deg=yaw, pitch_deg=pitch).basis()
        for vector in (right, up, eye):
            assert sum(c * c for c in vector) == pytest.approx(1.0, abs=1e-9)
        for a, b in ((right, up), (up, eye), (eye, right)):
            assert sum(x * y for x, y in zip(a, b)) == pytest.approx(0.0, abs=1e-9)


def test_pitch_is_clamped_short_of_the_pole():
    """At +-90 degrees the 'right' vector is undefined and the model spins."""
    camera = render3d.Camera(pitch_deg=80.0).orbit(0, 40.0)
    assert camera.pitch_deg == pytest.approx(88.0)
    assert render3d.Camera(pitch_deg=-80.0).orbit(0, -40.0).pitch_deg == pytest.approx(-88.0)


def test_the_view_fit_grows_and_never_shrinks():
    fit = render3d.ViewFit()
    fit.observe([(0, -1, 0), (0, 1, 0)])
    wide = fit.box[1][1]
    fit.observe([(0, -0.1, 0), (0, 0.1, 0)])
    assert fit.box[1][1] == wide, "a shrinking wing must not re-fill the window"
    fit.observe([(0, 0, 0), (0, 2, 0)])
    assert fit.box[1][1] == pytest.approx(2.0)


def test_the_colour_range_expands_but_a_candidate_re_anchors_it():
    rng = render3d.ColorRange()
    rng.observe([0.1, 0.5])
    rng.observe([0.3])
    assert (rng.lo, rng.hi) == (0.1, 0.5)
    rng.observe([-0.2, 0.9])
    assert (rng.lo, rng.hi) == (-0.2, 0.9)
    rng.anchor([0.0, 1.0])
    assert (rng.lo, rng.hi) == (0.0, 1.0)
    assert rng.fraction(0.5) == pytest.approx(0.5)


def test_a_degenerate_colour_range_does_not_divide_by_zero():
    rng = render3d.ColorRange()
    rng.observe([0.4, 0.4])
    assert not rng.valid
    assert rng.fraction(0.4) == 0.5
    rng.observe([float("nan")])
    assert rng.lo == 0.4


def test_turbo_is_ordered_and_clamped():
    assert render3d.turbo(-5.0) == render3d.turbo(0.0)
    assert render3d.turbo(5.0) == render3d.turbo(1.0)
    # Turbo runs dark blue -> cyan -> yellow -> dark red. Its middle is the
    # bright end; that is the property that makes it readable where jet is not.
    assert render3d.turbo(0.5).green() > render3d.turbo(0.0).green()
    assert render3d.turbo(0.5).green() > render3d.turbo(1.0).green()
    assert render3d.turbo(1.0).red() > render3d.turbo(0.0).red()


def test_there_is_no_cp_option():
    """No chordwise pressure exists on a one-chordwise-panel lifting line."""
    assert "cp" not in {name.lower() for name, _, _ in render3d.SCALARS}


def test_the_stall_margin_scale_is_fixed_so_a_colour_means_one_thing(qt_app):
    """Fitting the range would make a wing at 0.4 look as alarming as one at 0.99."""
    state = render3d.RenderState(scalar="stall_margin")
    state.prepare(_frame(values=None, color={
        "name": "cl", "values": [0.1, 0.2],
        "all": {"cl": [0.1, 0.2], "stall_margin": [0.30, 0.42]},
    }))
    assert (state.color_range.lo, state.color_range.hi) == (0.0, 1.0)
    # ... and it is still 0..1 for a frame whose values are much higher, so the
    # two frames are comparable at a glance, which is the whole point.
    state.prepare(_frame(values=None, color={
        "name": "cl", "values": [0.1, 0.2],
        "all": {"cl": [0.1, 0.2], "stall_margin": [0.90, 0.98]},
    }))
    assert (state.color_range.lo, state.color_range.hi) == (0.0, 1.0)


def test_a_strip_the_scalar_does_not_apply_to_is_grey_not_an_end_of_the_colormap(qt_app):
    """The stall margin is the WING airfoil's limit; a None strip has no value,
    and painting it dark blue would read as `margin 0`, the safest wing there is."""
    frame = _frame(values=None, color={
        "name": "stall_margin", "values": [0.5, None],
        "all": {"stall_margin": [0.5, None]},
    })
    image = _render(frame, render3d.RenderState(scalar="stall_margin"))
    colours = {QColor(image.pixel(x, y)).name()
               for x in range(image.width()) for y in range(image.height())}
    assert render3d.turbo(0.5).name() in colours, "the strip that HAS a value"
    assert render3d.turbo(0.0).name() not in colours
    greys = [c for c in colours if QColor(c).saturation() < 90]
    assert len(greys) > 3, "the strip without one is shaded grey"


def test_every_preset_view_gives_a_usable_basis():
    """`plan` sits exactly on the pole, where the naive cross product is zero."""
    for name, (_, camera) in render3d.VIEW_PRESETS.items():
        right, up, eye = camera.basis()
        for axis in (right, up, eye):
            assert sum(c * c for c in axis) == pytest.approx(1.0), name
        # orthogonal, so the projection cannot collapse the model to a line
        assert sum(right[i] * up[i] for i in range(3)) == pytest.approx(0.0, abs=1e-9)
        assert render3d.view_of(camera) == name


def test_orbiting_off_a_preset_stops_naming_it():
    """A combo that keeps saying "Plan" while you look from an angle is a lie."""
    plan = render3d.camera_from_view("plan")
    assert render3d.view_of(plan.orbit(30.0, 0.0)) is None
    # Zoom and pan are not a different VIEW, though — the name is a direction.
    assert render3d.view_of(plan.zoomed(2.0).panned(40, 10)) == "plan"
    assert render3d.camera_from_view("no-such-view") is render3d.DEFAULT_CAMERA


# --- painting -------------------------------------------------------------


def test_a_coloured_frame_paints_the_colormaps_ends_at_the_data_ends(qt_app):
    """The low quad must be the low colour and the high quad the high one."""
    image = _render(_frame(values=(0.0, 1.0)))
    colours = {QColor(image.pixel(x, y)).name()
               for x in range(image.width()) for y in range(image.height())}
    assert render3d.turbo(0.0).name() in colours
    assert render3d.turbo(1.0).name() in colours


def test_an_iterate_frame_is_shaded_grey_rather_than_coloured(qt_app):
    """Colouring an iterate would cost a lifting-line run per IPOPT iteration."""
    image = _render(_frame(kind="iterate"))
    colours = {QColor(image.pixel(x, y)).name()
               for x in range(image.width()) for y in range(image.height())}
    assert render3d.turbo(0.0).name() not in colours
    assert render3d.turbo(1.0).name() not in colours
    greys = [c for c in colours if QColor(c).saturation() < 90]
    assert len(greys) > 3, "the panel should be shaded, so it reads as 3D"


def test_the_nearer_panel_wins_where_two_overlap(qt_app):
    """Painter's algorithm: far to near, so the front of the model survives."""
    near = [(0.0, 0.0, 0.30), (0.4, 0.0, 0.30), (0.4, 0.4, 0.30), (0.0, 0.4, 0.30)]
    far = [(0.0, 0.0, -0.30), (0.4, 0.0, -0.30), (0.4, 0.4, -0.30), (0.0, 0.4, -0.30)]
    flat = []
    for quad in (far, near):  # deliberately in the WRONG order in the file
        for point in quad:
            flat += [int(round(c * liveframe.COORD_SCALE)) for c in point]
    frame = _frame(values=(0.0, 1.0))
    frame["mesh"]["quads"] = flat

    def centre_colour(values):
        frame = _frame(values=values)
        frame["mesh"]["quads"] = flat
        # Looking from almost straight above, the two quads project onto each
        # other; the pixel at their shared centroid is whichever one won.
        state = render3d.RenderState(
            camera=render3d.Camera(yaw_deg=0.0, pitch_deg=88.0)
        )
        image = _render(frame, state)
        state.prepare(frame)
        painter = QPainter(image)
        model = render3d.model_rect(painter, QRectF(0, 0, *SIZE), frame, True)
        painter.end()
        centre = render3d._Projector(state.camera, state.fit, model).point((0.2, 0.2, 0.0))
        return QColor(image.pixel(int(centre.x()), int(centre.y()))).name()

    assert centre_colour((0.0, 1.0)) == render3d.turbo(1.0).name(), "the near quad wins"
    # Swap the values and the same pixel must follow the NEAR quad, not the
    # high value — otherwise this would pass on a renderer with no depth sort.
    assert centre_colour((1.0, 0.0)) == render3d.turbo(0.0).name()


def test_the_model_stays_clear_of_the_stats_block(qt_app):
    """The stats block is opaque text; the aeroplane must not be drawn under it."""
    frame = _frame()
    image = _render(frame)
    painter = QPainter(image)
    stats_w, stats_h = render3d.stats_block_size(painter, frame)
    model = render3d.model_rect(
        painter, QRectF(0, 0, *SIZE), frame, has_colorbar=True
    )
    painter.end()

    # The colorbar legitimately reaches down the right-hand side, so the claim
    # is about the block's own corner: nothing of the model under the text.
    panel_pixels = [
        (x, y)
        for y in range(int(image.height() - stats_h * 0.78), image.height())
        # A headless build machine may expose no system fonts, in which case
        # Qt's missing-glyph metrics can make the nominal text block wider than
        # the image. QImage.pixel() outside the image returns an error colour
        # that is highly saturated, which used to look like thousands of model
        # pixels behind the stats even though every reported x was off-canvas.
        # Restrict the check to the rectangle in which model ink is allowed.
        # This also excludes the legitimate colorbar when missing-glyph metrics
        # make the nominal stats width span the whole headless image.
        for x in range(min(int(model.right()) + 1, int(stats_w)))
        # anything strongly saturated in that corner would be a panel
        if QColor(image.pixel(x, y)).saturation() > 120
    ]
    assert not panel_pixels, f"{len(panel_pixels)} model pixels behind the stats"
    assert (image.pixel(2, 2) & 0xFFFFFF) == (render3d.BACKGROUND.rgb() & 0xFFFFFF)


def test_every_projected_vertex_lands_inside_the_widget(qt_app):
    """A model that is clipped at the default camera is a fit bug, not a view."""
    frame = _frame()
    state = render3d.RenderState()
    state.prepare(frame)
    rect = QRectF(0, 0, *SIZE)
    image = QImage(SIZE[0], SIZE[1], QImage.Format_RGB32)
    painter = QPainter(image)
    model = render3d.model_rect(painter, rect, frame, True)
    painter.end()

    projector = render3d._Projector(state.camera, state.fit, model)
    for quad in liveframe.quad_points(frame):
        for point in quad:
            projected = projector.point(point)
            assert 0 <= projected.x() <= SIZE[0]
            assert 0 <= projected.y() <= SIZE[1]


# --- the overlays ---------------------------------------------------------


def _encode(points) -> list[int]:
    return [int(round(c * liveframe.COORD_SCALE)) for p in points for c in p]


#: A wake that dives a long way below the model, which is what the real thing
#: does from the plan view: a 1 m streamline behind a 0.9 m aeroplane.
_LONG_WAKE = [_encode([(0.0, 0.0, 0.0), (0.0, 0.0, -5.0)])]


def _ink_of(frame, size=SIZE, **flags) -> list[tuple[int, int]]:
    """Which pixels a layer put down, by rendering with it off and differencing.

    Not "which pixels are the pen colour": these are 1 px antialiased lines, so
    a diagonal one is blended with the background at every pixel and matches its
    own pen almost nowhere. Differencing finds the ink wherever it landed and at
    whatever blend, and asks exactly the question the toggle is for.
    """
    without = _render(frame, render3d.RenderState(show_streamlines=False), size=size)
    with_it = _render(frame, render3d.RenderState(**flags), size=size)
    return [
        (x, y)
        for y in range(size[1]) for x in range(size[0])
        if without.pixel(x, y) != with_it.pixel(x, y)
    ]


def test_the_wake_is_drawn_only_when_it_is_asked_for(qt_app):
    frame = _frame(overlays={"streamlines": _LONG_WAKE})
    assert _ink_of(frame, show_streamlines=True)
    assert not _ink_of(frame, show_streamlines=False)


def test_the_wake_is_clipped_off_the_stats_block(qt_app):
    """The one layer that deliberately overruns the model's own extent.

    Found by looking at a real plan-view render, where the wake ran off the
    bottom of the canvas and straight through the numbers.
    """
    frame = _frame(overlays={"streamlines": _LONG_WAKE})
    image = QImage(SIZE[0], SIZE[1], QImage.Format_RGB32)
    painter = QPainter(image)
    stats_w, stats_h = render3d.stats_block_size(painter, frame)
    painter.end()

    trespassing = [
        (x, y) for x, y in _ink_of(frame, show_streamlines=True)
        if y >= SIZE[1] - stats_h and x <= stats_w
    ]
    assert not trespassing, f"{len(trespassing)} wake pixels over the stats block"


def test_the_wake_does_not_shrink_the_model_but_the_lift_curve_does_count(qt_app):
    """Both are overlays; only one is a claim about how big the aeroplane is.

    A wake runs half a span downstream, so fitting it would shrink the model by a
    third to make room for air. The lift curve sits over the wing and would be
    cut off if the fit ignored it — and it counts whether or not it is being
    DRAWN, so toggling the overlay cannot resize the aeroplane.
    """
    curve = _encode([(0.0, -0.4, 0.9), (0.0, 0.4, 0.9)])
    frame = _frame(overlays={
        "streamlines": _LONG_WAKE,
        "lift": {"sticks": [], "curve": curve, "elliptical": [],
                 "peak_n_per_m": 8.0, "total_n": 15.0},
    })
    for show_lift in (False, True):
        state = render3d.RenderState(show_lift=show_lift)
        state.prepare(frame)
        (_, _), (_, _), (z_lo, z_hi) = state.fit.box
        assert z_hi == pytest.approx(0.9), "the lift curve is inside the fit"
        assert z_lo > -5.0, "the wake is not"


def test_the_lift_legend_says_what_the_curves_height_is_worth(qt_app):
    """Normalised height is a shape, not a measurement, until something says so."""
    frame = _frame(overlays={"lift": {
        "sticks": [], "curve": _encode([(0.0, -0.4, 0.9), (0.0, 0.4, 0.9)]),
        "elliptical": [], "peak_n_per_m": 8.25, "total_n": 15.5,
    }})
    size = (900, 600)
    plain = _render(frame, render3d.RenderState(show_streamlines=False), size=size)
    shown = _render(
        frame, render3d.RenderState(show_streamlines=False, show_lift=True), size=size
    )
    top_left = [
        (x, y) for y in range(60) for x in range(400)
        if plain.pixel(x, y) != shown.pixel(x, y)
    ]
    assert top_left, "the legend, with the peak in N/m, is drawn"
    # And the wake is kept out of the rows it occupies, for the same reason it is
    # kept off the stats block.
    painter = QPainter(shown)
    ink = render3d.ink_rect(
        painter, QRectF(0, 0, *size), frame, render3d.RenderState(show_lift=True)
    )
    painter.end()
    assert ink.top() > 0


def test_rendering_a_frame_with_no_mesh_does_not_raise(qt_app):
    frame = _frame()
    frame["mesh"] = {"quads": [], "surface_of": [], "surfaces": []}
    _render(frame)  # the stats block still draws; nothing explodes


# --- the window's frame stream (no solver, no run) ------------------------


def test_the_window_follows_the_newest_frame_and_ignores_partials(qt_app, tmp_path):
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__i0001.json.gz", _frame(kind="iterate"))
    (live / "f000001__multistart__nominal__i0002.json.gz.7.part").write_bytes(b"junk")

    window = LiveViewWindow()
    window.watch(live, live=True)
    assert window.view.frame["iter"] == 4
    assert window.slider.maximum() == 0, "the half-written frame is not a frame"

    newest = _frame(kind="candidate")
    _write(live, "f000002__multistart__nominal__final.json.gz", newest)
    window.rescan()
    assert window.view.frame["kind"] == "candidate"
    assert window.slider.value() == 1
    window.close()


def test_status_separates_total_frames_from_the_current_member_iteration(
    qt_app, tmp_path
):
    """The real regression: total frame 338 was only mass-bump iteration 9."""
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    frame = _frame(
        kind="iterate", label="multistart", key="mass_bump",
        member_index=[4, 4], iter=9, t_member_s=138.2,
    )
    _write(live, "f000337__multistart__mass_bump__i0009.json.gz", frame)

    window = LiveViewWindow()
    window.watch(live, live=True)
    status = window.status.text()
    assert "total frame 1/1" in status
    assert "multistart [4/4] mass_bump" in status
    assert "iter 9" in status
    assert "t+138 s" in status
    window.close()


def test_dragging_the_slider_is_what_stops_following(qt_app, tmp_path):
    """One gesture: the checkbox reports the mode, it does not gate the slider."""
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    for i in range(4):
        _write(live, f"f{i:06d}__multistart__nominal__i{i:04d}.json.gz",
               _frame(kind="iterate", iter=i))

    window = LiveViewWindow()
    window.watch(live, live=True)
    assert window.follow.isChecked()
    assert window.slider.isEnabled(), "the slider is never dead"

    window.slider.setValue(1)
    assert not window.follow.isChecked()
    assert window.view.frame["iter"] == 1

    # A frame arriving while frozen must NOT be mistaken for another drag.
    _write(live, "f000009__multistart__nominal__i0009.json.gz", _frame(kind="iterate", iter=9))
    window.rescan()
    assert window.view.frame["iter"] == 1
    window.close()


def test_unfollowing_freezes_the_view_and_enables_scrubbing(qt_app, tmp_path):
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    for i in range(4):
        _write(live, f"f{i:06d}__multistart__nominal__i{i:04d}.json.gz",
               _frame(kind="iterate", iter=i))

    window = LiveViewWindow()
    window.watch(live, live=True)
    assert window.view.frame["iter"] == 3

    window.follow.setChecked(False)
    window.slider.setValue(1)
    assert window.view.frame["iter"] == 1

    _write(live, "f000009__multistart__nominal__i0009.json.gz", _frame(kind="iterate", iter=9))
    window.rescan()
    assert window.view.frame["iter"] == 1, "a frozen view must stay frozen"

    # Ticking it again catches back up to whatever arrived meanwhile.
    window.follow.setChecked(True)
    assert window.view.frame["iter"] == 9
    window.close()


def test_the_window_follows_frames_that_move_into_the_run_directory(qt_app, tmp_path):
    """`liveframe.relocate` empties the live directory when a run succeeds."""
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    run_dir = tmp_path / "20260805T120000-run"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())

    window = LiveViewWindow()
    window.watch(live, run_dir, live=True)
    assert window.view.frame is not None

    liveframe.relocate(live, run_dir)
    window.rescan()
    assert window.directory == run_dir / "frames"
    assert window.view.frame is not None
    window.close()


def test_switching_scalar_re_reads_what_the_frame_already_carries(qt_app, tmp_path):
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame(values=(0.2, 0.8)))

    window = LiveViewWindow()
    window.watch(live, live=True)
    window.scalar.setCurrentIndex(
        [i for i in range(window.scalar.count()) if window.scalar.itemData(i) == "gamma"][0]
    )
    assert window.view.state.scalar == "gamma"
    # gamma is 2x cl in the fixture, so the range must have followed the switch
    # rather than keeping cl's numbers under gamma's label.
    assert window.view.state.color_range.hi == pytest.approx(1.6)
    window.close()


def test_toggling_an_overlay_repaints_without_reloading_the_frame(qt_app, tmp_path):
    """Both overlays are already in the frame the view is holding."""
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())
    _write(live, "f000001__multistart__nominal__final.json.gz", _frame())

    window = LiveViewWindow()
    window.watch(live, live=True)
    window.follow.setChecked(False)
    window.slider.setValue(0)

    window.lift_curve.setChecked(True)
    assert window.view.state.show_lift
    assert window.slider.value() == 0, "scrubbing position survives the toggle"
    window.streamlines.setChecked(False)
    assert not window.view.state.show_streamlines
    assert window.slider.value() == 0
    window.close()


# --- choosing the timelapse view -----------------------------------------


def test_the_window_opens_at_the_view_the_run_was_queued_with(qt_app, tmp_path):
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())
    liveframe.write_view(live, {"view": "plan"})

    window = LiveViewWindow()
    window.watch(live, live=True)
    assert render3d.view_of(window.view.state.camera) == "plan"
    assert window.view_preset.currentData() == "plan"
    # ... and a double-click comes back to THAT view, not to a global default:
    # "reset" means "back to how this opened".
    window.view.state.camera = window.view.state.camera.orbit(40.0, 5.0)
    window.view.reset_camera()
    assert render3d.view_of(window.view.state.camera) == "plan"
    window.close()


def test_orbiting_reports_custom_without_rewriting_the_runs_view(qt_app, tmp_path):
    """The live camera is the user's to move; the stored one is theirs to SET."""
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())
    liveframe.write_view(live, {"view": "side"})

    window = LiveViewWindow()
    window.watch(live, live=True)
    window.view.state.camera = window.view.state.camera.orbit(37.0, 11.0)
    window.view.camera_changed.emit()
    assert window.view_preset.currentText() == "Custom"
    assert liveframe.read_view(live)["view"] == "side", "unchanged until asked"

    window._adopt_view()
    stored = liveframe.read_view(live)
    assert stored["view"] is None, "a custom angle has no preset name"
    assert stored["yaw_deg"] == pytest.approx(window.view.state.camera.yaw_deg)
    window.close()


def test_picking_a_preset_moves_the_camera_and_names_it(qt_app, tmp_path):
    from planeopt.gui.liveview import LiveViewWindow

    live = tmp_path / "_live" / "job"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())

    window = LiveViewWindow()
    window.watch(live, live=True)
    index = window.view_preset.findData("front")
    window.view_preset.setCurrentIndex(index)
    window._preset_chosen(index)
    assert render3d.view_of(window.view.state.camera) == "front"
    window.close()


def test_the_new_run_dialog_records_a_view_the_timelapse_can_find(qt_app, tmp_path):
    """The whole point of choosing it up front is not being at the machine when
    a four-hour battery finishes."""
    from planeopt.gui import queuestore
    from planeopt.gui.jobs import Job

    job = Job(
        mission=tmp_path / "m.py", aircraft=tmp_path / "a.py", runs_dir=tmp_path,
        live_dir=tmp_path / "_live" / "job", timelapse_view="plan",
    )
    # It survives a restart of the app, like every other queued setting.
    queuestore.save(tmp_path, [job])
    assert queuestore.load(tmp_path)[0].timelapse_view == "plan"

    liveframe.write_view(job.live_dir, {"view": job.timelapse_view})
    camera, why = timelapse.resolve_camera(job.live_dir, None, None, None)
    assert render3d.view_of(camera) == "plan"
    assert "chosen for this run" in why


# --- timelapse ------------------------------------------------------------


def test_the_timelapse_camera_prefers_the_most_explicit_source(qt_app, tmp_path):
    liveframe.write_view(tmp_path, {"view": "side"})

    stored, why = timelapse.resolve_camera(tmp_path, None, None, None)
    assert render3d.view_of(stored) == "side" and "this run" in why

    named, why = timelapse.resolve_camera(tmp_path, "plan", None, None)
    assert render3d.view_of(named) == "plan" and why == "--view plan"

    exact, why = timelapse.resolve_camera(tmp_path, "plan", 12.0, None)
    assert (exact.yaw_deg, exact.pitch_deg) == (12.0, 90.0), "pitch keeps the preset's"
    assert "12" in why

    bare, why = timelapse.resolve_camera(tmp_path / "nowhere", None, None, None)
    assert bare is render3d.DEFAULT_CAMERA and render3d.DEFAULT_VIEW in why


def test_an_unknown_view_name_is_refused_before_the_render_not_after(qt_app, tmp_path):
    """A five-minute render is a bad place to discover a typo."""
    with pytest.raises(ValueError, match="unknown view"):
        timelapse.resolve_camera(tmp_path, "front-top-middle", None, None)


def test_parse_size_forces_even_dimensions():
    assert timelapse.parse_size("1920x1080") == (1920, 1080)
    # H.264 with 4:2:0 chroma cannot encode an odd dimension.
    assert timelapse.parse_size("1281x721") == (1280, 720)
    with pytest.raises(ValueError):
        timelapse.parse_size("big")
    with pytest.raises(ValueError):
        timelapse.parse_size("40x30")


def test_select_splits_kinds_by_filename(tmp_path):
    live = tmp_path / "frames"
    _write(live, "f000000__multistart__nominal__i0001.json.gz", _frame(kind="iterate"))
    _write(live, "f000001__multistart__nominal__final.json.gz", _frame())
    _write(live, "f000002__multistart__perturbed_0__i0001.json.gz", _frame(kind="iterate"))

    assert len(timelapse.select(live)) == 3
    assert [p.name for p in timelapse.select(live, "candidate")] == [
        "f000001__multistart__nominal__final.json.gz"
    ]
    assert len(timelapse.select(live, "iterate")) == 2
    with pytest.raises(ValueError):
        timelapse.select(live, "nonsense")


def test_timelapse_renders_pngs_and_holds_the_candidate(qt_app, tmp_path):
    live = tmp_path / "frames"
    _write(live, "f000000__multistart__nominal__i0001.json.gz", _frame(kind="iterate"))
    _write(live, "f000001__multistart__nominal__final.json.gz", _frame())

    result = timelapse.render(
        live, tmp_path / "out", size=(320, 240), hold_candidate=4
    )
    assert result["source_frames"] == 2
    # one iterate + four repeats of the candidate: a finished member has to
    # linger or a battery timelapse is unreadable
    assert result["images"] == 5
    pngs = sorted((tmp_path / "out").glob("frame_*.png"))
    assert len(pngs) == 5
    assert QImage(str(pngs[0])).size().width() == 320
    assert "ffmpeg" in result["ffmpeg_command"]


def test_timelapse_finds_a_run_directorys_frames(qt_app, tmp_path):
    run_dir = tmp_path / "20260805T120000-run"
    _write(run_dir / "frames", "f000000__multistart__nominal__final.json.gz", _frame())

    result = timelapse.render(run_dir, size=(320, 240), hold_candidate=1)
    assert result["source"] == run_dir / "frames"
    assert result["images"] == 1
    # A run's timelapse is an artifact OF that run: it lands inside it, beside
    # figures/ and frames/, not as a sibling directory under runs/.
    assert result["out_dir"] == run_dir / "timelapse"
    assert (run_dir / "timelapse" / "frame_000000.png").is_file()


def test_a_live_directorys_timelapse_lands_beside_it(qt_app, tmp_path):
    """A live directory has no run to live in yet — the run has not finished."""
    live = tmp_path / "_live" / "endurance"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())

    result = timelapse.render(live, size=(320, 240), hold_candidate=1)
    assert result["out_dir"] == tmp_path / "_live" / "endurance-timelapse"


def test_timelapse_skips_a_corrupt_frame_rather_than_failing(qt_app, tmp_path):
    live = tmp_path / "frames"
    _write(live, "f000000__multistart__nominal__final.json.gz", _frame())
    (live / "f000001__multistart__nominal__final.json.gz").write_bytes(b"not gzip")

    result = timelapse.render(live, tmp_path / "out", size=(320, 240), hold_candidate=1)
    assert result["images"] == 1
    assert result["unreadable"] == 1


def test_timelapse_refuses_an_empty_directory(qt_app, tmp_path):
    (tmp_path / "frames").mkdir()
    with pytest.raises(FileNotFoundError):
        timelapse.render(tmp_path / "frames", tmp_path / "out")


def test_a_recoloured_iterate_says_so_under_the_stats(qt_app):
    """The caption is what stops a real-but-untrimmed CL reading as a result."""
    plain = _frame(kind="iterate")
    marked = _frame(kind="iterate", recoloured=True)

    # Keep the paint device alive for the painter's whole lifetime. Passing a
    # temporary QImage leaves QPainter holding a dangling C++ pointer as soon as
    # Python releases the temporary; Qt may appear to tolerate it or abort the
    # process with an access violation depending on allocator timing.
    metrics_image = QImage(*SIZE, QImage.Format_RGB32)
    painter = QPainter(metrics_image)
    _, plain_h = render3d.stats_block_size(painter, plain)
    _, marked_h = render3d.stats_block_size(painter, marked)
    painter.end()
    # The block MEASURES taller, or the extra line would be drawn off the bottom
    # edge — the reservation and the drawing have to agree about the row count.
    assert marked_h > plain_h

    a, b = _render(plain), _render(marked)
    bottom = [
        (x, y) for y in range(SIZE[1] - int(marked_h), SIZE[1]) for x in range(SIZE[0])
        if a.pixel(x, y) != b.pixel(x, y)
    ]
    assert bottom, "the extra caption is actually drawn"
