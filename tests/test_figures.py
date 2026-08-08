"""The planform figure has to be drawn to scale AND be readable.

Those two pull against each other, which is why this file exists. A wing is
about seven times wider than it is deep and its dihedral is a few centimetres
across two metres of span, so an axes box that is right for one view is wrong
for the other — and `set_aspect("equal")` resolves the mismatch by SHRINKING the
box. On the front view that left a box 14.0 px tall printing 13.9 px tick
labels, which overlapped; above the planform it left a blank band taller than
the wing.

Asserted as numbers Matplotlib computes — pixels per metre on each axis, and the
gap between tick labels against their own height — because "looks fine" is what
shipped the overlap through eleven runs of reports.
"""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from planeopt.report import figures  # noqa: E402


def _wing(span: float, chord: float, dihedral_rise: float, stations: int = 5):
    """The three attributes `_wing_outline`/`_front_outline` actually read.

    A stub rather than a real `asb.Airplane`: what is under test is the LAYOUT
    against a set of extents, and building a real aeroplane would tie this to
    whichever one the repo ships today.
    """
    xsecs = []
    for i in range(stations):
        frac = i / (stations - 1)
        xsecs.append(SimpleNamespace(
            xyz_le=[0.4 + 0.05 * frac, frac * span / 2, dihedral_rise * frac**2],
            chord=chord,
        ))
    return SimpleNamespace(wings=[SimpleNamespace(xsecs=xsecs, symmetric=True)])


def _draw(planes, tmp_path):
    """Render, and hand back the figure `planform_compare` would have closed."""
    captured = {}
    orig_save, orig_close = plt.Figure.savefig, plt.close
    plt.Figure.savefig = lambda self, *a, **k: (
        captured.__setitem__("fig", self), orig_save(self, *a, **k)
    )[1]
    plt.close = lambda *a, **k: None
    try:
        figures.planform_compare(planes, tmp_path)
    finally:
        plt.Figure.savefig, plt.close = orig_save, orig_close
    fig = captured["fig"]
    try:
        yield fig
    finally:
        orig_close(fig)


def _figure(planes, tmp_path):
    gen = _draw(planes, tmp_path)
    return next(gen), gen


REAL = {"baseline (defaults)": _wing(2.0, 0.28, 0.030),
        "optimized": _wing(2.0, 0.26, 0.045)}


@pytest.mark.parametrize("planes", [
    pytest.param(REAL, id="the-rcv2-champion-shape"),
    pytest.param({"only": _wing(2.0, 0.28, 0.0)}, id="no-dihedral-at-all"),
    pytest.param({"only": _wing(0.8, 0.30, 0.20)}, id="stubby-and-strongly-canted"),
    pytest.param({"only": _wing(3.0, 0.15, 0.005)}, id="very-slender"),
])
def test_both_views_are_drawn_to_true_scale(planes, tmp_path):
    """A metre across must be a metre down, or the picture is of another wing."""
    fig, gen = _figure(planes, tmp_path)
    try:
        for ax in fig.axes:
            box = ax.get_window_extent()
            (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
            px_per_m_x = box.width / abs(x1 - x0)
            px_per_m_y = box.height / abs(y1 - y0)
            assert px_per_m_y == pytest.approx(px_per_m_x, rel=1e-3)
    finally:
        list(gen)


@pytest.mark.parametrize("planes", [
    pytest.param(REAL, id="the-rcv2-champion-shape"),
    pytest.param({"only": _wing(2.0, 0.28, 0.0)}, id="no-dihedral-at-all"),
    pytest.param({"only": _wing(3.0, 0.15, 0.005)}, id="very-slender"),
])
def test_no_two_tick_labels_overlap(planes, tmp_path):
    """The regression: the front view's box was shorter than one tick label.

    `_FRONT_MIN_H_IN` is what stops it, and the flatter the wing the more it is
    doing — `very-slender` is the case that would collapse furthest.
    """
    fig, gen = _figure(planes, tmp_path)
    try:
        for ax in fig.axes:
            labels = [t for t in ax.get_yticklabels() if t.get_text()]
            tops = sorted(t.get_window_extent().y0 for t in labels)
            gaps = [b - a for a, b in zip(tops, tops[1:])]
            height = labels[0].get_window_extent().height
            assert not gaps or min(gaps) >= height, (
                f"y tick labels are {height:.1f}px tall but only "
                f"{min(gaps):.1f}px apart on a {ax.get_title()!r} axes "
                f"{ax.get_window_extent().height:.1f}px high"
            )
    finally:
        list(gen)


def test_the_figure_is_not_mostly_blank_paper(tmp_path):
    """`aspect=equal` with `adjustable=box` paid for the mismatch in white space.

    The two axes together used to be 124 px of a 715 px figure. Asserting that
    the drawn boxes are most of the figure is the cheap way to say "the height
    is the aeroplane's, not a constant".
    """
    fig, gen = _figure(REAL, tmp_path)
    try:
        drawn = sum(ax.get_window_extent().height for ax in fig.axes)
        total = fig.get_window_extent().height
        assert drawn / total > 0.45, f"only {drawn:.0f}px of {total:.0f}px is axes"
    finally:
        list(gen)


def test_a_wing_with_no_dihedral_still_produces_a_front_view(tmp_path):
    """Zero extent must not divide by zero or collapse the axes to nothing."""
    fig, gen = _figure({"flat": _wing(2.0, 0.28, 0.0)}, tmp_path)
    try:
        front = fig.axes[1]
        assert front.get_window_extent().height > 50
        assert (tmp_path / "planform_compare.png").is_file()
    finally:
        list(gen)
