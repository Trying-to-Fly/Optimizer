"""The monospace font, ordered for the platform actually running.

Small and standalone so both the widget layer (`views`, `window`) and the 3D
canvas (`render3d`, which the `timelapse` CLI command pulls in without any
widgets) can share it without either importing the other.

It imports QtGui for `mono()` and nothing else from Qt. That is deliberate and
it is not the same as importing the widget layer: `timelapse` renders to a
QImage on a build machine with no display, which needs QtGui and must never need
QtWidgets.
"""

from __future__ import annotations

import functools
import sys

from PySide6.QtGui import QFont

#: Every monospace family worth trying, in preference order, ending in the
#: generic name so there is always something. Windows first because that is
#: where this app was built; `families()` fixes the order per platform.
MONO_STACK = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "monospace"]

#: What each platform actually ships, and so what it should be asked for first.
#: Menlo has been on every macOS since 10.6 and is what Terminal defaults to;
#: Cascadia Mono ships with Windows Terminal and recent Windows.
_NATIVE = {"darwin": "Menlo", "win32": "Cascadia Mono"}


def families(stack: list[str] | None = None) -> list[str]:
    """`stack` with this platform's own monospace font moved to the front.

    The families are unchanged and so is what actually gets drawn — the order is
    a hint about where to look first, and Qt takes the first one that exists
    either way. What it saves is the miss: asking for a family the system does
    not have makes Qt populate its whole font-alias table before it can rule the
    name out, which on macOS costs ~50 ms of startup and a warning on the
    console for every font built, to arrive at Menlo, which was in the list all
    along.

    Windows is unaffected by construction — Cascadia Mono already leads there —
    and a platform with no entry keeps the list exactly as written.
    """
    stack = MONO_STACK if stack is None else stack
    first = _NATIVE.get(sys.platform)
    if first is None or first not in stack:
        return list(stack)
    return [first] + [family for family in stack if family != first]


@functools.cache
def _families() -> list[str]:
    """`families()` for this process, resolved once."""
    return families()


def mono(size: int = 0, bold: bool = False) -> QFont:
    """The monospace QFont, built the one way that actually works.

    `setFamilies` and not `QFont("a, b, c")`: Qt reads a comma-joined string as a
    single family name, fails to find it, and silently substitutes the UI font —
    a proportional log pane that looks like a styling choice rather than a bug.

    One builder rather than one per module. There were three, and they had
    already drifted once: `main` asked for `'Monospace'` in one place and
    `'monospace'` in another, which is the sort of difference that only shows up
    on the one platform where exactly one of them exists.

    `size` of 0 keeps Qt's default point size, which is what the surrounding
    widget already uses.
    """
    font = QFont()
    font.setFamilies(_families())
    font.setStyleHint(QFont.Monospace)
    if size:
        font.setPointSize(size)
    font.setBold(bold)
    return font
