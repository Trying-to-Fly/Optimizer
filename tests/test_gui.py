"""GUI logic that must hold without a display.

Only the Qt-free half is tested here (run indexing, mission round-trip, command
building) — that is where the behaviour lives. Widget layout is verified by
running the app, not by asserting on pixels.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

from planeopt.gui import jobs, missionfile, runindex
from planeopt.gui.workspace import Workspace, resolve
from planeopt.types import MissionSpec


def _gui(name: str):
    """Import a `planeopt.gui` module, SKIPPING when the `gui` extra is absent.

    The tests below exercise pure logic and say so — `RunQueue.__new__`, "no Qt
    event loop needed" — but the module they reach through imports PySide6 at
    import time, so without the extra they FAILED where every sibling skips
    (test_fonts, test_liveview, test_newrun_dialog, and lines 449 and 584 of
    this file). Nine red tests on a machine that simply has not installed a
    heavy optional dependency is how a real regression goes unnoticed.
    """
    pytest.importorskip("PySide6.QtCore")
    return importlib.import_module(f"planeopt.gui.{name}")


REPO = Path(__file__).resolve().parent.parent


class _Signal:
    """Stands in for a Qt Signal on an un-__init__'d QObject.

    `RunQueue` is built with `__new__` in these tests so no event loop is needed,
    which leaves its class-level Signals unbound. Emitting is not what is under
    test — the state transitions are — so a no-op that records is enough.
    """

    def __init__(self):
        self.emitted = []

    def __get__(self, obj, owner=None):
        return self

    def emit(self, *args):
        self.emitted.append(args)


def _write_run(root: Path, stamp: str, **overrides) -> Path:
    run_dir = root / f"{stamp}-endurance_sample-fixture"
    run_dir.mkdir(parents=True)
    data = {
        "aircraft": "fixture_v1",
        "mission": "endurance_sample",
        "objective": "endurance",
        "status": "M2",
        "created": "2026-07-25T12:00:00",
        "geometry": {"span_m": 2.0},
        "masses": {"auw_kg": 1.75},
        "performance": {"objective_units": "min", "best": {"objective_value": 110.0, "V_ms": 9.5}},
        "constraints": {"v_min_active": True, "stall_ok": True, "sm_in_range": False},
    }
    data.update(overrides)
    (run_dir / "run.json").write_text(json.dumps(data), encoding="utf-8")
    return run_dir


# --- run index ----------------------------------------------------------


def test_scan_is_newest_first(tmp_path):
    _write_run(tmp_path, "20260101T000000")
    _write_run(tmp_path, "20260725T120000")
    stamps = [s.stamp for s in runindex.scan(tmp_path)]
    assert stamps == ["20260725T120000", "20260101T000000"]


def test_summary_extracts_the_headline_numbers(tmp_path):
    _write_run(tmp_path, "20260725T120000")
    summary = runindex.scan(tmp_path)[0]
    assert summary.objective_text == "110.0 min"
    assert summary.span_m == 2.0
    assert summary.auw_kg == 1.75
    assert summary.optimized is False


def test_binding_and_violated_constraints_are_split(tmp_path):
    _write_run(tmp_path, "20260725T120000")
    summary = runindex.scan(tmp_path)[0]
    assert summary.active_constraints == ["v_min"]  # *_active True = binding
    assert summary.violated_constraints == ["sm"]  # *_in_range False = violated
    assert "stall" not in summary.violated_constraints  # *_ok True = satisfied


def test_a_run_still_in_progress_is_listed_not_skipped(tmp_path):
    (tmp_path / "20260725T130000-endurance_sample-fixture").mkdir()
    summaries = runindex.scan(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].error  # flagged, but present — a solve may be running
    assert summaries[0].objective_text == "—"


def test_unrelated_directories_are_not_listed_as_runs(tmp_path):
    # runs/ also holds hand-made artifact directories (e.g. fuselage_preview).
    (tmp_path / "fuselage_preview").mkdir()
    _write_run(tmp_path, "20260725T120000")
    assert [s.stamp for s in runindex.scan(tmp_path)] == ["20260725T120000"]


def test_corrupt_run_json_does_not_break_the_scan(tmp_path):
    run_dir = tmp_path / "20260725T120000-x"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{not json", encoding="utf-8")
    assert runindex.scan(tmp_path)[0].error


def _renderable(summaries):
    """Every field the run tree and the detail pane touch."""
    for s in summaries:
        assert isinstance(s.objective_text, str)
        assert isinstance(s.label, str)
        assert isinstance(s.active_constraints, list)
        assert isinstance(s.violated_constraints, list)
        s.has_report, s.has_3d  # noqa: B018


@pytest.mark.parametrize("body", ["null", "[1, 2, 3]", '"a run"', "42"])
def test_json_that_is_not_a_run_record_costs_one_flagged_row(tmp_path, body):
    """Valid JSON, but not an object — nothing below can read it.

    The runs list is fed by any folder holding a `run.json`, so it reads
    artifacts this app did not write. `{not json` was already caught; this was
    not, and it raised out of `scan` and emptied the whole list.
    """
    _write_run(tmp_path, "20260725T120000")  # a good run, which must survive
    bad = tmp_path / "20260726T120000-not-a-record"
    bad.mkdir()
    (bad / "run.json").write_text(body, encoding="utf-8")

    summaries = runindex.scan(tmp_path)
    assert len(summaries) == 2, "the good run was lost with the bad one"
    wrong, good = summaries  # newest first
    assert wrong.error, "a file that is not a run record must say so"
    assert good.objective_text == "110.0 min", "the good run still reads"
    _renderable(summaries)


@pytest.mark.parametrize(
    "overrides",
    [
        {"constraints": [1, 2]},
        {"constraints": "none"},
        {"masses": "heavy"},
        {"geometry": 3},
        {"performance": []},
        {"performance": {"best": []}},
        {"aircraft": 7, "status": 3},
    ],
    ids=lambda o: "+".join(sorted(o)),
)
def test_a_wrong_typed_block_reads_as_blank_not_a_crash(tmp_path, overrides):
    """`data.get("masses") or {}` covers a MISSING or null block and nothing
    more: one that is present but is a list, a string or a number sailed through
    and raised on the next `.get` — out of `scan`, taking every other run with
    it. This module's contract is the opposite ("must list those rather than
    refuse to start"), so the row renders with whatever it could read.
    """
    _write_run(tmp_path, "20260725T120000")
    _write_run(tmp_path, "20260726T120000", **overrides)

    summaries = runindex.scan(tmp_path)
    assert len(summaries) == 2
    _renderable(summaries)
    assert summaries[1].objective_text == "110.0 min", "the good run still reads"


def test_a_non_numeric_objective_reads_as_a_dash_not_a_crash(tmp_path):
    """`objective_text` is built while the tree is being filled in, so a
    ValueError there empties the list rather than one cell."""
    _write_run(
        tmp_path, "20260725T120000",
        performance={"objective_units": "min", "best": {"objective_value": "n/a"}},
    )
    assert runindex.scan(tmp_path)[0].objective_text == "—"


@pytest.mark.parametrize(
    "overrides",
    [
        {"performance": "fast"},
        {"masses": [1, 2]},
        {"geometry": 3},
        {"masses": {"auw_kg": 1.0, "equipment": "none"}},
        {"performance": {"optimization": [1]}},
        {"performance": {"optimization": {"discrete_studies": [1]}}},
        {"performance": {"optimization": {"priced_options": {"tail": "no"}}}},
    ],
    ids=lambda o: "+".join(sorted(o)),
)
def test_the_detail_pane_survives_a_wrong_typed_block(tmp_path, overrides):
    """`show_run` reads the same blocks `summarize` does and had the same hole,
    but it runs inside a SELECTION SLOT — on a run the user has just clicked."""
    views = _gui("views")
    _gui("window")  # a QApplication has to exist before any widget
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    run = _write_run(tmp_path, "20260725T120000", **overrides)
    views.DetailView().show_run(runindex.summarize(run))


def test_a_string_note_is_one_bullet_not_one_per_character(tmp_path):
    """A bare string is iterable, so `notes: "one note"` drew a bullet per
    character — thirty-three labels for one sentence."""
    views = _gui("views")
    from PySide6.QtWidgets import QApplication, QLabel

    QApplication.instance() or QApplication([])

    run = _write_run(tmp_path, "20260725T120000", notes="a single note as a string")
    pane = views.DetailView()
    pane.show_run(runindex.summarize(run))

    bullets = [w.text() for w in pane.findChildren(QLabel) if w.text().startswith("\u2022 ")]
    assert bullets == ["\u2022 a single note as a string"]


def test_scan_of_a_missing_root_is_empty(tmp_path):
    assert runindex.scan(tmp_path / "nope") == []


# --- mission round-trip -------------------------------------------------


def test_mission_survives_a_round_trip(tmp_path):
    original = MissionSpec(
        name="round_trip",
        objective="range",
        v_wind_ms=3.5,
        penetration_margin_ms=6.0,
        v_stall_max_ms=7.5,
        static_margin_range=(0.05, 0.20),
        ballast_max_kg=0.045,
    )
    path = missionfile.save(original, tmp_path / "round_trip.py")
    loaded = missionfile.load(path)
    for field in ("name", "objective", "v_wind_ms", "penetration_margin_ms",
                  "v_stall_max_ms", "static_margin_range", "ballast_max_kg"):
        assert getattr(loaded, field) == getattr(original, field)
    assert loaded.v_min_ms == pytest.approx(9.5)


def test_optional_limits_round_trip_as_none(tmp_path):
    original = MissionSpec(name="loose", objective="endurance",
                           v_stall_max_ms=None, ballast_max_kg=None)
    loaded = missionfile.load(missionfile.save(original, tmp_path / "loose.py"))
    assert loaded.v_stall_max_ms is None
    assert loaded.ballast_max_kg is None


def test_the_shipped_sample_mission_loads(tmp_path):
    mission = missionfile.load(REPO / "missions" / "endurance_sample.py")
    assert mission.objective == "endurance"
    # and re-rendering it produces a module that loads back identically
    reloaded = missionfile.load(missionfile.save(mission, tmp_path / "again.py"))
    assert reloaded.static_margin_range == mission.static_margin_range


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("endurance_sample", "endurance_sample.py"),
        # A slash reads as a UNIT to a human and as a PATH to the filesystem.
        # This one created `missions/endurance 3m/` and hid the module inside it,
        # where `workspace.missions()` — a non-recursive glob — never sees it.
        ("endurance 3m/s wind", "endurance_3m_s_wind.py"),
        ("endurance (2026-08-08)", "endurance_2026-08-08.py"),
        ("Bob's mission", "Bob_s_mission.py"),
        ("wind\nspeed", "wind_speed.py"),
        ("   ", "mission.py"),
        ("", "mission.py"),
    ],
)
def test_a_mission_name_is_confined_to_the_missions_directory(tmp_path, name, expected):
    missions = tmp_path / "missions"
    missions.mkdir()
    path = missionfile.path_for(missions, MissionSpec(name=name, objective="endurance"))

    assert path.name == expected
    assert path.parent == missions, "a name must not choose its own directory"


def test_a_name_cannot_climb_out_of_the_missions_directory(tmp_path):
    """`../aircraft/aircraft` wrote OUTSIDE missions/ and overwrote a real
    aircraft definition — the dialog's name field is free text."""
    missions = tmp_path / "missions"
    missions.mkdir()
    victim = tmp_path / "aircraft"
    victim.mkdir()
    (victim / "aircraft.py").write_text("REAL = 'do not clobber'\n", encoding="utf-8")

    mission = MissionSpec(name="../aircraft/aircraft", objective="endurance")
    missionfile.save(mission, missionfile.path_for(missions, mission))

    assert (victim / "aircraft.py").read_text(encoding="utf-8") == "REAL = 'do not clobber'\n"
    assert not list(victim.glob("*.py.bak"))
    assert [p.name for p in missions.glob("*.py")] == ["aircraft_aircraft.py"]


def test_a_name_with_a_triple_quote_still_produces_a_module_that_loads(tmp_path):
    """The name is rendered into the module's docstring, so a triple quote made
    a file that would not parse. The dialog accepted it, queued the job, and the
    child died on a SyntaxError before it ever read the aircraft."""
    mission = MissionSpec(name='quoted """ name', objective="endurance", v_wind_ms=4.0)
    path = missionfile.save(mission, missionfile.path_for(tmp_path, mission))

    loaded = missionfile.load(path)
    assert loaded.objective == "endurance"
    assert loaded.v_wind_ms == 4.0
    # The name the user typed survives verbatim in the field, which is the
    # authoritative record — only the FILENAME and the docstring are sanitised.
    assert loaded.name == 'quoted """ name'


# --- job commands -------------------------------------------------------


def _job(tmp_path, **kw) -> jobs.Job:
    return jobs.Job(
        mission=tmp_path / "m.py", aircraft=tmp_path / "ac", runs_dir=tmp_path / "runs", **kw
    )


def test_optimize_command_carries_its_options(tmp_path):
    program, args = jobs.program_and_args(_job(tmp_path, optimize=True, multistart=5, flatness=False))
    assert program == sys.executable
    assert args[args.index("--multistart") + 1] == "5"
    assert "--no-flatness" in args
    assert "optimize" in args and "run" not in args


def test_evaluate_command_omits_optimizer_only_flags(tmp_path):
    _, args = jobs.program_and_args(_job(tmp_path, optimize=False))
    assert "run" in args
    assert "--multistart" not in args and "--no-flatness" not in args
    assert "--solve-timeout-min" not in args  # nothing to time-box in one pass


def test_solve_timeout_reaches_the_child(tmp_path):
    """The per-solve wall-clock cap is the app's guard against one diverging
    member owning a whole battery, so it has to survive the queue -> subprocess
    hop rather than only existing in the dialog."""
    _, args = jobs.program_and_args(_job(tmp_path, solve_timeout_min=45.0))
    assert args[args.index("--solve-timeout-min") + 1] == "45.0"
    # unset means "let the CLI's own default stand", not "no limit"
    assert "--solve-timeout-min" not in jobs.program_and_args(_job(tmp_path))[1]


def test_checkpoint_and_pause_reach_the_child(tmp_path):
    """The GUI's Pause button works by writing a sentinel the child polls, so
    both paths have to survive the queue -> subprocess hop or the button does
    nothing at all."""
    job = _job(tmp_path, checkpoint_dir=tmp_path / "ckpt",
               pause_file=tmp_path / "ckpt" / "m.PAUSE")
    _, args = jobs.program_and_args(job)
    assert args[args.index("--checkpoint") + 1] == str(tmp_path / "ckpt")
    assert args[args.index("--pause-file") + 1] == str(tmp_path / "ckpt" / "m.PAUSE")

    plain = jobs.program_and_args(_job(tmp_path))[1]
    assert "--checkpoint" not in plain and "--pause-file" not in plain


def test_the_live_frame_directory_reaches_the_child(tmp_path):
    """The live viewer watches a directory the CHILD writes, so the flag has to
    survive the queue -> subprocess hop or the popup opens onto nothing."""
    job = _job(tmp_path, optimize=True, live_dir=tmp_path / "_live" / "m")
    _, args = jobs.program_and_args(job)
    assert args[args.index("--live-dir") + 1] == str(tmp_path / "_live" / "m")

    # An evaluation has nothing to watch — no iteration — and must not be given
    # a flag the `run` subcommand does not have.
    evaluation = _job(tmp_path, optimize=False, live_dir=tmp_path / "_live" / "m")
    assert "--live-dir" not in jobs.program_and_args(evaluation)[1]
    assert "--live-dir" not in jobs.program_and_args(_job(tmp_path))[1]


def test_pause_writes_the_sentinel_only_for_the_running_job(tmp_path):
    """Pause must never kill: it asks, and the run stops at a boundary it
    chooses. A queued (not yet started) job has nothing to ask."""
    runner = _gui("runner")

    queue = runner.RunQueue.__new__(runner.RunQueue)  # no Qt event loop needed
    pause_path = tmp_path / "ckpt" / "m.PAUSE"
    running = _job(tmp_path, pause_file=pause_path)
    queued = _job(tmp_path, pause_file=tmp_path / "other.PAUSE")
    queue._current = running
    queue._process = object()  # stands in for the live QProcess

    assert queue.pause(running) is True
    assert pause_path.read_text(encoding="utf-8").strip()

    assert queue.pause(queued) is False
    assert not (tmp_path / "other.PAUSE").exists()

    # a job queued without a checkpoint cannot be paused, and says so
    queue._current = bare = _job(tmp_path)
    assert queue.pause(bare) is False


def test_the_dialog_default_matches_the_solver_default():
    """newrun copies the number instead of importing planeopt.solve (which drags
    in aerosandbox and would stall the dialog). Copies drift; this pins them."""
    from planeopt import solve
    newrun = _gui("newrun")

    assert newrun.SOLVE_TIMEOUT_MIN_DEFAULT == solve.SOLVE_TIMEOUT_MIN


def test_source_install_goes_through_python_m_planeopt(tmp_path):
    _, args = jobs.program_and_args(_job(tmp_path))
    assert args[:3] == ["-m", "planeopt", "optimize"]


def test_frozen_build_calls_the_bundle_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _, args = jobs.program_and_args(_job(tmp_path))
    assert args[0] == "optimize"  # the exe *is* the CLI; no -m indirection


def test_run_dir_is_recovered_from_the_child_output(tmp_path):
    runs = tmp_path / "runs"
    produced = runs / "20260725T120000-endurance_sample-fixture"
    produced.mkdir(parents=True)
    stdout = f"status: M2\n{produced}\n"
    assert jobs.parse_run_dir(stdout, runs) == produced


def test_run_dir_is_none_when_the_child_printed_nothing_useful(tmp_path):
    assert jobs.parse_run_dir("boom\n", tmp_path) is None


# --- workspace ----------------------------------------------------------
# A double-clicked .exe starts in whatever directory Explorer chose, so "where
# do aircraft/ and missions/ live" cannot be assumed the way the CLI assumes it.


def _project(root: Path) -> Path:
    (root / "aircraft" / "sample").mkdir(parents=True)
    (root / "aircraft" / "sample" / "aircraft.py").write_text("AIRCRAFT = None", encoding="utf-8")
    (root / "missions").mkdir()
    (root / "missions" / "m.py").write_text("MISSION = None", encoding="utf-8")
    return root


def test_a_folder_with_aircraft_is_usable(tmp_path):
    workspace = Workspace(_project(tmp_path))
    assert workspace.is_usable
    assert [p.name for p in workspace.aircraft_packages()] == ["sample"]
    assert [p.name for p in workspace.missions()] == ["m.py"]


def test_an_empty_folder_is_not_usable_and_lists_nothing(tmp_path):
    workspace = Workspace(tmp_path / "nowhere")
    assert not workspace.is_usable
    # Must not raise: this is the state of a freshly double-clicked executable.
    assert workspace.aircraft_packages() == []
    assert workspace.missions() == []


def test_a_directory_without_aircraft_py_is_not_an_aircraft(tmp_path):
    (tmp_path / "aircraft" / "notes").mkdir(parents=True)
    assert Workspace(tmp_path).aircraft_packages() == []


def test_explicit_choice_wins_over_everything(tmp_path):
    explicit = _project(tmp_path / "explicit")
    remembered = _project(tmp_path / "remembered")
    assert resolve(explicit=explicit, remembered=remembered).root == explicit


def test_a_remembered_project_wins_over_the_working_directory(tmp_path, monkeypatch):
    remembered = _project(tmp_path / "remembered")
    monkeypatch.chdir(_project(tmp_path / "cwd"))
    assert resolve(remembered=remembered).root == remembered


def test_an_unusable_remembered_project_falls_through_to_the_cwd(tmp_path, monkeypatch):
    cwd = _project(tmp_path / "cwd")
    monkeypatch.chdir(cwd)
    assert resolve(remembered=tmp_path / "deleted-since").root == cwd


def test_resolve_still_returns_something_when_nothing_qualifies(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # empty: no aircraft/, no missions/
    workspace = resolve()
    assert not workspace.is_usable  # the UI asks the user rather than dying
    assert workspace.root == tmp_path


# --------------------------------------------------------------- pause -> resume

def _paused_queue(tmp_path, stdout: str = "PAUSED — stopped at a member boundary"):
    """A RunQueue whose child has just exited 0 with the sentinel still on disk.

    Built without a Qt event loop: `_on_finished` is the whole of what the queue
    does when a child ends, and it is pure state.
    """
    runner = _gui("runner")

    queue = runner.RunQueue.__new__(runner.RunQueue)
    pause_path = tmp_path / "ckpt" / "m.PAUSE"
    pause_path.parent.mkdir(parents=True, exist_ok=True)
    job = _job(tmp_path, checkpoint_dir=tmp_path / "ckpt", pause_file=pause_path)
    queue.jobs = [job]
    queue._current, queue._process, queue._stdout = job, None, stdout
    job.state = jobs.JobState.RUNNING
    return queue, job, pause_path


def test_a_paused_job_is_not_reported_as_done(tmp_path, monkeypatch):
    """The child EXITS 0 on a pause — deliberately, so a shell loop does not read
    it as a crash — so without a state of its own a paused battery showed the
    same '✓ done' as a finished one, with no way back to it."""
    runner = _gui("runner")

    queue, job, pause_path = _paused_queue(tmp_path)
    pause_path.write_text("pause requested", encoding="utf-8")
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "job_finished", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: None)

    queue._on_finished(0, None)
    assert job.state is jobs.JobState.PAUSED
    assert job.run_dir is None


def test_a_finished_job_is_still_done_even_if_a_pause_was_requested_late(tmp_path, monkeypatch):
    """The sentinel alone is not enough: a pause asked for after the last member
    started leaves the file behind on a run that finished and wrote artifacts.
    That run has a run directory, and a run directory means DONE."""
    runner = _gui("runner")

    run_dir = tmp_path / "20260804T120000-endurance_sample-fixture"
    run_dir.mkdir(parents=True)
    queue, job, pause_path = _paused_queue(tmp_path, stdout=f"status: M3\n{run_dir}\n")
    pause_path.write_text("pause requested", encoding="utf-8")
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "job_finished", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: None)

    queue._on_finished(0, None)
    assert job.state is jobs.JobState.DONE
    assert job.run_dir == run_dir


def test_an_ordinary_finish_is_not_mistaken_for_a_pause(tmp_path, monkeypatch):
    """No sentinel on disk — `cli.optimize` unlinks it at startup — so a run that
    was never paused must not acquire the state."""
    runner = _gui("runner")

    queue, job, _ = _paused_queue(tmp_path, stdout="status: M3\n")
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "job_finished", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: None)

    queue._on_finished(0, None)
    assert job.state is jobs.JobState.DONE


def test_resume_requeues_the_same_job_rather_than_a_new_one(tmp_path, monkeypatch):
    """Resuming has to reuse the Job — same mission, aircraft and checkpoint
    directory. Re-filling the New Run dialog by hand is the alternative, and a
    field typed differently would not fail loudly; it would produce one artifact
    from two configurations."""
    runner = _gui("runner")

    queue, job, _ = _paused_queue(tmp_path)
    job.state, job.exit_code = jobs.JobState.PAUSED, 0
    started = []
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: started.append(self.jobs[0]))

    assert queue.resume(job) is True
    assert job.state is jobs.JobState.QUEUED
    assert job.exit_code is None
    assert started == [job], "resume must hand the SAME job back to the runner"


def test_only_a_paused_job_can_be_resumed(tmp_path, monkeypatch):
    runner = _gui("runner")

    queue, job, _ = _paused_queue(tmp_path)
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: None)
    for state in (jobs.JobState.RUNNING, jobs.JobState.DONE, jobs.JobState.FAILED,
                  jobs.JobState.QUEUED, jobs.JobState.CANCELLED):
        job.state = state
        assert queue.resume(job) is False


def test_resume_leaves_the_sentinel_for_the_cli_to_clear(tmp_path, monkeypatch):
    """One owner for that file. `cli.optimize` unlinks it at startup and says so,
    which is what makes a CLI resume and a GUI resume behave identically."""
    runner = _gui("runner")

    queue, job, pause_path = _paused_queue(tmp_path)
    pause_path.write_text("pause requested", encoding="utf-8")
    job.state = jobs.JobState.PAUSED
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: None)

    queue.resume(job)
    assert pause_path.exists()
    # ...and the CLI is what removes it, so that claim is pinned too
    assert "pause_file.unlink()" in (
        REPO / "src" / "planeopt" / "cli.py"
    ).read_text(encoding="utf-8")


def test_every_job_state_has_a_mark(tmp_path):
    """The queue row is f"{mark} {state}", so a state without a mark is a
    KeyError in the refresh — i.e. a broken queue list, not a missing glyph."""
    pytest.importorskip("PySide6.QtWidgets")
    from planeopt.gui.window import _STATE_MARK

    assert set(_STATE_MARK) == set(jobs.JobState)
    # ⏸ (U+23F8) had no font on this machine and rendered as tofu; the marks all
    # have to come from blocks that actually resolve.
    assert "⏸" not in "".join(_STATE_MARK.values())


# --------------------------------------------------- the queue across a restart

def test_a_paused_job_survives_closing_the_app(tmp_path):
    """Pausing exists to give the machine back, and the next thing anyone does
    with a machine they were just given back is close the app. That used to lose
    the job while its checkpoints sat on disk with nothing pointing at them."""
    from planeopt.gui import queuestore

    job = _job(tmp_path, checkpoint_dir=tmp_path / "ckpt",
               pause_file=tmp_path / "ckpt" / "m.PAUSE",
               # A RESERVED directory, which is what the dialog has produced
               # since 2026-08-08. This used to say `_live/m` — the shared
               # per-mission name — and that shape is now deliberately dropped
               # on load, because resuming into it adopts frames another run
               # left there. See the legacy test below.
               live_dir=tmp_path / "_live" / "20260808T091655-m-fixture",
               multistart=5, flatness=False, solve_timeout_min=45.0,
               memory_budget_gb=20.0)
    job.state = jobs.JobState.PAUSED
    queuestore.save(tmp_path, [job])

    restored, = queuestore.load(tmp_path)
    assert restored.mission == job.mission and restored.aircraft == job.aircraft
    assert restored.checkpoint_dir == job.checkpoint_dir
    assert restored.pause_file == job.pause_file
    # A resumed run appends to the frames the first half wrote, so the resumed
    # job has to point at the same directory (liveframe._next_seq).
    assert restored.live_dir == job.live_dir
    # the settings have to come back too — a resumed job that quietly dropped
    # --multistart would produce one artifact from two configurations
    assert (restored.multistart, restored.flatness) == (5, False)
    assert (restored.solve_timeout_min, restored.memory_budget_gb) == (45.0, 20.0)


def test_a_shared_live_dir_from_an_old_queue_file_is_not_carried_forward(tmp_path):
    """The frame-adoption defect, arriving through PERSISTED state.

    `runs/_live/<mission>` was shared by every run of that mission until
    2026-08-08. `FrameWriter` starts one past the highest sequence on disk, so a
    run resuming into one appends to whatever a cancelled run left there and
    relocates the lot into its own `frames/` — where the stranger's frames sort
    FIRST and the timelapse opens on an aeroplane it never flew.

    Reserving per job fixed that at the DIALOG. The queue file round-trips
    `live_dir` faithfully, which is correct for a real pause and is exactly what
    reopens the hole for a job written before the fix. This machine had three
    such entries, one pointing at a directory holding 1,683 orphaned frames.
    """
    from planeopt.gui import queuestore

    for shared in ("m", "endurance_sample", "rcv2_endurance"):
        job = _job(tmp_path, live_dir=tmp_path / "_live" / shared)
        job.state = jobs.JobState.PAUSED
        queuestore.save(tmp_path, [job])
        restored, = queuestore.load(tmp_path)
        assert restored.live_dir is None, f"{shared!r} was carried forward"
    # and loading must not have created anything: opening the app is not a
    # reason to make directories for jobs nobody has resumed
    assert not (tmp_path / "_live").exists()


def test_resuming_a_job_without_a_live_dir_reserves_one(tmp_path):
    """The other half: dropping the path must not silently cost the live view."""
    from planeopt.gui.runner import RunQueue

    job = _job(tmp_path, live_dir=None)
    job.state = jobs.JobState.PAUSED
    queue = RunQueue.__new__(RunQueue)
    queue.jobs = [job]
    queue.queue_changed = _Signal()
    queue.job_started = _Signal()
    queue._start_next = lambda: None
    assert queue.resume(job) is True
    assert job.live_dir is not None
    assert job.live_dir.is_dir()
    assert job.live_dir.parent == job.runs_dir / "_live"
    assert jobs.is_reserved_live_dir(job.live_dir)


def test_nothing_starts_on_its_own_at_launch(tmp_path):
    """Opening the window must never be what commits the machine to a two-hour
    solve, so every restored job comes back PAUSED — including one that was
    QUEUED and had not begun, and one that was RUNNING when the window closed."""
    from planeopt.gui import queuestore

    for state in (jobs.JobState.QUEUED, jobs.JobState.RUNNING, jobs.JobState.PAUSED):
        job = _job(tmp_path, checkpoint_dir=tmp_path / "ckpt")
        job.state = state
        queuestore.save(tmp_path, [job])
        assert queuestore.load(tmp_path)[0].state is jobs.JobState.PAUSED


def test_finished_jobs_are_not_carried_forward(tmp_path):
    """They cannot be acted on, and the runs list already records every finished
    run — keeping them would grow the queue forever across sessions."""
    from planeopt.gui import queuestore

    keep, drop = [], []
    for state in jobs.JobState:
        job = _job(tmp_path)
        job.state = state
        (keep if state in queuestore.RESTORABLE else drop).append(job)
    queuestore.save(tmp_path, keep + drop)
    assert len(queuestore.load(tmp_path)) == len(keep) == 3


def test_a_corrupt_queue_file_is_an_empty_queue_not_a_dead_window(tmp_path):
    """The part that took hours is the checkpoints, not this file. Losing it must
    never be what stops the app opening."""
    from planeopt.gui import queuestore

    queuestore.path_for(tmp_path).write_text("{not json", encoding="utf-8")
    assert queuestore.load(tmp_path) == []

    queuestore.path_for(tmp_path).write_text('[{"mission": "only-this"}]', encoding="utf-8")
    assert queuestore.load(tmp_path) == [], "an entry missing required fields is dropped"

    assert queuestore.load(tmp_path / "no-such-dir") == []


def test_the_queue_file_is_written_atomically(tmp_path):
    """A crash mid-write must not leave a half file that the next launch parses
    into a job with a missing aircraft."""
    from planeopt.gui import queuestore

    queuestore.save(tmp_path, [_job(tmp_path)])
    assert list(tmp_path.glob("*.json.part")) == []
    assert queuestore.path_for(tmp_path).is_file()


def test_restore_does_not_start_anything(tmp_path, monkeypatch):
    """`restore` exists separately from `submit` for exactly this."""
    runner = _gui("runner")

    queue = runner.RunQueue.__new__(runner.RunQueue)
    queue.jobs, queue._current, queue._process = [], None, None
    started = []
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: started.append(1))

    job = _job(tmp_path)
    job.state = jobs.JobState.PAUSED
    queue.restore([job])
    assert queue.jobs == [job] and started == []


def test_the_gui_never_imports_the_solver():
    """EXECUTION_PLAN section 3 rule 1: the GUI owns no solver path.

    It reads artifacts and launches subprocesses, and that separation is what
    keeps a ~14.5 GB solve — which the OOM killer can and does take — from being
    able to take the window and the queue down with it. The live viewer (M5.4)
    is the closest thing to a breach: it renders aircraft geometry, so the
    temptation is to build that geometry here. It does not; the SOLVER writes
    the mesh into each frame and `planeopt.liveframe` keeps every aerosandbox
    import function-local so that reading a frame stays pure stdlib.

    A subprocess, because this test session has already imported the solver
    through the aircraft fixtures — asking `sys.modules` in-process proves
    nothing.
    """
    import subprocess

    probe = (
        "import sys;"
        "from planeopt.gui import render3d, liveview, timelapse, jobs, runindex,"
        " queuestore, missionfile, workspace, newrun, window;"
        "from planeopt import liveframe;"
        "print(','.join(m for m in ('aerosandbox', 'casadi', 'matplotlib')"
        " if m in sys.modules))"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env,
    )
    if "No module named" in result.stderr:
        pytest.skip("the GUI extra is not installed")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"the GUI pulled in {result.stdout.strip()} — a solver import in the GUI "
        "process is exactly what the subprocess architecture exists to prevent"
    )
