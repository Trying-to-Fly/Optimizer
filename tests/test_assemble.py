"""Reading a run artifact back — `planeopt report`, `brief`, `build`, `--warm-start`.

Runs move between machines that are not upgraded together (the Mac and the WSL
box of docs/HANDOFF), so this file is mostly about a `run.json` that does not
match the code reading it — in EITHER direction.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from planeopt.report import assemble
from planeopt.types import RunResult

MINIMAL = {
    "aircraft": "fixture_v1",
    "mission": "endurance_sample",
    "objective": "endurance",
    "status": "M2",
    "created": "2026-07-25T12:00:00",
}


def _run(tmp_path, **overrides):
    run_dir = tmp_path / "20260725T120000-endurance_sample-fixture"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps({**MINIMAL, **overrides}), encoding="utf-8"
    )
    return run_dir


def test_a_minimal_artifact_loads(tmp_path):
    result = assemble.load(_run(tmp_path))
    assert result.aircraft == "fixture_v1"
    assert result.constraints == {}
    assert result.notes == []


def test_a_field_a_newer_version_added_is_dropped_not_fatal(tmp_path, caplog):
    """`RunResult(**data)` refuses an unexpected keyword, so a run written by a
    NEWER planeopt could not be read by an older one at all — `report`, `brief`,
    `build` and `--warm-start` all died on a TypeError naming the new field.
    """
    run_dir = _run(tmp_path, airworthiness={"legal": True}, provenance="wsl")

    with caplog.at_level("WARNING", logger="planeopt"):
        result = assemble.load(run_dir)

    assert result.aircraft == "fixture_v1"
    assert not hasattr(result, "airworthiness")
    # Dropped, but never silently: the artifact says more than this build shows.
    assert "airworthiness" in caplog.text
    assert "provenance" in caplog.text


def test_every_field_but_the_identity_strings_may_be_absent(tmp_path):
    """An OLDER artifact is the other direction, and already worked. Pin it, so
    a new REQUIRED field cannot be added without noticing it breaks old runs."""
    required = {
        f.name
        for f in dataclasses.fields(RunResult)
        if f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
    }
    assert required == set(MINIMAL), (
        "a field without a default was added to RunResult, so every run.json "
        "written before it can no longer be loaded"
    )


@pytest.mark.parametrize("constraints", [None, {}, {"stall_ok": True}])
def test_constraints_is_always_a_dict(tmp_path, constraints):
    assert isinstance(assemble.load(_run(tmp_path, constraints=constraints)).constraints, dict)
