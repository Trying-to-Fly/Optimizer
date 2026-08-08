"""The characterization phases must describe the aeroplane being SHIPPED.

The flatness sweep, the re-solve battery and the shadow price all answer "how
sensitive is this design to X". Until 2026-08-05 they ran immediately after the
multistart — before the discrete studies and the winglet study had finished
choosing the design. So the 2026-08-05 artifact's flatness curve and its whole
sensitivity battery described a 119.93-minute aircraft on the incumbent 11x6
prop carrying a winglet, while the champion it reported was a 142.09-minute
aircraft on a 12x10 with no winglet. Every member converged; nothing said they
were different aeroplanes.

The fix is an ordering property, so this pins the ORDER, using a fake NLP: what
is under test is the orchestration, not the aerodynamics.
"""

from __future__ import annotations

import pytest

from planeopt import solve

#: The phases whose results are only meaningful once the design is final.
CHARACTERIZATION = ("flatness sweep", "re-solve battery")


@pytest.fixture()
def phase_log(monkeypatch):
    """Record the order phases are dispatched in, and abort before the re-eval.

    `RunPaused` is the codebase's own clean-abort signal and is not caught by
    `optimize`, so it stops the run without pretending a solve failed.
    """
    labels: list[str] = []
    objective = {"n": 0.0}

    def fake_solve_many(aircraft, mission, jobs, parallel, label=None, **kw):
        labels.append(label)
        results = {}
        for key, _ in jobs:
            objective["n"] += 1.0
            results[key] = {
                # Rising, so every study "adopts" its candidate and the champion
                # keeps moving — the case where a stale characterization is
                # most obviously wrong.
                "objective_value": 100.0 + objective["n"],
                "V_ms": 9.5,
                "auw_kg": 1.8,
                "drag_n": 0.83,
                "static_margin": 0.08,
                "dv": {"span": 2.0, "ballast_kg": 0.0, "dihedral_tip": 5.0, "d_exp": 0.0},
                "dv_bounds": {"span": [1.5, 2.0]},
                "active_bounds": [],
            }
        if label == CHARACTERIZATION[-1]:
            raise solve.RunPaused("stop before the numeric re-evaluation")
        return results

    monkeypatch.setattr(solve, "_solve_many", fake_solve_many)
    return labels


def _run(aircraft, mission, tmp_path, phase_log):
    with pytest.raises(solve.RunPaused):
        solve.optimize(aircraft, mission, runs_root=tmp_path, multistart=2)
    return phase_log


def test_characterization_runs_after_every_discrete_study(
    sample_aircraft, sample_mission, tmp_path, phase_log, monkeypatch
):
    """The regression itself: no sensitivity phase may precede a study that can
    still change the design."""
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)

    order = _run(sample_aircraft, sample_mission, tmp_path, phase_log)

    studies = [i for i, lb in enumerate(order) if lb.startswith("study ")]
    assert studies, "the sample aircraft is supposed to declare discrete studies"
    for phase in CHARACTERIZATION:
        assert phase in order, f"{phase} did not run at all"
        assert order.index(phase) > max(studies), (
            f"{phase} ran at position {order.index(phase)}, before the last study "
            f"at {max(studies)} — it is describing a superseded design"
        )


def test_characterization_runs_after_the_winglet_study(
    sample_aircraft, sample_mission, tmp_path, phase_log, monkeypatch
):
    """The winglet study can replace the champion outright, so it is the last
    thing that can change what is being characterized."""
    monkeypatch.setattr(solve.aero, "vlm_induced_check", lambda *a, **k: {"stub": True})

    order = _run(sample_aircraft, sample_mission, tmp_path, phase_log)

    assert "winglet study" in order
    for phase in CHARACTERIZATION:
        assert order.index(phase) > order.index("winglet study")


def test_the_multistart_still_leads(
    sample_aircraft, sample_mission, tmp_path, phase_log, monkeypatch
):
    """Nothing can be studied before there is a champion to study against."""
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)

    order = _run(sample_aircraft, sample_mission, tmp_path, phase_log)

    assert order[0] == "multistart"


def test_the_shadow_price_is_re_measured_on_the_final_design(
    sample_aircraft, sample_mission, tmp_path, phase_log, monkeypatch
):
    """It is reported as this design's trade rate, so it cannot be the multistart
    champion's. The +20 g bump rides the re-solve battery for that reason."""
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    seen: list[tuple] = []

    real = solve._solve_many

    def spy(aircraft, mission, jobs, parallel, label=None, **kw):
        seen.append((label, [k for k, _ in jobs]))
        return real(aircraft, mission, jobs, parallel, label=label, **kw)

    monkeypatch.setattr(solve, "_solve_many", spy)

    _run(sample_aircraft, sample_mission, tmp_path, phase_log)

    battery = [keys for label, keys in seen if label == "re-solve battery"]
    assert battery, "the re-solve battery did not run"
    assert "mass_bump" in battery[0], (
        "the shadow price is still the multistart champion's — the +20 g bump "
        "must be re-solved against the final design"
    )


def test_optional_members_are_seeded_and_use_phase_specific_budgets(
    sample_aircraft, sample_mission, tmp_path, phase_log, monkeypatch
):
    """A sensitivity member is not another cold, 30-minute primary solve."""
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    dispatched: list[tuple[str, list[tuple], dict]] = []
    fake = solve._solve_many

    def spy(aircraft, mission, jobs, parallel, label=None, **kw):
        dispatched.append((label, jobs, kw))
        return fake(aircraft, mission, jobs, parallel, label=label, **kw)

    monkeypatch.setattr(solve, "_solve_many", spy)
    _run(sample_aircraft, sample_mission, tmp_path, phase_log)

    optional = [
        call for call in dispatched
        if call[0].startswith("study ") or call[0] == "re-solve battery"
    ]
    assert optional
    assert all(
        call_kw["timeout_min"] == solve.OPTIONAL_MEMBER_TIMEOUT_MIN
        for _, _, call_kw in optional
    )
    assert all(
        job_kw.get("inits", {}).get("span") == pytest.approx(2.0)
        for _, jobs, _ in optional for _, job_kw in jobs
    )

    flatness = [jobs for label, jobs, _ in dispatched if label == "flatness sweep"]
    assert flatness
    assert all(
        job_kw["timeout_min"] == solve.FLATNESS_TIMEOUT_MIN
        for jobs in flatness for _, job_kw in jobs
    )

    bump = [
        job_kw for label, jobs, _ in dispatched if label == "multistart"
        for key, job_kw in jobs if key == "mass_bump"
    ]
    assert bump
    assert bump[-1]["timeout_min"] == solve.OPTIONAL_MEMBER_TIMEOUT_MIN
    assert bump[-1]["inits"]["span"] == pytest.approx(2.0)
