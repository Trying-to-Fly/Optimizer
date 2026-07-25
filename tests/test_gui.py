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
