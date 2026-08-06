"""planeopt — general-purpose small-aircraft MDO.

Docs are the spec: OPTIMIZATION_CONCEPT.md (formulation), MODEL_DETAILS.md
(module equations), EXECUTION_PLAN.md (this codebase's structure).
"""

import os as _os
import sys as _sys

__version__ = "0.1.0"

#: Whether the Accelerate pin below was applied in time to take effect.
#:
#: True   — pinned, so forked workers are safe.
#: False  — the pin came too late to bite. `solve.check_parallel` refuses a
#:          concurrent run, because the alternative is workers that segfault and
#:          report themselves as out of memory.
#: None   — nobody's call to make here: either this is not macOS, or the thread
#:          count was set deliberately in the environment before planeopt loaded
#:          and that choice is the caller's to own.
_FORK_SAFE_MACOS: bool | None = None


def _make_fork_safe_on_macos() -> None:
    """Pin Apple's Accelerate BLAS to one thread, before NumPy can start it.

    Without this, `--parallel > 1` does not merely underperform on macOS: every
    forked worker **segfaults**, and does so through the one path that reads as
    something else entirely. `_solve_many` sees the child die without writing to
    its pipe and records `worker died before reporting (OOM?)`, so a battery
    that is actually hitting a fork bug reports a memory problem and sends the
    user to turn the memory budget DOWN, which cannot help.

    The mechanism. NumPy's macOS wheels link Apple's Accelerate, which
    parallelises through Grand Central Dispatch. GCD is documented as not
    fork-safe: `fork` carries only the calling thread, so the child inherits a
    dispatch pool whose worker threads do not exist, and the first BLAS call in
    the child dereferences it. It needs no BLAS in the CHILD to arm — one matrix
    multiply anywhere in the parent starts the pool, and a solve does thousands.
    Measured on an M5 / macOS 26.5 / NumPy 2.4: 9 forked workers out of 9
    segfaulted (SIGSEGV, exit -11) with the pool up, and 9 of 9 completed with
    it capped at one thread.

    Capping costs this app nothing, which is what makes it the right fix rather
    than a trade. The binding resource here is RAM and the solver is
    single-core (`memory.py`), so multi-threaded BLAS was never buying the
    concurrency the app actually wants — and when solves DO run N-wide, one
    thread each is what you would ask for anyway. Measured against the numerics
    that actually run, at 1 thread and at 10 (M5, 10 cores): a NeuralFoil polar
    sweep 0.6 ms either way, a lifting-line trim 15.0 vs 15.1 ms, the ordering
    reversing between repeats. These are small matrices; there was never any
    parallelism in them to lose.

    It has to happen before NumPy is imported, because the pool is created on
    first use and no later setting can unmake it. This module is the earliest
    point every front end passes through — CLI, `python -m planeopt`, the GUI's
    child processes and the frozen bundle all import the package before they
    import anything that touches NumPy — which is the same reason
    `_point_casadi_at_the_bundle` lives here. `setdefault`, so someone who knows
    their build links a fork-safe BLAS can still say otherwise.

    Whether it landed in time is recorded rather than assumed. Importing NumPy
    before planeopt — an embedding, a notebook, a test that reaches for an array
    first — makes this a no-op, and a silent no-op here reappears hours later as
    a battery of segfaulting workers. `_FORK_SAFE_MACOS` carries that fact to
    `solve.check_parallel`, which is the point where it can still be acted on.

    An accidental miss and a deliberate override are recorded as different
    things, because they deserve different treatment: the first is refused, and
    the second is left alone. A `setdefault` that the enforcement point then
    overruled would be an override in name only.

    A preset of exactly `"1"` is safe whatever the import order was, and is
    checked first for that reason. It is the value this function would have set
    and the remedy `check_parallel`'s own error message prescribes, so it
    reaches us from the environment the process started with — Accelerate read
    it at ITS first use, which is the only moment that matters, and our own
    `setdefault` is then a no-op rather than a miss. Folding it in with the
    unset case instead closed a loop with no way out: a numpy-first process
    (embedding, notebook, array-first test) was refused, and the refusal told
    the user to set the variable they had already set.
    """
    global _FORK_SAFE_MACOS
    if _sys.platform != "darwin":
        return
    preset = _os.environ.get("VECLIB_MAXIMUM_THREADS")
    in_time = "numpy" not in _sys.modules
    _os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    if preset == "1":
        _FORK_SAFE_MACOS = True  # pinned from process start, import order moot
    elif preset is not None:
        _FORK_SAFE_MACOS = None  # the caller's decision, and the caller's risk
    else:
        _FORK_SAFE_MACOS = in_time


_make_fork_safe_on_macos()


def _point_casadi_at_the_bundle() -> None:
    """Tell CasADi where its own libraries live inside a frozen build.

    Every NLP solve loads a plugin (libcasadi_nlpsol_ipopt,
    libcasadi_interpolant_bspline, ...) through a runtime search that knows
    nothing about a PyInstaller bundle, and the failure mode is vicious: the
    plugin load raises inside each trim, every sweep point is recorded as
    infeasible, and the run dies far from the cause.

    Setting CASADIPATH is not enough on Windows. CasADi reads it with the C
    runtime linked into libcasadi, which keeps its own copy of the environment
    made at process start — an assignment from Python lands in a different copy
    and is simply not seen. (Setting the variable in the shell *before* launch
    does work, which is what makes this so confusing to diagnose.) So set the
    search path through CasADi's own API, which needs no environment at all,
    and keep the env var for any child process that inherits it.

    This lives in the package rather than a PyInstaller runtime hook so it holds
    for every front end (CLI today, GUI later).
    """
    bundle = getattr(_sys, "_MEIPASS", None)
    if not getattr(_sys, "frozen", False) or bundle is None:
        return
    _os.environ.setdefault("CASADIPATH", bundle)
    try:
        import casadi

        casadi.GlobalOptions.setCasadiPath(bundle)
    except Exception:  # a broken CasADi surfaces at first solve with real detail
        pass


_point_casadi_at_the_bundle()
