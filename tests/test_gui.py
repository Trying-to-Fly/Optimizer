"""GUI logic that must hold without a display.

Only the Qt-free half is tested here (run indexing, mission round-trip, command
building) — that is where the behaviour lives. Widget layout is verified by
running the app, not by asserting on pixels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from planeopt.gui import jobs, missionfile, runindex
from planeopt.gui.workspace import Workspace, resolve
from planeopt.types import MissionSpec

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


def test_pause_writes_the_sentinel_only_for_the_running_job(tmp_path):
    """Pause must never kill: it asks, and the run stops at a boundary it
    chooses. A queued (not yet started) job has nothing to ask."""
    from planeopt.gui import runner

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
    from planeopt.gui import newrun

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
    from planeopt.gui import runner

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
               multistart=5, flatness=False, solve_timeout_min=45.0,
               memory_budget_gb=20.0)
    job.state = jobs.JobState.PAUSED
    queuestore.save(tmp_path, [job])

    restored, = queuestore.load(tmp_path)
    assert restored.mission == job.mission and restored.aircraft == job.aircraft
    assert restored.checkpoint_dir == job.checkpoint_dir
    assert restored.pause_file == job.pause_file
    # the settings have to come back too — a resumed job that quietly dropped
    # --multistart would produce one artifact from two configurations
    assert (restored.multistart, restored.flatness) == (5, False)
    assert (restored.solve_timeout_min, restored.memory_budget_gb) == (45.0, 20.0)


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
    from planeopt.gui import runner

    queue = runner.RunQueue.__new__(runner.RunQueue)
    queue.jobs, queue._current, queue._process = [], None, None
    started = []
    monkeypatch.setattr(runner.RunQueue, "queue_changed", _Signal())
    monkeypatch.setattr(runner.RunQueue, "_start_next", lambda self: started.append(1))

    job = _job(tmp_path)
    job.state = jobs.JobState.PAUSED
    queue.restore([job])
    assert queue.jobs == [job] and started == []
