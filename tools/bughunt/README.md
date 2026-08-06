# Bug-hunt drivers, and what is left to run

The 2026-08-06 session built cross-checks and guards, then ran them to find what
running them would break. It found five defects, all fixed (FINDINGS §26-28).
These are the drivers it used, kept because two of them are unfinished work and
the third is worth reaching for on any future artifact.

**They were run on a 16 GB Mac, which is the binding constraint on everything
below.** A solve there peaks at 10.2 GB (`vtail_sample`) or 12.0 GB
(`vtail_rcv2`), `plan_parallel` returns width 1 at every station count, and only
~60% of wall clock reaches the CPU — the rest goes to memory compression. On a
machine with real headroom these are much cheaper, and `--parallel > 1` becomes
available for the first time.

## What is still to do, in priority order

### 1. The Hessian experiment — `hessian_experiment.py` (NOT YET RUN)

    uv run python tools/bughunt/hessian_experiment.py stage5.json

A 39-variable NLP takes **5.2 s per IPOPT iteration** and peaks at **10.18 GB**,
of which the CasADi graph is only 0.81 GB (§23.4). A dense 39x39 Hessian is
12 KB, so the gigabytes are not linear algebra on the KKT system — they are the
SECOND DERIVATIVE of a full LiftingLine solve embedded symbolically, four times
over. `opti.solve()` sets no `hessian_approximation`, so IPOPT computes that
exactly, and nothing in this project has ever asked what it costs. `grep -ri
"hessian\|BFGS\|limited-memory"` over `docs/` and `src/` returns nothing.

The script runs two paired single solves — stock settings, then
`ipopt.hessian_approximation = "limited-memory"` — baseline FIRST so a machine
degrading across the pair penalises the challenger rather than flattering it. It
reports wall clock, peak RAM, iteration count, objective and active set.

**It also answers a second, unrelated question.** The baseline arm is a real
converged solve of `vtail_sample` at stock settings, which is the freed-spar-
bound check §25.2 predicted: both ODs should leave the active set with
`spar_wall_center`/`spar_wall_outer` binding in their place. A truncated solve
cannot test that — an active set is a property of a converged one. Printed as
the `spar bounds` section.

Read the result the way §25.2 asks: direction and the change in the active set
are what one solve per arm can establish; the magnitude is not a precision
figure, and if the arms land on different objectives they may not be in the same
basin.

**If L-BFGS wins, do not leave it as a patch.** The script monkeypatches
`asb.Opti.solve` deliberately — an undeclared global that changes solver
behaviour is exactly the kind of knob this project keeps finding it was misled
by. It should become a declared default with the measurement behind it.

### 2. `-m solve`, which has never completed (NOT YET RUN)

    uv run pytest -m solve        # budget ~1 h; do not run anything alongside

Three tests. It was started once on the 16 GB Mac, ran **3 hours**, and was
killed without finishing. `test_a_real_run_writes_frames_and_relocates_them` was
the culprit at 1 h 39 min and is now capped with `max_iter=3` (~2 min).
`test_m3_optimize_smoke` is ~10 real solves and is deliberately NOT capped — it
asserts a CONVERGED champion, and those assertions are meaningless on a
truncated solve. The third,
`test_a_sweep_with_no_legal_point_says_so_at_note_zero`, is new and is the §28
regression: a full 18-point sweep on the heavier aeroplane, ~20 min.

### 3. Merge `main` (NOT YET DONE — user's instruction: stages first)

At the time of writing `origin/main` had **6 commits not on this branch** and
had changed `src/planeopt/solve.py` by +157 lines — the same file carrying all
five fixes. Read these two before merging rather than after:

- `de97e63` "A champion that meets its stability window was reported as missing
  it" — static-margin reporting, which the `mesh_convergence_check` work touches.
- `5356e7b` "A decision rode on a measurement `active_bounds` could never make" —
  `active_bounds` is what the Hessian experiment's spar verdict reads.

Two sessions independently fixed adjacent honesty bugs; expect real conflicts,
not textual ones.

### 4. Spar sizes must be purchasable (OPEN — see HANDOFF)

The optimizer returns `spar_od_center = 10.826 mm`, `spar_wall_center =
1.011 mm`. Carbon tube is a catalogue product sold as OD x ID pairs, and the
walls are the BINDING structural rows since the ceilings were freed — so
rounding down violates the constraint that sized them and rounding up adds mass
the objective was trading against. User instruction, 2026-08-06.

## The other two drivers

### `force_gate.py` — make the selection-time guard actually reject

    uv run python tools/bughunt/force_gate.py <runs-dir>

A healthy aeroplane never exercises `objective_is_mesh_trustworthy`'s reject
path, so a green battery proves nothing about it. This drops `aero.LL_CHECK_TOL`
to 1e-9 — a tolerance, not a fake, so the real check runs on the real champion —
and drives a whole `optimize()` through the rejecting branch. Verified
2026-08-06: three discrete studies each WON on objective and were each refused,
the champion gate skipped the flatness sweep and the sensitivity battery,
`mass_bump` was retained so the shadow price survived, and a complete artifact
was still written.

### `audit_run.py` — read an artifact for the claims it is entitled to make

    uv run python tools/bughunt/audit_run.py <run-dir> [<run-dir> ...]

Prints what a run SAYS, so a missing field shows as absent rather than as a
default. Every defect this session found was visible in an artifact and invisible
in a log. Worth pointing at any run before believing it.

## The transferable finding

All five defects are one shape: **a quantity the run computes, stores, and never
adjudicates.** What found them was execution, not insight — §26 needed a
differently shaped AIRCRAFT, §27.1 a flag nobody had used, §27.3 and §28 a run
degenerate enough to make a silent number loud. A guard evaluated only on inputs
that pass it has not been tested, and a number reported only where nobody reads
it has not been reported.
