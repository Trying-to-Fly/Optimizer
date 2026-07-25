"""planeopt — general-purpose small-aircraft MDO.

Docs are the spec: OPTIMIZATION_CONCEPT.md (formulation), MODEL_DETAILS.md
(module equations), EXECUTION_PLAN.md (this codebase's structure).
"""

import os as _os
import sys as _sys

__version__ = "0.1.0"

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
