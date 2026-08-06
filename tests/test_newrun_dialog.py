"""The New Run dialog's live memory note.

Runs offscreen (`QT_QPA_PLATFORM=offscreen`) like `test_liveview.py`, because
what is under test here is a widget's reaction to a signal and there is no
display on a build machine.

`test_gui.py` covers the Qt-free half of the GUI deliberately — run indexing,
mission round-trip, command building — and this is the exception it names: the
note is recomputed by a Qt signal, so the signal is what has to fire.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="the dialog needs the `gui` extra")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planeopt import memory  # noqa: E402
from planeopt.gui.newrun import NewRunDialog  # noqa: E402
from planeopt.gui.workspace import resolve  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_the_budget_spinner_does_not_rescan_the_runs_directory(
    qt_app, tmp_path, monkeypatch
):
    """Dragging the budget spinner must not touch the disk once per tick.

    `observed_peak_gb` lists `runs/` and parses up to 25 `run.json` files to
    answer "what has a solve on this machine actually cost". It was being called
    from the note handler, which `valueChanged` fires on every arrow click and
    every keystroke — so holding the spinner's arrow re-read the run history
    tens of times a second to recompute a number that cannot have changed while
    a modal dialog is open.

    The scan is pinned at exactly one, not merely "few": one is what reading a
    fact that cannot change costs.
    """
    scans = []
    real = memory.observed_peak_gb
    monkeypatch.setattr(
        memory, "observed_peak_gb",
        lambda *a, **kw: (scans.append(a[0] if a else None), real(*a, **kw))[1],
    )

    dialog = NewRunDialog(resolve(tmp_path))
    dialog.mode_optimize.setChecked(True)
    dialog.memory_enabled.setChecked(True)
    after_construction = len(scans)

    for value in (16, 20, 24, 28, 32, 36):
        dialog.memory_budget.setValue(value)

    assert after_construction == 1, "the dialog should read the run history once"
    assert len(scans) == 1, (
        f"the spinner rescanned runs/ {len(scans) - after_construction} more times"
    )
    assert dialog.memory_note.text(), "the note must still say something"


def test_the_note_still_answers_after_the_facts_are_passed_in(qt_app, tmp_path):
    """The efficiency fix hands `plan_parallel` the machine facts the note
    already holds. Passing them must not change the answer it gives — a note
    that silently stopped mentioning the width would be the regression."""
    dialog = NewRunDialog(resolve(tmp_path))
    dialog.mode_optimize.setChecked(True)
    dialog.memory_enabled.setChecked(True)
    dialog.memory_budget.setValue(dialog.memory_budget.maximum())

    text = dialog.memory_note.text()
    assert "concurrent solve" in text, f"the width is the point of the note: {text!r}"
