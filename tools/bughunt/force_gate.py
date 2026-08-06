"""Stage 3 — make the selection-time guard FIRE in a real run.

A healthy aeroplane never exercises `objective_is_mesh_trustworthy`'s reject
path, so a green battery proves nothing about it. `tests/test_guard_gate.py`
covers the predicate with fakes; this drives the WHOLE optimize() through the
rejecting branch and checks that the artifact it writes is complete and says so.

The forcing is a tolerance, not a fake: `aero.LL_CHECK_TOL` drops to 1e-9, so
the real mesh check runs on the real champion and its real (tiny) drag delta is
read as non-convergence. Nothing in the model is stubbed.

Usage:  uv run python force_gate.py <runs-dir>
"""
import sys
from pathlib import Path

import planeopt  # noqa: F401  — must precede numpy (README: BLAS pinning)
from planeopt import aero, cli, solve

runs = Path(sys.argv[1])
runs.mkdir(parents=True, exist_ok=True)

print(f"LL_CHECK_TOL {aero.LL_CHECK_TOL} -> 1e-9")
aero.LL_CHECK_TOL = 1e-9

ac, ac_file = cli.load_aircraft(Path("aircraft/vtail_sample"))
ms, ms_file = cli.load_mission(Path("missions/endurance_sample.py"))

result, run_dir = solve.optimize(
    ac, ms, runs, input_files=[ac_file, ms_file],
    multistart=1, flatness=True, parallel=1, max_iter=3,
)
print(f"RUN_DIR {run_dir}")
