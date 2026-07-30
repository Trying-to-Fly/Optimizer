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
