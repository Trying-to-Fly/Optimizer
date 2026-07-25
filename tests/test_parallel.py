"""_solve_many mechanics: fork-parallel batches must be result-identical to
the sequential path (NLP itself is stubbed — these are plumbing tests)."""

from types import SimpleNamespace

import pytest

from planeopt import solve

# Concurrency rides fork, so the width>1 tests are POSIX-only; the sequential
# path (the only one Windows uses) stays covered everywhere.
needs_fork = pytest.mark.skipif(
    not solve.parallel_available(), reason="platform has no fork start method"
)


def _fake_nlp_factory():
    def fake(aircraft, mission, **kw):
        if kw.get("inits") == "explode":
            raise RuntimeError("boom: infeasible")
        return {"objective_value": float(kw.get("extra_mass_kg", 1.0)), "kw": kw}

    return fake


@needs_fork
def test_parallel_matches_sequential(monkeypatch):
    monkeypatch.setattr(solve, "_solve_nlp", _fake_nlp_factory())
    jobs = [
        ("a", {}),
        ("b", {"extra_mass_kg": 2.0}),
        ("c", {"inits": "explode"}),
        ("d", {"extra_mass_kg": 4.0}),
    ]
    seq = solve._solve_many(None, None, jobs, parallel=1)
    par = solve._solve_many(None, None, jobs, parallel=2)
    assert seq == par
    assert par["b"]["objective_value"] == 2.0
    assert "failed" in par["c"] and "boom" in par["c"]["failed"]


def test_prep_snapshot_reaches_each_job(monkeypatch):
    """prep(key) mutations must be seen by that job only (fork snapshot),
    and restore() must leave the parent at baseline afterwards."""
    aircraft = SimpleNamespace(mode="baseline")

    def fake(ac, mission, **kw):
        return {"objective_value": 0.0, "mode_seen": ac.mode}

    monkeypatch.setattr(solve, "_solve_nlp", fake)
    jobs = [("red", {}), ("blue", {}), ("green", {})]
    widths = (1, 2) if solve.parallel_available() else (1,)
    for width in widths:
        res = solve._solve_many(
            aircraft, None, jobs, parallel=width,
            prep=lambda key: setattr(aircraft, "mode", key),
            restore=lambda: setattr(aircraft, "mode", "baseline"),
        )
        assert {k: r["mode_seen"] for k, r in res.items()} == {
            "red": "red", "blue": "blue", "green": "green"
        }
        assert aircraft.mode == "baseline"


def test_empty_batch_is_a_noop():
    width = 2 if solve.parallel_available() else 1
    assert solve._solve_many(None, None, [], parallel=width) == {}


def test_width_one_never_needs_fork(monkeypatch):
    """Sequential is the portable path — it must not consult fork at all."""
    monkeypatch.setattr(solve, "parallel_available", lambda: False)
    monkeypatch.setattr(solve, "_solve_nlp", _fake_nlp_factory())
    solve.check_parallel(1)
    assert solve._solve_many(None, None, [("a", {})], parallel=1)["a"]["objective_value"] == 1.0


def test_width_above_one_is_rejected_without_fork(monkeypatch):
    """On Windows the failure must be an explanation, not a spawn/pickle traceback."""
    monkeypatch.setattr(solve, "parallel_available", lambda: False)
    with pytest.raises(RuntimeError) as e:
        solve.check_parallel(2)
    assert "fork" in str(e.value) and "parallel=1" in str(e.value)
