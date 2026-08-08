"""Adaptive multistart stops only on strict numerical consensus."""

import pytest

from planeopt import solve


def _result(objective=100.0, span=1.8, chord=0.22):
    return {
        "objective_value": objective,
        "dv": {"span": span, "c_root": chord},
        "dv_bounds": {"span": [1.5, 2.0], "c_root": [0.15, 0.30]},
    }


def test_numerically_identical_starts_reach_strict_consensus():
    agreed, evidence = solve.multistart_consensus(
        _result(), _result(objective=100.0 + 1e-9, span=1.8 + 1e-7)
    )

    assert agreed
    assert evidence["reason"] == "strict consensus"
    assert evidence["worst_dv"] == "span"


@pytest.mark.parametrize(
    ("other", "reason"),
    [
        (_result(objective=100.01), "solutions differ"),
        (_result(span=1.8001), "solutions differ"),
        ({"failed": "Maximum_WallTime_Exceeded"}, "a probe start failed"),
    ],
)
def test_disagreement_or_failure_runs_the_remaining_starts(other, reason):
    agreed, evidence = solve.multistart_consensus(_result(), other)

    assert not agreed
    assert evidence["reason"] == reason


def test_missing_bounds_fail_closed():
    other = _result()
    del other["dv_bounds"]["span"]

    agreed, evidence = solve.multistart_consensus(_result(), other)

    assert not agreed
    assert "span" in evidence["reason"]


@pytest.mark.parametrize(
    ("second_objective", "expected_batches"),
    [
        (100.0, [["nominal", "perturbed_0"], ["mass_bump"]]),
            (
                101.0,
                [["nominal", "perturbed_0"], ["perturbed_1"], ["mass_bump"]],
            ),
    ],
)
def test_serial_scheduler_skips_only_after_consensus(
    sample_aircraft, sample_mission, tmp_path, monkeypatch,
    second_objective, expected_batches,
):
    batches = []

    def fake_solve_many(aircraft, mission, jobs, parallel, label=None, **kwargs):
        keys = [key for key, _ in jobs]
        if label != "multistart":
            raise solve.RunPaused("multistart scheduling was observed")
        batches.append(keys)
        out = {}
        for key in keys:
            objective = second_objective if key == "perturbed_0" else 100.0
            if key == "mass_bump":
                objective = 99.0
            out[key] = _result(objective=objective)
            out[key] |= {
                "V_ms": 9.5, "auw_kg": 1.8, "drag_n": 0.8,
                "static_margin": 0.08, "active_bounds": [],
            }
        return out

    monkeypatch.setattr(solve, "_solve_many", fake_solve_many)
    monkeypatch.setattr(sample_aircraft, "discrete_options", {}, raising=False)
    monkeypatch.setattr(sample_aircraft, "priced_options", {}, raising=False)
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)

    with pytest.raises(solve.RunPaused, match="scheduling was observed"):
        solve.optimize(
            sample_aircraft, sample_mission, runs_root=tmp_path,
            multistart=3, flatness=False, parallel=1,
        )

    assert batches == expected_batches
