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


@pytest.fixture()
def workspace(tmp_path):
    """A project folder of this test's own.

    NOT `resolve(tmp_path)`, which is what these tests used to say. `resolve`
    returns the first *usable* candidate — one that already has `aircraft/` or
    `missions/` — and an empty `tmp_path` has neither, so it fell through to the
    working directory and handed every test the REAL repository. The tests that
    only read got away with it; `NewRunDialog.job()` writes a mission module and
    reserves a live-frame directory, so it wrote into `missions/` and `runs/`.

    The aircraft package is a stub on purpose: `aircraft_packages()` looks for
    an `aircraft.py` and `job()` only ever passes the path to the child process,
    so nothing here imports it and the fixture stays instant.
    """
    (tmp_path / "aircraft" / "stub_plane").mkdir(parents=True)
    (tmp_path / "aircraft" / "stub_plane" / "aircraft.py").write_text(
        "AIRCRAFT = None\n", encoding="utf-8"
    )
    (tmp_path / "missions").mkdir()
    (tmp_path / "runs").mkdir()
    resolved = resolve(tmp_path)
    assert resolved.root == tmp_path, "the fixture must not hand back the repo"
    return resolved


def test_the_budget_spinner_does_not_rescan_the_runs_directory(
    qt_app, workspace, monkeypatch
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

    dialog = NewRunDialog(workspace)
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


def test_the_note_still_answers_after_the_facts_are_passed_in(qt_app, workspace):
    """The efficiency fix hands `plan_parallel` the machine facts the note
    already holds. Passing them must not change the answer it gives — a note
    that silently stopped mentioning the width would be the regression."""
    dialog = NewRunDialog(workspace)
    dialog.mode_optimize.setChecked(True)
    dialog.memory_enabled.setChecked(True)
    dialog.memory_budget.setValue(dialog.memory_budget.maximum())

    text = dialog.memory_note.text()
    assert "concurrent solve" in text, f"the width is the point of the note: {text!r}"


def test_two_jobs_on_one_mission_get_their_own_live_frame_directories(qt_app, workspace):
    """Frames from a cancelled run must not be adopted by the next one.

    The dialog used to name the live directory `runs/_live/<mission>`, from the
    mission alone. `FrameWriter` appends from one past the highest sequence
    already on disk — that is what makes a pause/resume continue instead of
    overwrite — and a run that is CANCELLED or fails never reaches
    `liveframe.relocate`, so its frames stay in that folder. The next run on the
    same mission therefore inherited them, showed them in the live view, and
    relocated them into its own `frames/`, where a timelapse replayed a
    different aeroplane under this run's name.

    Same second and same aircraft on purpose: the stamp alone has one-second
    resolution, so this is the case a stamp does not fix.
    """
    def queue_one() -> object:
        dialog = NewRunDialog(workspace)
        dialog.mode_optimize.setChecked(True)
        return dialog.job()

    first, second = queue_one(), queue_one()

    assert first.live_dir is not None
    assert first.live_dir != second.live_dir, (
        "two queued runs share a live frame directory, so the second inherits "
        "whatever the first left behind"
    )
    for job in (first, second):
        assert job.live_dir.is_dir(), "the directory is the reservation"
        assert not list(job.live_dir.iterdir()), "a job starts with no frames"


def test_an_evaluation_reserves_no_live_directory(qt_app, workspace):
    """Nothing iterates in an evaluation, so there is nothing to watch — and a
    stray empty directory under `runs/_live/` would suggest otherwise."""
    dialog = NewRunDialog(workspace)
    dialog.mode_evaluate.setChecked(True)

    assert dialog.job().live_dir is None
    assert not (workspace.runs_dir / "_live").exists()


@pytest.mark.parametrize("typed", ["../../escaped", "endurance 3m/s wind", "a/b/c"])
def test_every_path_a_job_names_stays_inside_the_workspace(qt_app, workspace, typed):
    """The mission name is free text and reaches FOUR paths — the module, the
    checkpoint directory, the pause sentinel and the live frames. `../../escaped`
    put the checkpoints and the sentinel outside the runs directory entirely."""
    dialog = NewRunDialog(workspace)
    dialog.name.setText(typed)
    dialog.mode_optimize.setChecked(True)
    job = dialog.job()

    root = workspace.root.resolve()
    for field in ("mission", "checkpoint_dir", "pause_file", "live_dir"):
        value = getattr(job, field)
        assert value is not None, field
        assert root in value.resolve().parents, f"{field} escaped to {value}"


def test_an_ordinary_name_still_lands_where_it_always_did(qt_app, workspace):
    """Sanitising must not move the checkpoint folder for names that were
    already safe — a resume looks for the folder its first run wrote."""
    dialog = NewRunDialog(workspace)
    dialog.name.setText("endurance_sample")
    dialog.mode_optimize.setChecked(True)
    job = dialog.job()

    assert job.mission == workspace.missions_dir / "endurance_sample.py"
    assert job.checkpoint_dir == workspace.runs_dir / "_checkpoints" / "endurance_sample"
    assert job.pause_file == workspace.runs_dir / "_checkpoints" / "endurance_sample.PAUSE"
