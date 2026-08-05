"""_solve_many mechanics: fork-parallel batches must be result-identical to
the sequential path (NLP itself is stubbed — these are plumbing tests)."""

import sys
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
    # peak_rss_gb is a MEASUREMENT of the run, not part of its result: the
    # sequential path reads a batch-wide high-water mark and a forked worker
    # reads its own, so the two legitimately differ. Everything the solve
    # actually produced must be identical at any width.
    strip = lambda d: {k: {kk: vv for kk, vv in v.items() if kk != "peak_rss_gb"}
                       for k, v in d.items()}
    assert strip(seq) == strip(par)
    assert all("peak_rss_gb" in r for r in par.values())
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


# ------------------------------------------------------- macOS fork safety
# NumPy's macOS wheels link Apple's Accelerate, which parallelises through Grand
# Central Dispatch, and GCD is not fork-safe. One matrix multiply in the parent
# starts the dispatch pool; every worker forked afterwards then segfaults on its
# first BLAS call. Measured on an M5 / macOS 26.5 / NumPy 2.4: 9 of 9 workers
# died with the pool up, 9 of 9 survived with VECLIB_MAXIMUM_THREADS=1
# (`planeopt._make_fork_safe_on_macos`).
#
# What makes it worth a guard rather than a note is how it presents. The child
# dies before writing to its pipe, `_solve_many` reads EOF, and the result says
# "worker died before reporting (OOM?)" — so a fork bug arrives dressed as a
# memory problem, hours into a battery, and sends the user to lower the memory
# budget, which cannot help.


def test_macos_fork_guard_refuses_a_width_it_cannot_honour(monkeypatch):
    """When the pin missed, refuse UP FRONT and say why. The message has to name
    the cause, because the symptom points somewhere else entirely."""
    import planeopt

    monkeypatch.setattr(solve, "parallel_available", lambda: True)
    monkeypatch.setattr(planeopt, "_FORK_SAFE_MACOS", False)
    with pytest.raises(RuntimeError) as e:
        solve.check_parallel(2)
    msg = str(e.value)
    assert "Accelerate" in msg and "segfault" in msg
    assert "VECLIB_MAXIMUM_THREADS" in msg, "must say what to actually set"
    assert "parallel=1" in msg, "must say what still works"

    solve.check_parallel(1)  # sequential never forks, so it is never blocked


@pytest.mark.parametrize("state", [None, True])
def test_fork_guard_is_silent_where_it_does_not_apply(monkeypatch, state):
    """None is every non-macOS platform and True is a macOS process that got the
    pin in time. Neither may be affected — this guard must not become a second
    way for Windows or Linux to refuse a width that works there."""
    import planeopt

    monkeypatch.setattr(solve, "parallel_available", lambda: True)
    monkeypatch.setattr(planeopt, "_FORK_SAFE_MACOS", state)
    solve.check_parallel(4)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
def test_macos_pin_is_in_place_for_this_process():
    """The pin only works if it lands before NumPy is imported, so assert the
    real process state rather than the function in isolation — importing
    planeopt is exactly what a run does."""
    import os

    import planeopt

    assert os.environ.get("VECLIB_MAXIMUM_THREADS") == "1"
    assert planeopt._FORK_SAFE_MACOS is True


@needs_fork
def test_forked_workers_survive_real_blas_in_the_parent(monkeypatch):
    """The end-to-end version, through `_solve_many` itself: warm the parent's
    BLAS the way a nominal solve does, then run a batch N-wide and require every
    worker back alive. Without the pin this fails on macOS with every member
    recorded as `worker died before reporting (OOM?)`."""
    import numpy as np

    def fake(aircraft, mission, **kw):
        a = np.random.rand(400, 400)  # BLAS in the CHILD — where it crashed
        return {"objective_value": float((a @ a).sum())}

    np.random.rand(400, 400) @ np.random.rand(400, 400)  # ...and in the parent
    monkeypatch.setattr(solve, "_solve_nlp", fake)
    res = solve._solve_many(None, None, [(f"m{i}", {}) for i in range(4)], parallel=3)

    died = {k: v["failed"] for k, v in res.items() if "failed" in v}
    assert not died, f"forked workers died: {died}"
    assert all(r["objective_value"] > 0 for r in res.values())
