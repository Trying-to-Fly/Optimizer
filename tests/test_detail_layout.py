"""The detail pane has to FIT the width the window gives it.

`test_gui.py` says widget layout is verified by running the app rather than by
asserting on pixels, and that still holds — nothing here looks at a pixel. What
is asserted is geometry: whether the pane needs a horizontal scrollbar, and
whether every chip ends up inside the row that owns it. Both are numbers Qt
computes, and both were WRONG for `vtail_rcv2` before `ChipRow` existed.

Screenshots could not have found this and were actively misleading: under the
offscreen platform `QWidget.grab()` paints the whole child tree into the
viewport rectangle, so content that is really scrolled out of sight is drawn
overlapping whatever is in front of it. That looks like a layout collapse and is
a property of the capture. Geometry is the thing to assert.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="the detail pane needs the `gui` extra")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planeopt.gui import runindex  # noqa: E402
from planeopt.gui.views import Chip, ChipRow, DetailView  # noqa: E402

#: What a 1280-wide window — the size this app opens at on a laptop — leaves for
#: the detail pane once the runs list and the splitter have taken their share.
#: Measured from `MainWindow`, and the width the defect showed up at.
LAPTOP_PANE_PX = 896


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


def _run_with_studies(root, count: int):
    """A run adopting `count` discrete studies — the thing that widened the row.

    `vtail_rcv2` adopts five and prices a sixth. The names are the real ones,
    because chip width is text width and a placeholder would not reproduce it.
    """
    names = [
        ("motor_mount", "puller"),
        ("prop_choice", "ancf_12x10"),
        ("fuselage_topology", "pod_boom"),
        ("tail_type", "vtail"),
        ("wing_dihedral_form", "curve"),
        ("spar_material", "carbon_pultruded"),
    ]
    run_dir = root / "20260808T000000-rcv2_endurance-fixture"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({
        "aircraft": "fixture_v1",
        "mission": "rcv2_endurance",
        "objective": "endurance",
        "status": "M3",
        "created": "2026-08-08T00:00:00",
        "geometry": {"span_m": 2.0},
        "masses": {"auw_kg": 2.1},
        "performance": {
            "objective_units": "min",
            "best": {"objective_value": 122.6, "V_ms": 9.5},
            "optimization": {
                "discrete_studies": {
                    attr: {"adopted": value} for attr, value in names[:count]
                },
            },
        },
        "constraints": {"v_min_active": True, "sm_in_range": False},
    }), encoding="utf-8")
    return runindex.summarize(run_dir)


def _pane(summary, width: int, app) -> DetailView:
    pane = DetailView()
    pane.show_run(summary)
    pane.resize(width, 700)
    pane.show()
    for _ in range(3):
        app.processEvents()
    return pane


def test_the_pane_never_scrolls_sideways_at_a_laptop_width(qt_app, tmp_path):
    """The regression itself.

    Six study chips in a QHBoxLayout came to 1051 px and could not be narrower,
    so the pane scrolled sideways by 169 px — carrying the metric grids and the
    notes, which fit perfectly well, along with them.
    """
    pane = _pane(_run_with_studies(tmp_path, 6), LAPTOP_PANE_PX, qt_app)
    assert pane.horizontalScrollBar().maximum() == 0


@pytest.mark.parametrize("width", [500, 686, 896, 1000, 1202, 1600])
def test_no_width_makes_the_pane_scroll_sideways(qt_app, tmp_path, width):
    pane = _pane(_run_with_studies(tmp_path, 6), width, qt_app)
    assert pane.horizontalScrollBar().maximum() == 0, (
        f"pane needs {pane.widget().sizeHint().width()}px at a {width}px width"
    )


def test_chips_wrap_instead_of_running_off_the_edge(qt_app, tmp_path):
    """Wrapping, not eliding: a study chip is a verdict and half of one is no use.

    Asserted as "more than one distinct y", which is what wrapping IS, rather
    than a line count that would change with a font.
    """
    pane = _pane(_run_with_studies(tmp_path, 6), LAPTOP_PANE_PX, qt_app)
    rows = pane.widget().findChildren(ChipRow)
    studies = max(rows, key=lambda r: len(r.findChildren(Chip)))
    chips = studies.findChildren(Chip)
    assert len(chips) == 6
    assert len({c.y() for c in chips}) > 1


def test_every_chip_lands_inside_its_row(qt_app, tmp_path):
    """A chip drawn outside its row is clipped, and nothing else would say so."""
    for width in (500, 686, 896, 1202):
        pane = _pane(_run_with_studies(tmp_path / str(width), 6), width, qt_app)
        for row in pane.widget().findChildren(ChipRow):
            for chip in row.findChildren(Chip):
                assert chip.x() >= 0 and chip.y() >= 0
                assert chip.x() + chip.width() <= row.width() + 1, (
                    f"{chip.text()!r} runs past the row at a {width}px pane"
                )
                assert chip.y() + chip.height() <= row.height() + 1, (
                    f"{chip.text()!r} is below the row at a {width}px pane"
                )


def test_the_body_is_never_shorter_than_its_wrapped_content(qt_app, tmp_path):
    """The scroll area must be TOLD about the wrapped line.

    `setWidgetResizable(True)` sizes the body from `sizeHint` alone, which is
    the ONE-LINE height; without `DetailView.resizeEvent` re-measuring, a second
    line of chips is drawn outside the body and the scrollbar never accounts for
    it. The pane is deliberately short here so the content overflows — given
    spare height the box layout absorbs the extra line and the defect hides.
    """
    summary = _run_with_studies(tmp_path, 6)
    for width in (500, 686, 896):
        pane = DetailView()
        pane.show_run(summary)
        pane.resize(width, 300)
        pane.show()
        for _ in range(3):
            qt_app.processEvents()
        body = pane.widget()
        needed = body.layout().heightForWidth(pane.viewport().width())
        assert body.height() >= needed, (
            f"body is {body.height()}px at a {width}px pane but its content "
            f"needs {needed}px — the wrapped line is drawn outside it"
        )


def test_a_run_with_no_studies_is_unaffected(qt_app, tmp_path):
    """The fix must not add height to the pane it was not about."""
    pane = _pane(_run_with_studies(tmp_path, 0), LAPTOP_PANE_PX, qt_app)
    assert pane.horizontalScrollBar().maximum() == 0
    assert pane.widget().findChildren(ChipRow)  # the constraints row still renders
