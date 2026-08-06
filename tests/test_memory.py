"""RAM accounting (planeopt.memory).

The budget dial is safety-critical in an unusual direction: getting it wrong
optimistically does not produce a bad answer, it produces no answer at all,
because the OOM killer takes the process several hours into a battery. So the
arithmetic is pure and injected-fact based, and this is where it is pinned.
"""

import json
import os
import sys
import time

import pytest

from planeopt import memory


PER = 13.0  # per-solve peak used throughout, matching the observed figure

#: The Mach probes only exist on macOS. Hoisted rather than pasted per test,
#: matching `needs_fork` in test_parallel.py — five copies had already drifted
#: into two different reason strings for the same condition.
darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")


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


def test_the_plan_probes_the_machine_at_most_once(monkeypatch):
    """Two facts, one probe — and none at all when the caller already has them.

    `machine_ram` returns total AND available together, so asking it twice buys
    nothing. It matters because of who calls this: the GUI's budget spinner
    replans on every arrow click and every keystroke, and on macOS each probe is
    a Mach round trip rather than a read of `/proc`.
    """
    calls = []
    monkeypatch.setattr(
        memory, "machine_ram", lambda: (calls.append("ram"), (32.0, 24.0))[1]
    )
    monkeypatch.setattr(memory, "swap_gb", lambda: 4.0)

    memory.plan_parallel(20.0, per_solve_gb=PER, fork=True, cpu_count=8)
    assert calls == ["ram"], f"probed {len(calls)}x for facts one call answers"

    calls.clear()
    memory.plan_parallel(
        20.0, per_solve_gb=PER, fork=True, cpu_count=8,
        available_gb=24.0, ceiling_gb=36.0,
    )
    assert calls == [], "facts the caller supplied must not be re-probed"


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


# --------------------------------------------------- per-solve, not per-batch
# HANDOFF issue 0c: the 2026-07-31 run recorded 14.45 GB against both winglet
# solves and the session read that as "the winglet pair costs 2.7 GB more than
# everything else". It does not — the RSS high-water mark only ever rises, so
# every member after the heaviest one inherits its number, and the step actually
# happened two phases earlier in the tail-type study. The winglet solves are the
# LIGHTEST in that run (27 design variables against the champion's 32).


@pytest.mark.skipif(sys.platform != "linux", reason="/proc/self/clear_refs is Linux-only")
def test_resetting_the_mark_makes_the_next_reading_per_solve():
    """Allocate, reset, and the mark must forget the allocation."""
    before = memory.peak_rss_gb()
    big = bytearray(400 * 1024 * 1024)
    raised = memory.peak_rss_gb()
    assert raised > before + 0.3, "the allocation should move the high-water mark"
    del big

    assert memory.reset_peak_rss() is True
    assert memory.peak_rss_gb() < raised - 0.3, "the mark still carries the old peak"


def test_reset_reports_failure_rather_than_lying(monkeypatch):
    """Where the reset is unavailable the caller must know, because the number
    then means 'largest solve so far' and not 'this solve'."""
    monkeypatch.setattr(memory.sys, "platform", "win32")
    assert memory.reset_peak_rss() is False

    monkeypatch.setattr(memory.sys, "platform", "linux")
    def _refuse(*a, **kw):
        raise OSError("permission denied")
    monkeypatch.setattr(memory.Path, "write_text", _refuse)
    assert memory.reset_peak_rss() is False


@darwin_only
def test_macos_sampler_makes_the_next_reading_per_solve():
    """The macOS half of the test above. No `clear_refs` here, so the same
    guarantee is reconstructed by sampling: after a reset the reading must
    describe THIS solve and not the largest one that came before it.

    Anonymous `mmap` rather than a `bytearray`, because the assertion is about
    the sampler and not about an allocator. Freeing a large `bytearray` does not
    reliably hand the pages back to macOS — the footprint stays up, correctly,
    because the process is still being billed for them — and a test written that
    way fails on a true reading. `mmap.close()` unmaps, which is the only way to
    ask for the memory back and mean it.
    """
    import mmap

    memory.reset_peak_rss()
    block = mmap.mmap(-1, 400 * 1024 * 1024)
    block.write(b"\xa5" * (400 * 1024 * 1024))  # fault the pages in; reserving is free
    time.sleep(3 * memory._FootprintSampler.INTERVAL_S)  # let the sampler see it
    raised = memory.peak_rss_gb()
    assert raised > 0.35, f"the allocation should show up in the peak, got {raised}"

    block.close()
    assert memory.reset_peak_rss() is True
    assert memory.peak_rss_gb() < raised - 0.3, "the reading still carries the old peak"


@darwin_only
def test_macos_sampler_is_inert_until_started():
    """`peak_rss_gb` answers 'how big did this get', so before any reset it must
    fall through to the watermark rather than report a spot footprint — which
    would read a solve that has just freed its memory as tiny."""
    sampler = memory._FootprintSampler()
    assert sampler.peak_gb() == 0.0


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs a real fork")
def test_the_fork_hook_resets_the_sampler_in_the_child(monkeypatch):
    """The at-fork hook must actually be attached to `_SAMPLER`.

    Its macOS twin below asserts the same guarantee through real Mach readings;
    this one asserts the wiring, and runs everywhere `fork` does — the hook is
    plain Python state, so a Linux CI can catch it coming unplugged. It is the
    registration that is easy to get wrong: hooks cannot be removed once added,
    so it moved from `__init__` (one per instance, forever) to one module-level
    registration, and a module-level hook naming the wrong object fails silently
    and only on the platform that forks.

    No thread is started. `_thread` stands in as the "was started" marker, so a
    sentinel exercises the reset without leaving a sampler running for the rest
    of the suite.
    """
    import multiprocessing as mp

    monkeypatch.setattr(memory._SAMPLER, "_peak", 9.9)
    monkeypatch.setattr(memory._SAMPLER, "_thread", object())

    def child(conn):
        s = memory._SAMPLER
        conn.send((s._peak, s._thread is None, s._pid == os.getpid(), s.peak_gb()))
        conn.close()

    ctx = mp.get_context("fork")
    rx, tx = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=child, args=(tx,))
    proc.start()
    tx.close()
    peak, thread_cleared, pid_is_own, reported = rx.recv()
    proc.join(30)

    assert proc.exitcode == 0
    assert peak == 0.0, "the child kept the parent's reading"
    assert thread_cleared, "the child kept a thread that the fork did not carry"
    assert pid_is_own, "the hook did not re-stamp the pid"
    assert reported == 0.0, "the child must refuse to answer, not guess"
    # ...and the parent is untouched by its child's reset.
    assert memory._SAMPLER._peak == 9.9


@darwin_only
def test_macos_forked_child_does_not_inherit_the_parents_peak():
    """A fork carries the memory but not the sampling thread, so the child's
    copy is a frozen parent reading attached to a dead thread — and a lock the
    child could block on forever. It must refuse to answer and let the caller
    fall back to its own `ru_maxrss`, which for a one-solve child is already the
    per-solve number. This is the path `solve._solve_worker` takes."""
    import multiprocessing as mp

    memory.reset_peak_rss()
    hog = bytearray(300 * 1024 * 1024)
    time.sleep(3 * memory._FootprintSampler.INTERVAL_S)
    parent_peak = memory.peak_rss_gb()
    del hog
    assert parent_peak > 0.25

    def child(conn):
        conn.send((memory._SAMPLER.peak_gb(), memory.peak_rss_gb()))
        conn.close()

    ctx = mp.get_context("fork")
    rx, tx = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=child, args=(tx,))
    proc.start()
    tx.close()
    sampled, reported = rx.recv()  # a deadlock here is the bug this test exists for
    proc.join(30)

    assert proc.exitcode == 0
    assert sampled == 0.0, "the child answered with the parent's sampler"
    # Bounded, not merely positive. This is the ONLY test of the macOS
    # forked-child fallback, and that fallback is `ru_maxrss` — whose unit is
    # bytes here and kilobytes on Linux. `> 0` passes just as happily on a
    # reading that is out by 1024, or by 1024**2, which is exactly the slip that
    # shipped once already (`_rusage_peak_gb`).
    assert 0.005 < reported < 64.0, f"implausible child peak {reported} GB — check units"


@darwin_only
def test_macos_readings_agree_with_the_system_tools():
    """The Mach structures are hand-laid `ctypes`, and a layout that drifted
    would return plausible-looking nonsense rather than an error. Pin each one
    against the tool that prints the same number."""
    import subprocess

    total, available = memory.machine_ram()
    hw_memsize = int(subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True
    ).stdout)
    assert total == pytest.approx(hw_memsize / memory.GB, rel=1e-9)
    assert 0 < available <= total

    swap_line = subprocess.run(
        ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True
    ).stdout
    swap_mb = float(swap_line.split("total =")[1].split("M")[0])
    assert memory.swap_gb() == pytest.approx(swap_mb / 1024, rel=1e-6)

    # phys_footprint has no command-line twin, but it must sit in the same
    # neighbourhood as RSS — the two differ by compression and by clean file
    # pages, not by orders of magnitude. This is what catches a unit slip: the
    # macOS ru_maxrss scale was wrong by 1024**2 until 2026-08-05.
    import resource

    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / memory.GB
    assert 0.2 * rss_gb < memory._darwin_footprint_gb() < 5 * rss_gb


@darwin_only
def test_macos_compressed_memory_is_reported_and_bounded():
    """It is a headline number on a Mac — several GB of what the machine is
    using can be sitting compressed — but it can never exceed the machine."""
    total, _ = memory.machine_ram()
    assert 0 <= memory.compressed_gb() <= total


# ------------------------------------------------------------ platform parity
# The macOS support was added to a working Windows/Linux app, so the standing
# requirement is that none of it is reachable anywhere else. These run on every
# platform and assert the gating itself, which is the part a Mac-only test run
# cannot otherwise check.


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_the_macos_probes_are_unreachable_off_macos(monkeypatch, platform):
    """Every Mach entry point must answer neutrally rather than reach for a
    libSystem that is not there.

    This asserts only what it owns: the Mach half. `reset_peak_rss` on the
    simulated "linux" pass is deliberately NOT checked here — the honest
    expectation would reduce to "whatever this host does", since a container
    with a masked `/proc`, or a kernel without `clear_refs`, returns False for
    reasons that have nothing to do with the macOS gating under test. Worse, on
    a real Linux host asserting it means PERFORMING the write, which resets this
    process's RSS watermark in the middle of a suite that measures it.
    `test_resetting_the_mark_makes_the_next_reading_per_solve` owns that path on
    the platform that has it, and `test_reset_reports_failure_rather_than_lying`
    already pins both ways it can refuse.
    """
    monkeypatch.setattr(memory.sys, "platform", platform)
    memory._libsystem.cache_clear()  # cached per process; re-decide it here
    memory._mach_host_port.cache_clear()
    try:
        assert memory._libsystem() is None
        assert memory.compressed_gb() == 0.0
        assert memory._darwin_ram() is None
        assert memory._darwin_swap() == 0.0
        assert memory._darwin_footprint_gb() == 0.0
    finally:
        memory._libsystem.cache_clear()
        memory._mach_host_port.cache_clear()


@pytest.mark.parametrize("platform,probe", [
    ("win32", "_windows_status"), ("linux", "_meminfo"), ("darwin", "_darwin_ram"),
])
def test_machine_ram_dispatches_to_the_right_probe(monkeypatch, platform, probe):
    """A platform reading another platform's probe is how macOS silently
    returned (0, 0) and switched off every guard in `plan_parallel`."""
    called = []
    for name in ("_windows_status", "_meminfo", "_darwin_ram"):
        monkeypatch.setattr(
            memory, name, lambda n=name: (called.append(n), (32.0, 16.0))[1]
        )
    monkeypatch.setattr(memory.sys, "platform", platform)
    assert memory.machine_ram() == (32.0, 16.0)
    assert called == [probe]


def test_a_platform_that_hides_its_ram_still_caps_the_budget_by_cpu(monkeypatch):
    """(0, 0) must not read as 'unlimited'. It is the one case where the
    hardware ceiling cannot bite, so the CPU cap has to be what holds — this is
    the regression that made a 60 GB budget mean 4 workers on a 16 GB Mac."""
    monkeypatch.setattr(memory, "machine_ram", lambda: (0.0, 0.0))
    monkeypatch.setattr(memory, "swap_gb", lambda: 0.0)
    width, _ = memory.plan_parallel(60.0, per_solve_gb=14.5, fork=True, cpu_count=2)
    assert width == 2

    # ...and with the machine known, the hardware is what decides.
    width, why = memory.plan_parallel(
        60.0, per_solve_gb=14.5, fork=True, cpu_count=10,
        available_gb=4.6, ceiling_gb=18.0,
    )
    assert width == 1 and "capped" in why


def test_the_run_peak_survives_the_per_solve_resets():
    """Resetting between solves means the process no longer knows the run's
    peak at the end — the tracker is what keeps it, and it must keep the MAX."""
    from planeopt import solve

    solve.RUN_PEAK.reset()
    assert solve.RUN_PEAK.gb == 0.0
    for gb in (11.7, 14.45, 11.7, None):
        solve.RUN_PEAK.observe(gb)
    assert solve.RUN_PEAK.gb == 14.45
    solve.RUN_PEAK.reset()
    assert solve.RUN_PEAK.gb == 0.0
