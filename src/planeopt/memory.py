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
"""

from __future__ import annotations

import json
import logging
import os
import sys
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
    """(total_gb, available_gb). Falls back to (0, 0) if the platform hides it."""
    probe = _windows_status if sys.platform == "win32" else _meminfo
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

    Linux only: `/proc/self/clear_refs` with the magic value 5 clears the peak
    (kernel >= 4.0). Everywhere else — and if the write is refused — the caller
    keeps the watermark behaviour and says so, because a number that silently
    changes meaning per platform is worse than one that is always conservative.
    """
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
    """
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
    # ru_maxrss is kB on Linux and bytes on macOS.
    scale = 1024 if sys.platform == "darwin" else 1024**2
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
            "back it off if the OOM killer takes a job"
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
