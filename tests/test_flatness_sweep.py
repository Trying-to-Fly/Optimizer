"""The span flatness sweep, and when it is allowed to stop early.

The 2026-07-30 run spent roughly two of its hours re-deriving that its bottom
end contains no aircraft (FINDINGS §14.5.8). Skipping that is worth real time,
but only under an inference the sweep is actually entitled to make — which is
what these pin.
"""

from __future__ import annotations

import numpy as np
import pytest

from planeopt import solve


class _Recorder:
    """Stands in for the solver: records the spans asked for, and answers with
    whatever verdict the test wants."""

    def __init__(self, verdicts=None):
        self.asked: list[float] = []
        self.verdicts = verdicts or {}

    def __call__(self, aircraft, mission, **kw):
        span = kw["fixed"]["span"]
        self.asked.append(span)
        verdict = self.verdicts.get(round(span, 4))
        if verdict is not None:
            raise RuntimeError(verdict)
        return {"objective_value": 100.0 + span, "dv": {"span": span}}


def _run(monkeypatch, recorder, span_cap=2.0):
    """Drive optimize()'s sweep in isolation by replaying its own logic."""
    monkeypatch.setattr(solve, "_solve_nlp", recorder)

    def batch(label, jobs, **kw):
        return solve._solve_many(None, None, jobs, label=label)

    spans = sorted((float(s) for s in np.linspace(1.5, span_cap, 6)), reverse=True)
    fr, floor = {}, None
    for span in spans:
        if floor is not None:
            fr[span] = {"failed": "skipped", "return_status": "Skipped_Below_Infeasible_Span"}
            continue
        one = batch("flatness sweep", [(span, {"fixed": {"span": span}})])
        fr[span] = one[span]
        if fr[span].get("return_status") == "Infeasible_Problem_Detected":
            floor = span
    return fr


def test_the_sweep_runs_downward_from_the_cap(monkeypatch):
    """Direction is the whole basis for stopping early: shrinking span makes the
    constraints harder, so an infeasible member licenses an inference about
    SMALLER spans only. Sweeping upward would license nothing."""
    rec = _Recorder()
    _run(monkeypatch, rec)
    assert rec.asked == sorted(rec.asked, reverse=True)
    assert rec.asked[0] == pytest.approx(2.0)


def test_a_proof_of_infeasibility_short_circuits_smaller_spans(monkeypatch):
    rec = _Recorder({1.8: "Infeasible_Problem_Detected after 131 iterations"})
    monkeypatch.setattr(
        solve, "_failure_record",
        lambda e: {"failed": str(e), "return_status": "Infeasible_Problem_Detected"},
    )
    fr = _run(monkeypatch, rec)

    # 2.0, 1.9, 1.8 are solved; 1.7, 1.6, 1.5 are not attempted
    assert rec.asked == pytest.approx([2.0, 1.9, 1.8])
    for span in (1.7, 1.6, 1.5):
        assert fr[span]["return_status"] == "Skipped_Below_Infeasible_Span"
    # and the skip says why, rather than looking like a mysterious failure
    assert "skipped" in fr[1.5]["failed"]


def test_a_TIMEOUT_never_short_circuits(monkeypatch):
    """A timeout certifies nothing. Cascading one would silently discard spans
    that are merely slow — which is exactly the mistake this sweep is trying to
    stop making, in the other direction."""
    rec = _Recorder({1.8: "Maximum_WallTime_Exceeded after 199 iterations"})
    monkeypatch.setattr(
        solve, "_failure_record",
        lambda e: {"failed": str(e), "return_status": "Maximum_WallTime_Exceeded"},
    )
    rec_all = _run(monkeypatch, rec)
    assert rec.asked == pytest.approx([2.0, 1.9, 1.8, 1.7, 1.6, 1.5])
    assert all("Skipped" not in str(v.get("return_status")) for v in rec_all.values())


def test_an_all_feasible_sweep_is_unaffected(monkeypatch):
    rec = _Recorder()
    fr = _run(monkeypatch, rec)
    assert len(rec.asked) == 6
    assert all("failed" not in v for v in fr.values())
    # every span still reported, and the objective still tied to its own span
    assert fr[2.0]["objective_value"] == pytest.approx(102.0)
    assert fr[1.5]["objective_value"] == pytest.approx(101.5)
