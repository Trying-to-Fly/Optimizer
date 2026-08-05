"""RAM accounting: how much this machine has, how much a solve actually took,
and how many solves may therefore run at once.

Why this module exists. RAM is the binding resource for this app and nothing
else is: one NLP solve peaks near 14.5 GB while using a single core of the
sixteen available (HANDOFF section 2). So a memory budget does NOT make a solve
faster — a solve is what it is. What it buys is CONCURRENCY: independent solves
within a batch (multistart, flatness, the re-solve battery, discrete studies)
run N-wide, and N is set by how many 14.5 GB peaks fit in the RAM the user is
willing to hand over. Getting that number wrong in the optimistic direction
costs a whole battery, because the OOM killer takes the process rather than the
job.

Everything here is stdlib-only and works on a frozen Windows build. psutil
would do the same job and is a perfectly good library, but a packaging-sensitive
app (packaging/README.md) is better off not adding a compiled dependency for
~40 lines of platform code.

**macOS is a third memory model, not a variant of the other two.** Three
differences change what the numbers here mean, and all three are handled below
rather than papered over:

1. There is no `/proc`, so every figure comes from Mach (`host_statistics64`,
   `task_info`) or `sysctl` through `ctypes` — the same approach the Windows
   path already takes with `GlobalMemoryStatusEx`.
2. Swap is **dynamic**: macOS creates and deletes swap files on demand instead
   of using a fixed partition, so there is no `SwapTotal` to read. `swap_gb`
   reports what is provisioned right now, which under-states the true ceiling —
   the safe direction, and the one this module always chooses.
3. Memory is **compressed** before it is swapped, and RSS does not count
   compressed pages. A solve whose pages get compressed under pressure would
   show a *falling* RSS while still owning the memory, so the per-solve peak is
   measured as `phys_footprint` (what Activity Monitor calls Memory, and what
   the kernel bills the process) rather than as RSS.

The failure mode differs too, which is worth knowing when reading the warnings
below: Linux has an OOM killer that takes the process outright, while macOS
grows swap until the disk fills and only then reports "system has run out of
application memory". A too-optimistic budget on a Mac therefore shows up as a
battery that thrashes for hours rather than one that dies quickly.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("planeopt")

GB = 1024**3

#: Fallback per-solve peak, used only until a run has measured one.
#:
#: **14.5, not 13.0 (2026-08-05).** 13 was the HANDOFF section 2 figure and it
#: has been overtaken by measurement: the 2026-08-05 battery peaked at 14.48 GB.
#: The error direction is not symmetric — `budget_to_parallel` DIVIDES by this,
#: so an optimistic figure hands out a concurrency the machine cannot honour and
#: the OOM killer takes the process, losing a battery measured in hours, while a
#: pessimistic one costs at most one fewer concurrent solve on a machine that is
#: single-core-bound anyway. Round up to the measurement, not down to the memory.
DEFAULT_PER_SOLVE_GB = 14.5

#: Never handed out, whatever the user asks for: the OS, the GUI, the desktop
#: and the page cache all need room, and a machine that swaps while IPOPT
#: factorizes is slower than solving one at a time.
RESERVE_GB = 2.0


# --- macOS: the Mach layer -------------------------------------------------
#
# Structure layouts are from <mach/vm_statistics.h>, <mach/task_info.h> and
# <sys/sysctl.h>. They are public kernel interfaces and stable, but a layout
# that ever did drift would produce nonsense rather than an error, so every
# caller sanity-checks the result against a bound it knows independently and
# reports "unknown" rather than a wrong number. `tests/test_memory.py` pins the
# readings against `vm_stat`, `sysctl` and `ru_maxrss` on any Mac that runs
# them.

_natural_t = ctypes.c_uint32
_integer_t = ctypes.c_int32

_HOST_VM_INFO64 = 4
_TASK_VM_INFO = 22


class _VMStatistics64(ctypes.Structure):
    """`vm_statistics64_data_t` — the counts behind `vm_stat`."""

    _fields_ = [
        ("free_count", _natural_t),
        ("active_count", _natural_t),
        ("inactive_count", _natural_t),
        ("wire_count", _natural_t),
        ("zero_fill_count", ctypes.c_uint64),
        ("reactivations", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64),
        ("pageouts", ctypes.c_uint64),
        ("faults", ctypes.c_uint64),
        ("cow_faults", ctypes.c_uint64),
        ("lookups", ctypes.c_uint64),
        ("hits", ctypes.c_uint64),
        ("purges", ctypes.c_uint64),
        ("purgeable_count", _natural_t),
        ("speculative_count", _natural_t),
        ("decompressions", ctypes.c_uint64),
        ("compressions", ctypes.c_uint64),
        ("swapins", ctypes.c_uint64),
        ("swapouts", ctypes.c_uint64),
        ("compressor_page_count", _natural_t),
        ("throttled_count", _natural_t),
        ("external_page_count", _natural_t),
        ("internal_page_count", _natural_t),
        ("total_uncompressed_pages_in_compressor", ctypes.c_uint64),
    ]


class _TaskVMInfo(ctypes.Structure):
    """`task_vm_info_data_t`, truncated at `phys_footprint`.

    The kernel appends fields to the tail of this structure between releases and
    fills only as many as the caller asks for, so a prefix is the portable way
    to read it: `task_info` is told the size of what is passed, not the size the
    kernel knows about.
    """

    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("region_count", _integer_t),
        ("page_size", _integer_t),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_peak", ctypes.c_uint64),
        ("device", ctypes.c_uint64),
        ("device_peak", ctypes.c_uint64),
        ("internal", ctypes.c_uint64),
        ("internal_peak", ctypes.c_uint64),
        ("external", ctypes.c_uint64),
        ("external_peak", ctypes.c_uint64),
        ("reusable", ctypes.c_uint64),
        ("reusable_peak", ctypes.c_uint64),
        ("purgeable_volatile_pmap", ctypes.c_uint64),
        ("purgeable_volatile_resident", ctypes.c_uint64),
        ("purgeable_volatile_virtual", ctypes.c_uint64),
        ("compressed", ctypes.c_uint64),
        ("compressed_peak", ctypes.c_uint64),
        ("compressed_lifetime", ctypes.c_uint64),
        ("phys_footprint", ctypes.c_uint64),
    ]


class _XswUsage(ctypes.Structure):
    """`struct xsw_usage` — what `sysctl vm.swapusage` prints."""

    _fields_ = [
        ("xsu_total", ctypes.c_uint64),
        ("xsu_avail", ctypes.c_uint64),
        ("xsu_used", ctypes.c_uint64),
        ("xsu_pagesize", ctypes.c_uint32),
        ("xsu_encrypted", ctypes.c_ubyte),
    ]


def _libsystem():
    """libSystem, loaded once and cached. None anywhere it is not macOS."""
    if sys.platform != "darwin":
        return None
    lib = getattr(_libsystem, "_cached", None)
    if lib is None:
        try:
            lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
            lib.mach_task_self.restype = ctypes.c_uint
            lib.mach_host_self.restype = ctypes.c_uint
        except OSError as e:  # a RAM probe must never break a solve
            log.debug("libSystem unavailable: %s", e)
            lib = False
        _libsystem._cached = lib
    return lib or None


def _vm_statistics() -> tuple[_VMStatistics64, int] | None:
    """(counts, page_size) from Mach, or None if the call fails."""
    lib = _libsystem()
    if lib is None:
        return None
    st = _VMStatistics64()
    count = ctypes.c_uint(ctypes.sizeof(st) // ctypes.sizeof(_natural_t))
    if lib.host_statistics64(
        lib.mach_host_self(), _HOST_VM_INFO64, ctypes.byref(st), ctypes.byref(count)
    ) != 0:
        return None
    return st, os.sysconf("SC_PAGE_SIZE")


def _darwin_ram() -> tuple[float, float] | None:
    """(total, available) GB on macOS.

    `available` is the macOS analogue of Linux's MemAvailable and is assembled
    the same way and for the same reason: free pages alone read catastrophically
    low on a Mac, because the kernel deliberately keeps almost nothing free and
    parks everything reclaimable in `inactive`. Free + inactive + speculative +
    purgeable is what a new allocation can claim without pushing anything to
    swap. Active, wired and compressor pages are excluded — the compressor's
    pages are memory that is already spoken for, merely stored small.
    """
    got = _vm_statistics()
    if got is None:
        return None
    st, page = got
    total = os.sysconf("SC_PHYS_PAGES") * page / GB
    available = (
        st.free_count + st.inactive_count + st.speculative_count + st.purgeable_count
    ) * page / GB
    if not 0 < total < 1e6 or not 0 <= available <= total:
        return None  # a layout that drifted; say nothing rather than something wrong
    return total, available


def compressed_gb() -> float:
    """Memory currently held compressed, in GB. 0.0 off macOS.

    Reported by `planeopt info` because it is the one line of a Mac's memory
    picture that has no counterpart on the platforms this app grew up on, and
    because it explains an otherwise baffling reading: a machine can show very
    little free memory, no swap in use, and still run a 14.5 GB solve, because
    several GB of what everything else owns is sitting compressed.
    """
    got = _vm_statistics()
    if got is None:
        return 0.0
    st, page = got
    return st.compressor_page_count * page / GB


def _darwin_swap() -> float:
    """Swap provisioned right now, GB. See the module docstring: on macOS this
    grows on demand, so it is a floor on the ceiling rather than the ceiling."""
    lib = _libsystem()
    if lib is None:
        return 0.0
    usage = _XswUsage()
    size = ctypes.c_size_t(ctypes.sizeof(usage))
    if lib.sysctlbyname(
        b"vm.swapusage", ctypes.byref(usage), ctypes.byref(size), None, 0
    ) != 0:
        return 0.0
    total = usage.xsu_total / GB
    return total if 0 <= total < 1e6 else 0.0


def _darwin_footprint_gb() -> float:
    """This process's `phys_footprint` in GB — what the kernel bills it.

    Not RSS: on macOS RSS omits compressed pages, so a process under memory
    pressure appears to shrink while owning exactly as much as before. Footprint
    is what Activity Monitor shows and what the memory limits are enforced
    against, so it is the number worth dividing a budget by.
    """
    lib = _libsystem()
    if lib is None:
        return 0.0
    info = _TaskVMInfo()
    count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(_natural_t))
    if lib.task_info(
        lib.mach_task_self(), _TASK_VM_INFO, ctypes.byref(info), ctypes.byref(count)
    ) != 0:
        return 0.0
    return info.phys_footprint / GB


class _FootprintSampler:
    """macOS stand-in for `/proc/self/clear_refs`: a per-solve peak by sampling.

    Linux can zero the kernel's high-water mark between solves, so a later
    reading means "this solve". macOS has no such call — `ru_maxrss` and
    `resident_size_peak` only ever rise — and a watermark misattributes memory
    to whichever phase happened to run after the heavy one (the 2026-07-31
    winglet reading, see `reset_peak_rss`). Sampling the current footprint on a
    background thread reconstructs the same quantity from the other side: reset
    the running maximum at the start of a solve, and what it holds at the end is
    that solve's peak.

    The sampling interval is chosen against what is being measured. A solve
    takes minutes and climbs to ~14.5 GB as IPOPT builds and factorizes, which
    is a seconds-scale ramp, so a quarter-second sample cannot miss the peak by
    anything that matters — and one `task_info` call four times a second is free
    next to the solve it is watching.

    Fork safety is the delicate part, and it needs both halves of what is below.
    A fork carries the memory but only the calling thread, so a child inherits
    this object with its sampler dead, its recorded peak belonging to the
    parent, and — if the fork landed while the sampler held it — **a locked lock
    that nothing will ever release**. Since `_solve_worker` calls
    `peak_rss_gb()` on itself, that is a solve worker deadlocking at the moment
    it tries to report, on a window of a few microseconds, thousands of times a
    battery. So:

    - the pid is checked BEFORE the lock is taken, which keeps a forked child
      off it entirely on the one path a child actually uses, and
    - `os.register_at_fork` replaces the lock outright in the child, so even a
      caller that does reach for it finds a fresh one.

    Neither alone is enough: the pid check leaves `restart` exposed, and the
    at-fork hook only runs for forks that Python itself performs. The child
    loses nothing by being locked out — it performs exactly one solve, so its
    own `ru_maxrss` is already the per-solve peak this class exists to recover.
    """

    INTERVAL_S = 0.25

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._peak = 0.0
        self._started = False
        self._pid = os.getpid()
        self._thread: threading.Thread | None = None
        if hasattr(os, "register_at_fork"):  # POSIX only; Windows never forks
            os.register_at_fork(after_in_child=self._reset_after_fork)

    def _reset_after_fork(self) -> None:
        """Drop the parent's lock, thread and reading — none of them survived."""
        self._lock = threading.Lock()
        self._peak = 0.0
        self._started = False
        self._thread = None
        self._pid = os.getpid()

    def restart(self) -> None:
        with self._lock:
            self._peak = _darwin_footprint_gb()
            self._started = True
            self._pid = os.getpid()
            if self._thread is not None and self._thread.is_alive():
                return
            # daemon: a sampler must never be the reason a run does not exit
            self._thread = threading.Thread(
                target=self._run, name="planeopt-footprint", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:  # pragma: no cover — timing-dependent background loop
        while True:
            now = _darwin_footprint_gb()
            with self._lock:
                if os.getpid() != self._pid:
                    return  # forked child: this thread is a ghost of the parent
                self._peak = max(self._peak, now)
            time.sleep(self.INTERVAL_S)

    def peak_gb(self) -> float:
        """The largest footprint seen since `restart`, or 0.0 if unusable.

        0.0 rather than the current footprint when the sampler was never
        started, because the caller's question is "how big did this get", and a
        spot reading answers a different one — quietly substituting it would
        report a solve that has just released its memory as tiny.

        The two guards are read before the lock, not inside it: this is the call
        a forked worker makes, and a child that took a lock inherited from its
        parent mid-update would never come back out of it.
        """
        if not self._started or os.getpid() != self._pid:
            return 0.0
        with self._lock:
            return max(self._peak, _darwin_footprint_gb())


#: Process-global for the same reason `solve.RUN_PEAK` is: the thing it samples
#: is process-global. Only ever started on macOS, and only by `reset_peak_rss`.
_SAMPLER = _FootprintSampler()


# --- what the machine has -------------------------------------------------


def _windows_status() -> tuple[float, float] | None:
    import ctypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    st = MemoryStatusEx()
    st.dwLength = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return st.ullTotalPhys / GB, st.ullAvailPhys / GB


def _meminfo() -> tuple[float, float] | None:
    """(total, available) GB from /proc/meminfo.

    MemAvailable, not MemFree: the kernel's own estimate of what a new
    allocation can actually claim, which counts reclaimable page cache. MemFree
    reads catastrophically low on a box that has just written run artifacts.
    """
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    vals = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            vals[key] = float(parts[0]) / (1024 * 1024)  # kB -> GB
    if "MemTotal" not in vals:
        return None
    return vals["MemTotal"], vals.get("MemAvailable", vals.get("MemFree", 0.0))


def machine_ram() -> tuple[float, float]:
    """(total_gb, available_gb). Falls back to (0, 0) if the platform hides it.

    A (0, 0) here is not cosmetic. `plan_parallel` derives its hardware ceiling
    from this, and a zero ceiling disables the cap entirely — so a platform this
    function does not know silently converts a mistyped budget into as many
    concurrent 14.5 GB solves as it will divide into. That is exactly what macOS
    did before it was taught here: `_meminfo` looked for `/proc`, found nothing,
    and every guard downstream quietly switched off.
    """
    probe = {"win32": _windows_status, "darwin": _darwin_ram}.get(
        sys.platform, _meminfo
    )
    try:
        got = probe()
    except Exception as e:  # noqa: BLE001 — a RAM probe must never break a solve
        log.debug("RAM probe failed: %s", e)
        got = None
    return (got or (0.0, 0.0))[:2]


def swap_gb() -> float:
    """Configured swap, which is why a budget may exceed physical RAM.

    Peak RSS is transient — two solves seldom peak in the same instant — so
    running 2-wide on a 25 GB box at a 14.5 GB peak works in practice with swap
    behind it (HANDOFF section 2 records exactly that, verified). Swap is the
    slack that makes the budget dial reach 2 on this hardware instead of being
    permanently pinned at 1.
    """
    if sys.platform == "win32":
        return 0.0  # the pagefile is dynamic; do not pretend to size it
    if sys.platform == "darwin":
        # macOS swap is dynamic too, but unlike the Windows pagefile it can be
        # sized: `vm.swapusage` reports what is provisioned at this instant, and
        # the kernel adds more files as they are needed. Reporting it therefore
        # under-states the ceiling rather than inventing one, which is the error
        # direction this module wants everywhere.
        return _darwin_swap()
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return 0.0
    for line in text.splitlines():
        if line.startswith("SwapTotal:"):
            parts = line.split()
            if len(parts) > 1:
                return float(parts[1]) / (1024 * 1024)
    return 0.0


# --- what a solve actually took -------------------------------------------


def reset_peak_rss() -> bool:
    """Reset this process's RSS high-water mark. Returns whether it worked.

    Without this, the in-process path reports a WATERMARK as if it were a
    per-solve peak: the mark only ever rises, so every later member of a battery
    inherits the largest solve that ran before it. That is not a harmless
    over-estimate — it misattributes memory to whichever phase happened to run
    afterwards. The 2026-07-31 run recorded 14.45 GB against both winglet
    solves and the whole session read that as "the winglet pair costs 2.7 GB
    more than everything else"; the step actually happened two phases earlier,
    in the tail-type study, and the winglet solves are the SMALLEST in the run
    (27 design variables against the champion's 32).

    Linux: `/proc/self/clear_refs` with the magic value 5 clears the peak
    (kernel >= 4.0).

    macOS has no equivalent — `ru_maxrss` and `resident_size_peak` only rise —
    so the same quantity is obtained from the other side: start (or restart) a
    background sampler over `phys_footprint` and let `peak_rss_gb` read its
    running maximum. The two routes disagree about nothing that matters; both
    answer "how big did THIS solve get", which is what the budget divides by.

    Everywhere else — and if the write is refused — the caller keeps the
    watermark behaviour and says so, because a number that silently changes
    meaning per platform is worse than one that is always conservative.
    """
    if sys.platform == "darwin":
        try:
            _SAMPLER.restart()
        except Exception as e:  # noqa: BLE001 — never break a solve over a probe
            log.debug("footprint sampler failed to start: %s", e)
            return False
        return True
    if sys.platform != "linux":
        return False
    try:
        Path("/proc/self/clear_refs").write_text("5", encoding="utf-8")
    except OSError:
        return False
    return True


def peak_rss_gb(children: bool = False) -> float:
    """High-water mark of this process (or of its reaped children) in GB.

    A forked solve worker calls this on itself just before reporting, which is
    the only place a genuine PER-SOLVE peak can be observed. In the sequential
    path the process high-water mark is a ceiling over the batch rather than one
    solve, which is still the right number to divide a budget by.

    On macOS a sampler may be running (`reset_peak_rss`), and where it is, its
    reading wins: it is per-solve where `ru_maxrss` is a watermark, and it
    counts compressed pages where `ru_maxrss` does not. In a forked child the
    sampler is deliberately unusable — the fork did not carry its thread — and
    the child's own `ru_maxrss` is already the per-solve number, so the fallback
    below is the right answer there rather than a degraded one.
    """
    if sys.platform == "darwin" and not children:
        sampled = _SAMPLER.peak_gb()
        if sampled > 0:
            return sampled
    if sys.platform == "win32":
        if children:
            return 0.0
        try:
            import ctypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            c = Counters()
            c.cb = ctypes.sizeof(Counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if not ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(c), c.cb
            ):
                return 0.0
            return c.PeakWorkingSetSize / GB
        except Exception:  # noqa: BLE001
            return 0.0
    try:
        import resource

        who = resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF
        maxrss = resource.getrusage(who).ru_maxrss
    except Exception:  # noqa: BLE001
        return 0.0
    # ru_maxrss is kB on Linux and BYTES on macOS, so the conversion to GB is
    # 1024**2 there and 1024**3 here. The macOS scale read 1024 until 2026-08-05
    # — six orders of magnitude out, which turned a 14.5 GB solve into a peak of
    # 15 million and would have been read straight into the budget arithmetic as
    # "this aircraft needs more RAM than exists". It was invisible because the
    # only assertion over it, `test_peak_rss_is_positive_and_in_gigabytes`, had
    # never been run on a Mac.
    scale = 1024**3 if sys.platform == "darwin" else 1024**2
    return maxrss / scale


def observed_peak_gb(runs_root: Path, limit: int = 25) -> float | None:
    """Largest per-solve peak recorded by recent runs, or None if never measured.

    This is what makes the budget arithmetic honest: dividing by a hard-coded
    a hard-coded figure is folklore, dividing by what this aircraft measured last week is data.
    """
    try:
        dirs = sorted((p for p in Path(runs_root).iterdir() if p.is_dir()), reverse=True)
    except OSError:
        return None
    peaks = []
    for d in dirs[:limit]:
        try:
            blob = json.loads((d / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        peak = (blob.get("diagnostics") or {}).get("peak_rss_gb")
        if isinstance(peak, (int, float)) and peak > 0:
            peaks.append(float(peak))
    return max(peaks) if peaks else None


# --- how many solves may run at once --------------------------------------


def parallel_supported() -> bool:
    """Whether this platform can run solves concurrently at all.

    Duplicated from solve.parallel_available deliberately: the GUI asks this
    question while drawing a dialog, and importing solve would drag AeroSandbox
    and CasADi in behind it — seconds of startup for a one-line answer.
    solve.check_parallel remains the enforcement point.
    """
    import multiprocessing as mp

    return "fork" in mp.get_all_start_methods()


def plan_parallel(
    budget_gb: float | None,
    per_solve_gb: float | None = None,
    available_gb: float | None = None,
    fork: bool | None = None,
    cpu_count: int | None = None,
    ceiling_gb: float | None = None,
) -> tuple[int, str]:
    """(width, human-readable reason) for a memory budget.

    Pure arithmetic over injected facts so it is testable without a 14.5 GB solve.
    The width is deliberately conservative: it floors rather than rounds, holds
    RESERVE_GB back for the OS, and never exceeds what is actually free even if
    the user asks for more.
    """
    if budget_gb is None:
        return 1, "no memory budget set — solving one at a time"

    per = per_solve_gb or DEFAULT_PER_SOLVE_GB
    if fork is None:
        fork = parallel_supported()
    if not fork:
        return 1, (
            f"memory budget {budget_gb:.0f} GB ignored: concurrent solves need the "
            "'fork' start method, which Windows does not have (solve.parallel_available). "
            "Solving one at a time."
        )

    if available_gb is None:
        _, available_gb = machine_ram()
    if ceiling_gb is None:
        total, _ = machine_ram()
        ceiling_gb = total + swap_gb()

    # The budget is a declaration, not a request: the user is saying how much of
    # their machine this app may have, and they may legitimately mean more than
    # is free right now (peaks are transient, and swap is real). So overshoot is
    # WARNED about, never silently clamped — a dial that quietly refuses to move
    # is worse than no dial. The one hard stop is a budget the hardware cannot
    # back at all, which is a typo rather than an intent.
    notes = []
    usable = budget_gb
    if available_gb > 0 and budget_gb > available_gb - RESERVE_GB:
        notes.append(
            f"exceeds the {max(0.0, available_gb - RESERVE_GB):.1f} GB free right now "
            f"({available_gb:.1f} GB less {RESERVE_GB:.0f} GB reserved) — relying on swap; "
            "back it off if jobs start dying or the machine starts thrashing"
        )
    if ceiling_gb > 0 and budget_gb > ceiling_gb - RESERVE_GB:
        usable = max(0.0, ceiling_gb - RESERVE_GB)
        notes.append(
            f"capped at {usable:.1f} GB — the machine has only {ceiling_gb:.1f} GB "
            "of RAM plus swap in total"
        )

    width = int(usable // per)
    cpus = cpu_count or os.cpu_count() or 1
    if width > cpus:
        notes.append(f"capped at {cpus} by CPU count")
        width = cpus
    if width < 1:
        notes.append(
            f"one solve needs ~{per:.1f} GB and only {usable:.1f} GB is usable — "
            "running anyway, but expect swapping or an OOM kill"
        )
        width = 1

    reason = f"{usable:.1f} GB usable / ~{per:.1f} GB per solve -> {width}-wide"
    if notes:
        reason += " (" + "; ".join(notes) + ")"
    return width, reason
