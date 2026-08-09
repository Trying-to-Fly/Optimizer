"""What a FAILED solve tells you.

A battery runs for hours and its members fail independently, so the artifact has
to explain each failure well enough to act on. Four sessions were spent chasing
"failed to converge" before the answer turned out to be that the corner simply
contained no flyable aircraft — see FINDINGS §14.5. These pin the machinery that
makes that answer visible without a bespoke script.

Deliberately built on toy Opti stacks: the properties under test are about the
solver seam, not about aerodynamics, and the suite has to stay seconds long.
"""

from __future__ import annotations

import aerosandbox as asb
import pytest

from planeopt import solve


def _infeasible():
    """x >= 3 and x <= 2, plus a slack constraint that is comfortably satisfied."""
    opti = asb.Opti()
    labels = solve._ConstraintLabels(opti)
    x = opti.variable(init_guess=1.0, lower_bound=-10, upper_bound=10)
    y = opti.variable(init_guess=0.0, lower_bound=-10, upper_bound=10)
    opti.subject_to(x >= 3.0)
    opti.subject_to(x <= 2.0)
    opti.subject_to(y <= 5.0)  # never the problem
    opti.minimize(x**2 + y**2)
    labels.stop()
    return opti, labels


def test_failure_carries_the_solver_status_not_a_truncated_assertion():
    """CasADi's message ends with `return_status is '...'`; a log line that cut
    it off is what made three runs of failures undiagnosable."""
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    failure = solve.SolveFailure(opti, caught.value, labels.as_dict())

    assert failure.return_status not in ("", "unknown")
    assert failure.return_status in str(failure)
    assert isinstance(failure.iter_count, int)


def test_failure_names_the_constraint_it_could_not_satisfy():
    """The point: a row index is useless, a source line is actionable."""
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    failure = solve.SolveFailure(opti, caught.value, labels.as_dict())

    assert failure.violations, "a failed solve should report what it missed"
    worst = failure.violations[0]
    assert worst["by"] > 0
    # points at this file and at one of the two constraints that conflict
    assert "test_solve_diagnostics.py" in worst["what"]
    assert ("x >= 3.0" in worst["what"]) or ("x <= 2.0" in worst["what"])
    # the comfortably-satisfied row must not be blamed
    assert all("y <= 5.0" not in v["what"] for v in failure.violations)

    record = solve._failure_record(failure)
    assert record["violations"][0]["what"] == worst["what"]
    assert record["return_status"] == failure.return_status


def test_violations_are_ordered_worst_first():
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    failure = solve.SolveFailure(opti, caught.value, labels.as_dict())
    by = [v["by"] for v in failure.violations]
    assert by == sorted(by, reverse=True)


def test_a_converged_solve_reports_no_violations():
    opti = asb.Opti()
    labels = solve._ConstraintLabels(opti)
    x = opti.variable(init_guess=0.0, lower_bound=-10, upper_bound=10)
    opti.subject_to(x >= 1.0)
    opti.minimize(x**2)
    labels.stop()
    opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    assert solve._worst_violations(opti, labels.as_dict()) == []


# ------------------------------------------------------- the labelling itself

def test_labels_cover_every_row_and_are_removed_afterwards():
    opti = asb.Opti()
    labels = solve._ConstraintLabels(opti)
    x = opti.variable(init_guess=1.0, lower_bound=0.0, upper_bound=5.0)
    opti.subject_to(x >= 2.0)
    mapping = labels.as_dict()
    # bounds are constraint rows too, and all of them are accounted for
    assert len(mapping) == opti.g.shape[0] > 0

    labels.stop()
    # the instance patch is gone, so nothing leaks into later solves
    assert "subject_to" not in opti.__dict__
    before = opti.g.shape[0]
    opti.subject_to(x <= 4.0)
    assert opti.g.shape[0] > before  # still a working Opti
    assert len(labels.as_dict()) == before  # but no longer recording


def test_labelling_is_per_instance_not_global():
    """A build that raises must not leave a patch behind poisoning later solves
    — which is why the wrapper binds to the instance, not the class."""
    a = asb.Opti()
    solve._ConstraintLabels(a)  # never stopped, as if the build had thrown
    b = asb.Opti()
    y = b.variable(init_guess=0.0, lower_bound=-1, upper_bound=1)
    b.subject_to(y >= 0.0)
    assert "subject_to" not in b.__dict__


def test_every_failure_field_survives_the_summarisers():
    """The battery, each discrete study, the flatness sweep and the winglet pair
    all project a failed result down through `_failed_entry`. A field missing
    from `_FAILURE_FIELDS` is written by the solver and then silently dropped
    before it reaches run.json — which is how `return_status` was lost for three
    runs, and how `violations` was nearly lost the day it was added."""
    record = {
        "failed": "Infeasible_Problem_Detected after 131 iterations",
        "return_status": "Infeasible_Problem_Detected",
        "iter_count": 131,
        "violations": [{"row": 76, "by": 8.3e-3, "value": 0.0717, "what": "sm floor"}],
        "detail": "…",
        "solve_minutes": 17.9,
        "peak_rss_gb": 12.6,
    }
    kept = solve._failed_entry(record)
    for key in ("failed", "return_status", "iter_count", "violations", "solve_minutes"):
        assert key in kept, f"{key} is dropped before it reaches run.json"
    assert kept["violations"][0]["what"] == "sm floor"
    # and nothing unrelated rides along
    assert "peak_rss_gb" not in kept


def test_diagnostics_never_replace_the_real_failure():
    """Best-effort by contract: a broken Opti must yield [] rather than raise,
    because a crash here would hide the solver error it was meant to explain."""
    class Hostile:
        @property
        def x(self):
            raise ValueError("no")

    assert solve._worst_violations(Hostile(), {}) == []


# ------------------------------------------------- which bounds a solution sits on
# HANDOFF issue 0b: the 2026-07-31 champion was pinned against EIGHT declared
# bounds and only three of them were ever discussed, because nothing reported
# them — the box lives in the aircraft's `design_variables` and the framework
# never saw it. These pin the recorder that now does.


def _boxed(**kwargs):
    """A toy Opti whose optimum sits on x's upper bound and y's lower bound."""
    opti = asb.Opti()
    declared = solve._DeclaredBounds(opti)
    dv = {
        "x": opti.variable(init_guess=1.0, lower_bound=0.0, upper_bound=2.0),
        "y": opti.variable(init_guess=1.0, lower_bound=0.5, upper_bound=4.0),
        "z": opti.variable(init_guess=1.0, lower_bound=-5.0, upper_bound=5.0),
    }
    declared.stop()
    for key, value in kwargs.items():
        opti.subject_to(dv[key] == value)
    # pushes x up, y down, and leaves z interior
    opti.minimize(-dv["x"] + dv["y"] + (dv["z"] - 1.0) ** 2)
    return opti, dv, declared


def test_active_bounds_are_named():
    opti, dv, declared = _boxed()
    sol = opti.solve(verbose=False, max_iter=200, detect_simple_bounds=True)
    active = declared.active(dv, sol)

    assert [(b["variable"], b["at"]) for b in active] == [("x", "upper"), ("y", "lower")]
    assert active[0]["bound"] == 2.0 and active[0]["box"] == [0.0, 2.0]
    # z is interior and must not be reported — a list that names everything is
    # the same as a list that names nothing
    assert "z" not in [b["variable"] for b in active]


def test_a_bound_is_active_when_ipopt_lands_just_past_it():
    """IPOPT converges ONTO a bound, not to it: the champion's span is
    2.0000000199 against a 2.0 m cap. An exact comparison reports nothing."""
    opti, dv, declared = _boxed()
    opti.solve(verbose=False, max_iter=200, detect_simple_bounds=True)

    class _JustPast:
        def __call__(self, var):
            return {id(dv["x"]): 2.0 + 2e-8, id(dv["y"]): 0.5 - 1e-9,
                    id(dv["z"]): 1.0}[id(var)]

    assert {b["variable"] for b in declared.active(dv, _JustPast())} == {"x", "y"}


def test_the_recorder_is_removed_and_is_per_instance():
    """Same discipline as the constraint labeller: no global patch may survive.

    A leaked patch would make every later solve in the process record bounds
    against the wrong Opti — and a battery runs dozens of solves in one process.
    """
    opti = asb.Opti()
    declared = solve._DeclaredBounds(opti)
    other = asb.Opti()
    assert "variable" not in other.__dict__, "patch leaked to another Opti"
    declared.stop()
    assert "variable" not in opti.__dict__
    declared.stop()  # idempotent


def test_fixing_a_variable_adds_no_constraint_row():
    """`fixed` values are handed to IPOPT as BOUNDS, not as an extra equality.

    HANDOFF issue 1 called for plumbing `fixed` into `design_variables` because
    `subject_to(dv[k] == v)` on a variable ALREADY at that bound declares the
    same constraint twice — LICQ violated by construction, multipliers
    non-unique. `detect_simple_bounds=True` (added the session before) already
    does it: CasADi hoists `x == v` into lbx/ubx and eliminates the variable.
    Measured on the real model the same day: fixing span at its own lower bound
    took it from 36 variables / 4 equalities / 34 inequalities to 35 / 4 / 34.

    This test is what stops that from silently regressing if the flag is ever
    dropped — the symptom would be a diverging `inf_du` in the flatness sweep,
    which costs a session to diagnose.
    """
    free, _, _ = _boxed()
    free.solve(verbose=False, max_iter=200, detect_simple_bounds=True)
    baseline = list(free.stats()["detect_simple_bounds_is_simple"])
    assert all(baseline), "the declared box itself should already be bounds"

    for value, where in ((1.0, "interior"), (0.0, "on its own lower bound")):
        opti, dv, _ = _boxed(x=value)
        sol = opti.solve(verbose=False, max_iter=200, detect_simple_bounds=True)
        is_simple = list(opti.stats()["detect_simple_bounds_is_simple"])
        # CasADi flags every row it hoisted out of `g` into lbx/ubx. The row the
        # `fixed` value added must be among them: one more row than the free
        # problem, and all of them simple.
        assert len(is_simple) == len(baseline) + 1, where
        assert all(is_simple), f"{where}: `fixed` survived as a constraint row"
        assert float(sol(dv["x"])) == pytest.approx(value), where


def test_the_declared_box_is_recorded_next_to_the_values():
    """A bound is only readable next to the value it bounds — and the flatness
    sweep needs to ask what the span box IS, because a `fixed` value outside it
    is an invalid problem rather than an infeasible aircraft."""
    opti, dv, declared = _boxed()
    boxes = declared.boxes(dv)
    assert boxes == {"x": [0.0, 2.0], "y": [0.5, 4.0], "z": [-5.0, 5.0]}
    # every declared variable appears, whether or not its bound is active
    assert set(boxes) == set(dv)


# --------------------------------------------------------------------------
# the dual side of a failure — which KIND of failure it was
# --------------------------------------------------------------------------


def _stats(pr, du, mu=None):
    return {"iterations": {"inf_pr": pr, "inf_du": du, "mu": mu or [0.1] * len(pr)}}


def test_convergence_trace_reads_a_dual_blow_up_as_degeneracy():
    """`inf_du` diverging while the primal side is driven small is the
    signature `tools/degeneracy.py` exists for — no multipliers to converge to,
    so more clock cannot help."""
    tr = solve._convergence_trace(_stats([5.0] + [1e-9] * 40, [1.0] + [1e6] * 40))
    assert tr["inf_pr_final"] == pytest.approx(1e-9)
    assert tr["inf_du_final"] == pytest.approx(1e6)
    assert "Stuck, not slow" in tr["reading"]


def test_convergence_trace_reads_a_flat_primal_side_as_a_starved_corner():
    """No dual blow-up, but no progress either: the shape of an infeasible
    corner rather than a solver defect."""
    tr = solve._convergence_trace(_stats([5.0] * 40, [3.0] * 40))
    assert "starved corner" in tr["reading"]
    assert tr["inf_pr_min"] == pytest.approx(5.0)


def test_convergence_trace_says_when_more_clock_would_actually_pay():
    """Still descending when the clock stopped — the only case where raising
    the timeout is the right response."""
    tr = solve._convergence_trace(
        _stats([5.0 - 0.1 * i for i in range(40)], [3.0] * 40)
    )
    assert "may actually pay" in tr["reading"]


def test_convergence_trace_measures_the_plateau():
    """How much the last 25 iterations actually bought. ~0 is why more clock is
    not the fix (FINDINGS 14.5.7)."""
    flat = solve._convergence_trace(_stats([0.3] * 40, [0.3] * 40))
    assert flat["inf_pr_progress_last_25"] == pytest.approx(0.0)
    moving = solve._convergence_trace(
        _stats([1.0] * 15 + [1.0 - 0.02 * i for i in range(26)], [1.0] * 41)
    )
    assert moving["inf_pr_progress_last_25"] > 0.4


def test_convergence_trace_is_best_effort():
    """A diagnostic must never turn a failed solve into a crashed one."""
    assert solve._convergence_trace({}) == {}
    assert solve._convergence_trace({"iterations": {}}) == {}
    assert solve._convergence_trace({"iterations": {"inf_pr": ["not a number"]}}) == {}


def test_a_real_failure_carries_its_convergence_trace():
    """End to end: the trace reaches the record and survives the summarisers."""
    opti, labels = _infeasible()
    try:
        opti.solve(verbose=False, max_iter=12)
        pytest.fail("expected the solve to fail")
    except RuntimeError as e:
        exc = solve.SolveFailure(opti, e, labels.as_dict())
    rec = solve._failure_record(exc)
    assert "convergence" in rec, rec
    assert rec["convergence"]["iterations_recorded"] > 0
    assert "reading" in rec["convergence"]
    assert "convergence" in solve._failed_entry(rec)


# --------------------------------------------------------------------------
# which operating point each static margin was read at
# --------------------------------------------------------------------------

SM_RANGE = (0.08, 0.15)


def test_sm_read_at_is_silent_when_both_read_the_same_speed():
    """Eleven runs' worth of normal: the NLP optimum sits on v_min and so does
    the sweep's peak, so there is nothing to disclose."""
    champ = {"V_ms": 9.5, "static_margin": 0.08}
    best = {"V_ms": 9.5}
    assert solve.sm_read_at(champ, best, {"sm_in_range": True}, SM_RANGE) == (None, None)


def test_sm_read_at_names_both_speeds_when_they_differ():
    champ = {"V_ms": 9.709, "static_margin": 0.08}
    read_at, _ = solve.sm_read_at(champ, {"V_ms": 9.5}, {"sm_in_range": True}, SM_RANGE)
    assert read_at["nlp_V_ms"] == 9.709
    assert read_at["reeval_V_ms"] == 9.5
    assert "static-margin window" in read_at["why"]


def test_sm_read_at_rejects_an_impossible_legal_but_unstable_headline():
    """After stability joined the filter, `legal` beside a failed margin is an
    internal inconsistency rather than a different legitimate operating point."""
    champ = {"V_ms": 9.709, "static_margin": 0.07999999}
    _, note = solve.sm_read_at(champ, {"V_ms": 9.5}, {"sm_in_range": False}, SM_RANGE)
    assert note is not None
    assert "9.500 m/s" in note and "9.709 m/s" in note
    assert "internal selection inconsistency" in note
    assert "final trust gate must reject it" in note


def test_sm_read_at_treats_a_bound_hit_to_solver_tolerance_as_in_range():
    """The champion lands ON the floor, a hair under it: SM 0.07999999 against
    0.08. That is a converged bound, not a design that misses its window."""
    champ = {"V_ms": 9.709, "static_margin": 0.07999999000380999}
    _, note = solve.sm_read_at(champ, {"V_ms": 9.5}, {"sm_in_range": False}, SM_RANGE)
    assert note is not None


def test_sm_read_at_stays_quiet_when_the_design_itself_misses_the_window():
    """If the NLP's own static margin is out of range too, the aeroplane really
    does miss its window and there is nothing to explain away."""
    champ = {"V_ms": 9.709, "static_margin": 0.061}
    _, note = solve.sm_read_at(champ, {"V_ms": 9.5}, {"sm_in_range": False}, SM_RANGE)
    assert note is None


# --- where this feature meets the no-legal-point fallback -------------------
#
# `sm_read_at`'s premise is "the sweep picks the best AIRWORTHY point". That is
# false when NOTHING in the sweep was airworthy and `run` fell back to the best
# FEASIBLE one (FINDINGS §28). The two were written in separate sessions and
# merged on 2026-08-06; separately each is correct, and together they put a
# reassuring "the design meets its window at the speed it was solved for" one
# line away from a champion trimming at 4.2x its control limit.


def test_the_premise_is_restated_when_no_point_was_airworthy():
    """The `why` text is the reader's explanation of what the two speeds MEAN,
    and 'the best airworthy point' is exactly wrong in the fallback."""
    champ = {"V_ms": 9.8, "static_margin": 0.10}

    read_at, _ = solve.sm_read_at(
        champ, {"V_ms": 12.5}, {"sm_in_range": True}, SM_RANGE,
        candidates_source="feasible_fallback",
    )

    assert read_at["candidates_source"] == "feasible_fallback"
    assert "NO point in the sweep was airworthy" in read_at["why"]
    assert "best AIRWORTHY point" not in read_at["why"]


def test_the_reassuring_note_refuses_to_read_as_an_all_clear():
    """It stays — the NLP design really does meet its window at its own speed —
    but it may not be the last word on a run with no legal operating point."""
    champ = {"V_ms": 9.8, "static_margin": 0.10}

    _, note = solve.sm_read_at(
        champ, {"V_ms": 12.5}, {"sm_in_range": False}, SM_RANGE,
        candidates_source="feasible_fallback",
    )

    assert "NLP met the window" in note
    assert "not an all-clear" in note
    assert "ILLEGAL" in note


def test_a_normal_run_is_unchanged_by_any_of_this():
    """The fallback is rare; the ordinary case must read exactly as before."""
    champ = {"V_ms": 9.709, "static_margin": 0.07999999}

    read_at, note = solve.sm_read_at(
        champ, {"V_ms": 9.5}, {"sm_in_range": False}, SM_RANGE
    )

    assert read_at["candidates_source"] == "legal"
    assert "best AIRWORTHY point" in read_at["why"]
    assert "ALL-CLEAR" not in note


# --- a wall clock charges a member for time the process was ASLEEP ----------
#
# `ipopt.max_wall_time` is the right guard (it is protecting the run's wall
# clock against a solve that starts swapping), but it cannot tell "this solve
# ran for 30 minutes" from "this laptop was shut for 25 of them". On 2026-08-07
# four cells of docs/studies/RCV2_CAP_PRICING.md died that way and three of them
# converge in 2-9 minutes when re-measured awake; the fourth is a real corner.
# Same `Maximum_WallTime_Exceeded`, opposite meaning, and nothing in the
# artifact separated them.


def test_suspended_minutes_is_the_gap_between_the_two_clocks():
    """`time.time()` runs through sleep; `time.monotonic()` does not.

    So the difference IS the suspension, on both macOS (mach_absolute_time)
    and Linux (CLOCK_MONOTONIC), with no platform branch and no pmset.
    """
    assert solve.suspended_minutes(600.0, 600.0) == 0.0
    assert solve.suspended_minutes(1800.0, 300.0) == pytest.approx(25.0)
    # never negative: the two clocks drift, and a member that reports having
    # been asleep for -0.3 minutes destroys trust in the number that matters
    assert solve.suspended_minutes(100.0, 100.5) == 0.0


def test_a_wall_time_failure_that_slept_says_so():
    """The message is the log line and the first thing a reader sees."""
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)

    slept = solve.SolveFailure(
        opti, caught.value, labels.as_dict(), suspended_min=14.2
    )
    assert slept.suspended_minutes == 14.2
    assert "SUSPENDED" in str(slept)
    assert "14.2" in str(slept)

    # below the floor it is recorded but not narrated — an NTP step of a few
    # seconds must not print as "the machine slept"
    brief = solve.SolveFailure(
        opti, caught.value, labels.as_dict(), suspended_min=0.05
    )
    assert brief.suspended_minutes == 0.05
    assert "SUSPENDED" not in str(brief)


def test_the_three_positional_form_still_builds():
    """Four call sites in this file pass three positional args; a signature
    change that broke them would be a fix that costs the diagnostics it joins."""
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    failure = solve.SolveFailure(opti, caught.value, labels.as_dict())
    assert failure.suspended_minutes == 0.0


def test_suspension_survives_the_summariser():
    """A field the battery entry drops is worth nothing — which is the exact
    defect `_FAILURE_FIELDS` was created to fix."""
    opti, labels = _infeasible()
    with pytest.raises(RuntimeError) as caught:
        opti.solve(verbose=False, max_iter=50, detect_simple_bounds=True)
    failure = solve.SolveFailure(
        opti, caught.value, labels.as_dict(), suspended_min=9.5
    )
    record = solve._failure_record(failure)
    assert record["suspended_minutes"] == 9.5
    assert solve._failed_entry(record)["suspended_minutes"] == 9.5
