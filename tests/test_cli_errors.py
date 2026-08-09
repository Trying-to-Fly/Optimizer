"""What the CLI says when the path you typed is wrong.

Every one of these is the FIRST thing a user does wrong — a mistyped aircraft
name, a run directory that is not one — and each used to answer with an
internal traceback instead of a message. They are cheap to hold: nothing here
imports a solver or writes a run.
"""

from __future__ import annotations

import json

import pytest
import typer

from planeopt import cli


def _run_dir(tmp_path, body=None):
    run_dir = tmp_path / "20260725T120000-endurance_sample-fixture"
    run_dir.mkdir(parents=True)
    if body is not None:
        (run_dir / "run.json").write_text(body, encoding="utf-8")
    return run_dir


# --- the run directory a user types -------------------------------------


def test_a_missing_run_directory_names_itself(tmp_path):
    with pytest.raises(typer.BadParameter, match="is not a directory"):
        cli._load_run(tmp_path / "typo")


def test_a_directory_that_is_not_a_run_says_which_file_is_missing(tmp_path):
    with pytest.raises(typer.BadParameter, match="has no run.json"):
        cli._load_run(_run_dir(tmp_path))


def test_a_corrupt_run_json_is_a_message_not_a_traceback(tmp_path):
    with pytest.raises(typer.BadParameter, match="could not be read"):
        cli._load_run(_run_dir(tmp_path, "{not json"))


def test_a_real_run_directory_still_loads(tmp_path):
    body = json.dumps({
        "aircraft": "fixture", "mission": "endurance_sample",
        "objective": "endurance", "status": "M2", "created": "2026-07-25T12:00:00",
    })
    assert cli._load_run(_run_dir(tmp_path, body)).aircraft == "fixture"


# --- the aircraft / mission module a user types -------------------------


def test_a_mistyped_aircraft_name_is_a_message_not_a_traceback(tmp_path):
    """`spec_from_file_location` RETURNS None for a file that is not there, so
    this came out as `AttributeError: 'NoneType' object has no attribute
    'loader'` from inside importlib."""
    with pytest.raises(typer.BadParameter, match="does not exist"):
        cli.load_aircraft(tmp_path / "vtail_smaple")


def test_a_file_that_is_not_a_python_module_says_so(tmp_path):
    not_python = tmp_path / "README.md"
    not_python.write_text("# not an aircraft\n", encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="not an importable Python module"):
        cli.load_aircraft(not_python)


def test_a_module_without_the_expected_symbol_says_which(tmp_path):
    module = tmp_path / "aircraft.py"
    module.write_text("SOMETHING_ELSE = 1\n", encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="does not define `AIRCRAFT`"):
        cli.load_aircraft(tmp_path)


def test_a_mistyped_mission_name_is_a_message_not_a_traceback(tmp_path):
    with pytest.raises(typer.BadParameter, match="does not exist"):
        cli.load_mission(tmp_path / "endurance_smaple.py")
