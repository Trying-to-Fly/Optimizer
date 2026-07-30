"""Stopping a multi-hour battery and getting the machine back.

The pause is at MEMBER boundaries, and that is a physical limit rather than a
shortcut: a solve in progress is ~13 GB of CasADi graph plus IPOPT barrier,
filter and factorization state, none of it serialisable through CasADi. Freeing
that memory necessarily destroys the solve, so the only pause that both releases
memory AND loses nothing is one that waits for the member to finish.

These use fake solves — the properties are about the batch runner, not the NLP.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from planeopt import solve


@pytest.fixture()
def fake_solves(monkeypatch):
    """Replace the NLP with a counter, so a 'battery' runs in milliseconds."""
    calls = []

    def fake(aircraft, mission, **kw):
        calls.append(kw)
        return {
            "objective_value": 100.0 + len(calls),
            "dv": {"span": 2.0},
            # numpy and tuples are what a real result carries, and what a naive
            # json.dumps would mangle
            "clmax_ab_used": (np.float64(1.25), np.float64(0.11)),
            "V_ms": np.float64(9.5),
        }

    monkeypatch.setattr(solve, "_solve_nlp", fake)
    return calls


def _jobs(n):
    return [(f"m{i}", {}) for i in range(n)]


# ------------------------------------------------------------------ the cache

def test_a_finished_member_is_not_solved_twice(tmp_path, fake_solves):
    cache = solve._SolveCache(tmp_path)
    first = solve._solve_many(None, None, _jobs(3), label="phase", cache=cache)
    assert len(fake_solves) == 3

    second = solve._solve_many(None, None, _jobs(3), label="phase", cache=cache)
    assert len(fake_solves) == 3, "cached members must not re-solve"
    assert [second[k]["objective_value"] for k in second] == [
        first[k]["objective_value"] for k in first
    ]


def test_cached_results_survive_the_json_round_trip(tmp_path, fake_solves):
    """A checkpoint that reloads a float as the string 'np.float64(9.5)' is
    worse than no checkpoint — every consumer downstream does arithmetic."""
    cache = solve._SolveCache(tmp_path)
    solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)
    reloaded = solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)["m0"]

    assert isinstance(reloaded["V_ms"], float) and reloaded["V_ms"] == 9.5
    assert isinstance(reloaded["dv"]["span"], float)
    assert [float(v) for v in reloaded["clmax_ab_used"]] == [1.25, 0.11]


def test_cache_keys_are_filesystem_safe(tmp_path):
    """Member keys are floats (flatness spans) and free text (study candidates),
    neither of which is guaranteed to be a legal filename."""
    cache = solve._SolveCache(tmp_path)
    for label, key in [("flatness sweep", 1.5), ("study motor_mount", "pusher"),
                       ("re-solve battery", "printed_mass_x1.10")]:
        cache.put(label, key, {"objective_value": 1.0})
        assert cache.get(label, key) == {"objective_value": 1.0}
    assert len(list(tmp_path.glob("*.json"))) == 3


def test_a_corrupt_checkpoint_is_ignored_not_fatal(tmp_path, fake_solves):
    cache = solve._SolveCache(tmp_path)
    solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)
    next(tmp_path.glob("*.json")).write_text("{not json", encoding="utf-8")

    solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)
    assert len(fake_solves) == 2, "an unreadable entry should just re-solve"


def test_a_half_written_checkpoint_is_never_read(tmp_path):
    """Written via a .part file and renamed, so a run killed mid-write cannot
    leave something the next run trusts."""
    cache = solve._SolveCache(tmp_path)
    cache.put("phase", "m0", {"objective_value": 1.0})
    assert list(tmp_path.glob("*.json.part")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1


# ------------------------------------------------------------------ the pause

def test_pause_stops_at_the_next_member_boundary(tmp_path, fake_solves):
    pause = tmp_path / "PAUSE"
    pause.write_text("", encoding="utf-8")
    cache = solve._SolveCache(tmp_path / "ckpt")

    with pytest.raises(solve.RunPaused):
        solve._solve_many(None, None, _jobs(4), label="phase",
                          cache=cache, pause_file=pause)
    # exactly one member ran: the pause is honoured after the first completes,
    # never mid-solve
    assert len(fake_solves) == 1


def test_paused_work_is_kept_and_resumed(tmp_path, fake_solves):
    pause = tmp_path / "PAUSE"
    cache = solve._SolveCache(tmp_path / "ckpt")
    pause.write_text("", encoding="utf-8")
    with pytest.raises(solve.RunPaused):
        solve._solve_many(None, None, _jobs(3), label="phase",
                          cache=cache, pause_file=pause)
    assert len(fake_solves) == 1

    pause.unlink()  # what the CLI does on resume
    results = solve._solve_many(None, None, _jobs(3), label="phase",
                                cache=cache, pause_file=pause)
    assert len(fake_solves) == 3, "the paused member must not be redone"
    assert set(results) == {"m0", "m1", "m2"}


def test_no_pause_file_means_no_pause(tmp_path, fake_solves):
    cache = solve._SolveCache(tmp_path)
    results = solve._solve_many(None, None, _jobs(3), label="phase",
                                cache=cache, pause_file=tmp_path / "absent")
    assert len(results) == 3


def test_batches_are_unchanged_without_checkpointing(fake_solves):
    """The feature is opt-in; the default path must behave exactly as before."""
    results = solve._solve_many(None, None, _jobs(3), label="phase")
    assert len(results) == 3 and len(fake_solves) == 3
    assert all("solve_minutes" in r for r in results.values())


def test_a_failed_member_is_checkpointed_too(tmp_path, monkeypatch):
    """Re-running must not repeat a 30-minute timeout that already has its
    answer — a failure is a result."""
    def boom(aircraft, mission, **kw):
        raise RuntimeError("Infeasible_Problem_Detected after 131 iterations")

    monkeypatch.setattr(solve, "_solve_nlp", boom)
    cache = solve._SolveCache(tmp_path)
    first = solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)
    assert "failed" in first["m0"]

    calls = []
    monkeypatch.setattr(solve, "_solve_nlp", lambda *a, **k: calls.append(1))
    second = solve._solve_many(None, None, _jobs(1), label="phase", cache=cache)
    assert calls == [], "a recorded failure should not be re-attempted"
    assert "failed" in second["m0"]


def test_jsonable_handles_what_results_actually_contain():
    out = solve._jsonable(
        {"a": np.float64(1.5), "b": (np.int64(2), 3), "c": np.array([1.0, 2.0]),
         "d": None, "e": True, "f": "text"}
    )
    assert out == {"a": 1.5, "b": [2.0, 3.0], "c": [1.0, 2.0],
                   "d": None, "e": True, "f": "text"}
    json.dumps(out)  # must not raise
