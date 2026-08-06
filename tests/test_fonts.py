"""The one monospace font, and the platform ordering behind it.

Every monospaced glyph the GUI draws — the log pane, the metric grids, the 3D
canvas overlays, the timelapse annotations — now comes from `fonts.mono`. There
were three builders before, and they had already drifted apart once, so what is
pinned here is the single definition rather than any one caller.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="the font helper needs the `gui` extra")

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planeopt.gui import fonts  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


#: Ordering is not cosmetic: asking Qt for a family the system does not have
#: makes it build its entire font-alias table before it can rule the name out —
#: ~50 ms of startup and a console warning per font, on macOS, to arrive at
#: Menlo, which was in the list the whole time.
@pytest.mark.parametrize("platform,stack,expected", [
    ("darwin", ["Cascadia Mono", "Menlo", "monospace"],
     ["Menlo", "Cascadia Mono", "monospace"]),
    ("win32", ["Cascadia Mono", "Menlo", "monospace"],
     ["Cascadia Mono", "Menlo", "monospace"]),
    # A platform with no entry keeps the list exactly as written...
    ("linux", ["Cascadia Mono", "Menlo", "monospace"],
     ["Cascadia Mono", "Menlo", "monospace"]),
    # ...and so does one whose native family is not in the stack at all.
    ("darwin", ["Consolas", "monospace"], ["Consolas", "monospace"]),
])
def test_each_platform_leads_with_what_it_actually_ships(
    monkeypatch, platform, stack, expected
):
    monkeypatch.setattr(fonts.sys, "platform", platform)
    got = fonts.families(stack)
    assert got == expected
    assert sorted(got) == sorted(stack), "reordering only — never add or drop a family"


def test_the_stack_always_ends_in_a_generic_name():
    """Whatever else is missing, `monospace` resolves to something everywhere."""
    assert fonts.MONO_STACK[-1] == "monospace"


def test_mono_asks_for_families_not_one_comma_joined_name(qt_app):
    """`QFont("a, b, c")` is the trap: Qt reads it as a SINGLE family name, does
    not find it, and silently substitutes the proportional UI font — which looks
    like a styling choice rather than a bug."""
    font = fonts.mono(9)
    assert font.families() == fonts.families()
    assert len(font.families()) > 1
    assert font.styleHint() == QFont.Monospace


def test_mono_carries_size_and_weight_through(qt_app):
    assert fonts.mono(22, bold=True).pointSize() == 22
    assert fonts.mono(22, bold=True).bold() is True
    assert fonts.mono(9).bold() is False


def test_size_zero_keeps_the_surrounding_widget_s_size(qt_app):
    """The metric grids call `mono()` with no size and must not be re-scaled to
    some hard-coded point size the rest of the pane does not use."""
    assert fonts.mono().pointSize() == QApplication.font().pointSize()
