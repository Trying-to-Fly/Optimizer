"""RAM accounting (planeopt.memory).

The budget dial is safety-critical in an unusual direction: getting it wrong
optimistically does not produce a bad answer, it produces no answer at all,
because the OOM killer takes the process several hours into a battery. So the
arithmetic is pure and injected-fact based, and this is where it is pinned.
"""

import json

import pytest

from planeopt import memory


PER = 13.0  # per-solve peak used throughout, matching the observed figure


def plan(budget, **kw):
    kw.setdefault("per_solve_gb", PER)
    kw.setdefault("fork", True)
    kw.setdefault("available_gb", 24.0)
    kw.setdefault("ceiling_gb", 34.0)
    kw.setdefault("cpu_count", 16)
    return memory.plan_parallel(budget, **kw)


def test_no_budget_means_sequential():
    """The default has to stay exactly what it was: one solve at a time."""
    width, why = plan(None)
    assert width == 1
    assert "no memory budget" in why


def test_budget_divides_into_concurrent_solves():
    assert plan(13.0)[0] == 1
    assert plan(25.9)[0] == 1  # floors, never rounds up into an OOM
    assert plan(26.0)[0] == 2


def test_the_dial_reaches_two_wide_on_this_hardware():
    """A 26 GB budget must actually reach 2-wide against a 25 GB machine with
    swap. Clamping to free RAM instead would pin the dial at 1 forever and make
    the whole feature decorative — HANDOFF section 2 records 2-wide as verified.
    """
    width, why = plan(26.0, available_gb=23.6, ceiling_gb=35.4)
    assert width == 2
    assert "swap" in why  # and it says so rather than pretending it is free


def test_absurd_budget_is_capped_by_the_hardware():
    """A typo cannot conjure workers the machine cannot back."""
    width, why = plan(500.0)
    assert width == 2  # (34 - 2 reserved) // 13
    assert "capped" in why


def test_cpu_count_caps_the_width():
    """Memory is the binding resource, but never hand out more workers than
    cores — the solver is single-core, so past that they only contend."""
    assert plan(500.0, ceiling_gb=1000.0, cpu_count=2)[0] == 2


def test_platform_without_fork_is_always_sequential():
    """Windows cannot fork, so the budget is honestly reported as inert rather
    than silently ignored (solve.check_parallel is the enforcement point)."""
    width, why = plan(64.0, fork=False)
    assert width == 1
    assert "fork" in why and "Windows" in why


def test_tiny_budget_still_runs_one_solve_and_warns():
    """Refusing to run at all would be worse than running slowly; say so."""
    width, why = plan(4.0, ceiling_gb=8.0, available_gb=8.0)
    assert width == 1
    assert "OOM" in why or "swapping" in why


def test_machine_ram_and_swap_are_plausible():
    """The probe is platform code; assert only what must be true anywhere."""
    total, avail = memory.machine_ram()
    assert total >= 0 and avail >= 0
    assert avail <= total or total == 0  # available never exceeds physical
    assert memory.swap_gb() >= 0


def test_peak_rss_is_positive_and_in_gigabytes():
    """A unit slip here (kB vs bytes) would silently scale the width by 1e6."""
    peak = memory.peak_rss_gb()
    assert 0.005 < peak < 64.0, f"implausible peak {peak} GB — check unit scaling"


def test_observed_peak_reads_the_largest_recent_run(tmp_path):
    for name, peak in [("20260101T000000", 9.5), ("20260102T000000", 12.25)]:
        d = tmp_path / name
        d.mkdir()
        (d / "run.json").write_text(
            json.dumps({"diagnostics": {"peak_rss_gb": peak}}), encoding="utf-8"
        )
    assert memory.observed_peak_gb(tmp_path) == 12.25


def test_observed_peak_is_none_when_never_measured(tmp_path):
    """No runs yet, or older runs that predate the instrumentation — the caller
    falls back to the documented default rather than dividing by zero."""
    assert memory.observed_peak_gb(tmp_path) is None
    d = tmp_path / "20260101T000000"
    d.mkdir()
    (d / "run.json").write_text(json.dumps({"diagnostics": {}}), encoding="utf-8")
    assert memory.observed_peak_gb(tmp_path) is None


def test_observed_peak_survives_a_corrupt_run(tmp_path):
    """A half-written run.json from a killed job must not break the next run."""
    bad = tmp_path / "20260101T000000"
    bad.mkdir()
    (bad / "run.json").write_text("{not json", encoding="utf-8")
    good = tmp_path / "20260102T000000"
    good.mkdir()
    (good / "run.json").write_text(
        json.dumps({"diagnostics": {"peak_rss_gb": 11.0}}), encoding="utf-8"
    )
    assert memory.observed_peak_gb(tmp_path) == 11.0


def test_measured_peak_beats_the_default():
    """The whole point of recording peaks: the arithmetic improves with data."""
    assumed = plan(30.0, per_solve_gb=None)[0]  # falls back to DEFAULT_PER_SOLVE_GB
    measured = plan(30.0, per_solve_gb=9.0)[0]  # a lighter aircraft, measured
    assert assumed == 2 and measured == 3


@pytest.mark.parametrize("budget", [0.0, -1.0])
def test_nonpositive_budget_never_yields_zero_workers(budget):
    """A zero width would deadlock the batch loop."""
    assert plan(budget)[0] >= 1
