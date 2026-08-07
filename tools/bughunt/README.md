# Bug-hunt drivers, and what is left to run

The 2026-08-06 session built cross-checks and guards, then ran them to find what
running them would break. It found five defects, all fixed (FINDINGS §26-28).
These are the drivers it used, kept because two of them are unfinished work and
the third is worth reaching for on any future artifact.

**They were first run on a 16 GB Mac, which was the binding constraint on
everything below.** A solve there peaks at 10.2 GB (`vtail_sample`) or 12.0 GB
(`vtail_rcv2`), `plan_parallel` returns width 1 at every station count, and only
~60% of wall clock reaches the CPU — the rest goes to memory compression.

**Stage 1 has since been run on a 25 GB Linux box, and the headroom is not
cosmetic.** 99% CPU sustained and swap never touched across a 12.02 GB peak, so
the timings below are true solver cost rather than solver cost plus compression.
`plan_parallel` reaches width 2 there and `--parallel > 1` is available for the
first time. Two cautions when comparing across the two machines:

- **Peak RAM is not the same quantity on both.** macOS reads `phys_footprint`
  through the sampler; Linux reads the `ru_maxrss` high-water mark. They measure
  different things and 12.02 GB here is not 10.2 GB there plus 1.8.
- **A paired experiment must not be spread across cores.** Stage 1's arms run
  back to back, baseline first, on purpose; running them concurrently on a
  roomier machine would let them contend and destroy the comparison. Headroom
  buys each arm a clean run, not two arms at once.

## What is still to do, in priority order

### 1. The Hessian experiment — `hessian_experiment.py` (RUN 2026-08-07 — L-BFGS LOST)

    uv run python tools/bughunt/hessian_experiment.py docs/studies/hessian_stage5.json

**Answered. Do not adopt `limited-memory`; the exact Hessian is cheaper here.**
Result in `docs/studies/hessian_stage5.json`, read in FINDINGS §29. Run on the
25 GB Linux box, not the Mac — 99% CPU throughout and swap never touched, so
neither arm paid the memory-compression tax that distorts the Mac's timings.

| | exact Hessian | limited-memory |
|---|---|---|
| wall clock | **17.38 min** | 31.12 min (hit the 30 min cap) |
| peak RAM | 12.02 GB | **8.68 GB** |
| status | **Solve_Succeeded** | `Maximum_WallTime_Exceeded`, 871 iterations |
| objective | **119.7810 min** | never reached one |

L-BFGS did drop the second-derivative graph exactly as theory says — 3.34 GB,
28% less memory — and then failed to convert it into an answer. The README's
standing instruction ("if L-BFGS wins, make it a declared default") therefore
does NOT trigger, and the monkeypatch stays a monkeypatch.

Honest limit: 30 min is `SOLVE_TIMEOUT_MIN`, a cap and not a divergence proof,
and §25.2 records a freed-spar arm that needed 45 min. What is established is
that L-BFGS is decisively worse at the timeout this project actually runs with.
Anyone reopening it should raise the cap for both arms, not just the challenger.

The baseline arm also settled the freed-spar question it was doubling as, and
reproduced §25.2's Mac numbers exactly on Linux — 119.7810 min, 1.8411 kg,
`spar_od_center` 15.131 mm, `spar_od_outer` 6.530 mm. See FINDINGS §29.1.

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

### 3. Merge `main` (DONE 2026-08-06, commit `1ff0917`)

`main` and `macos-support` are the same commit; there is nothing left to merge.
The warning below was right, and worth keeping for the shape of what it caught:

> Two sessions independently fixed adjacent honesty bugs; expect real conflicts,
> not textual ones.

`git merge` reported no conflicts and 524 tests passed. The defect was a
SENTENCE. `sm_read_at` (`de97e63`) explains a headline whose static margin is
read at a different speed from the NLP's, and states its premise as "the sweep
picks the best AIRWORTHY point" — which §28, written the same day on the other
branch, had just shown can FAIL. Merged, that reassurance landed one line from a
champion trimming at 4.2x its control limit. Both sentences true; together an
all-clear on an aeroplane with no legal operating point. `candidates_source` is
now threaded into `sm_read_at`, which says "THIS IS NOT AN ALL-CLEAR" in the
fallback case.

Nothing in a clean `git merge` could have found that. It is the argument for
reading a merge for meaning, not just for conflicts.

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
