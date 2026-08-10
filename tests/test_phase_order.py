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


#: Every OPTIONAL member measured converging on `vtail_rcv2`, in minutes, across
#: the two 2026-08 main-code batteries. These are the members the cap governs —
#: studies, the winglet pair, the priced equipment fit and the re-solve battery.
#: `winglet off` is the slowest that matters most: it is a paired study's
#: BASELINE, so losing it costs the comparison rather than one candidate.
RCV2_CONVERGED_OPTIONAL_MIN = {
    "winglet off": 12.38,
    "priced_equipment_fit__airframe_only": 12.97,
    "chain_eta_x0.90": 12.33,
    "chain_eta_x1.10": 12.40,
    "study_tail_type__ttail": 8.26,
    "study_fuselage_topology__integrated": 5.81,
}


def test_the_optional_cap_clears_every_optional_member_that_has_converged():
    """A cap below a member that converges does not save time, it loses answers.

    `OPTIONAL_MEMBER_TIMEOUT_MIN` was 12.0, justified in `solve.py` by "every
    optional member that did converge in that run landed inside 9.1 minutes" —
    a `vtail_sample` figure attached to a citation of an rcv2 run whose four
    slowest converged optional members take 12.28 to 12.97. The 2026-08-10
    battery then failed both of those it reached, including the winglet
    baseline, which took the whole winglet comparison with it (FINDINGS §35.3).

    The same substitution of `vtail_sample` timings for rcv2's had already been
    caught once in the flatness cap (§34.1). This pins it against the measured
    numbers so a third occurrence is a red test rather than a lost run.
    """
    slowest = max(RCV2_CONVERGED_OPTIONAL_MIN.values())
    assert solve.OPTIONAL_MEMBER_TIMEOUT_MIN > slowest, (
        f"the cap is at or below {slowest:.2f} min, which is a member that "
        "CONVERGES on rcv2 — it will be failed, not saved"
    )
    # And it must still do the job it exists for: no unselected alternative
    # gets the primary solve's full entitlement.
    assert solve.OPTIONAL_MEMBER_TIMEOUT_MIN < solve.SOLVE_TIMEOUT_MIN


def test_a_seeded_battery_member_that_fails_is_retried_cold():
    """FINDINGS §36.4: a champion seed can strand a member its cold solve reaches.

    `printed_mass_x0.90` is main's FASTEST member at 4.51 min and failed on this
    branch in both warm-start configurations. Paired arms settled it — cold 6.31
    min / 26 iterations converged, seeded 17.04 / 78 timed out, same closest
    miss the battery reported. So the battery must not treat a seeded failure as
    the member's answer.
    """
    seen = []

    def batch(label, jobs, prep=None, restore=None, timeout_min=None):
        seen.append((label, [(k, dict(kw)) for k, kw in jobs]))
        out = {}
        for key, kw in jobs:
            # fails while seeded, converges once the seed is gone
            if key == "printed_mass_x0.90" and "inits" in kw:
                out[key] = {"failed": "Maximum_WallTime_Exceeded",
                            "return_status": "Maximum_WallTime_Exceeded"}
            else:
                out[key] = {"objective_value": 100.0, "dv": {"span": 2.0}}
        return out

    jobs = [
        ("printed_mass_x1.10", {"inits": {"span": 2.0}, "printed_scale": 1.10}),
        ("printed_mass_x0.90", {"inits": {"span": 2.0}, "printed_scale": 0.90}),
    ]
    first = batch("re-solve battery", jobs)
    assert "failed" in first["printed_mass_x0.90"]

    recovered = solve._cold_retry(batch, jobs, first, timeout_min=16.0)

    assert set(recovered) == {"printed_mass_x0.90"}
    assert recovered["printed_mass_x0.90"]["objective_value"] == 100.0
    # the retry must drop the seed and keep the perturbation — retrying with
    # neither would measure a different member entirely
    retry_jobs = dict(seen[-1][1])
    assert "inits" not in retry_jobs["printed_mass_x0.90"]
    assert retry_jobs["printed_mass_x0.90"]["printed_scale"] == 0.90
    assert len(retry_jobs) == 1, "only the failed member is retried"


def test_a_member_that_fails_cold_too_keeps_its_seeded_diagnosis():
    """Two identical-looking failures are worse than one explained failure.

    The seeded result carries the convergence verdict (`dual_blow_up`,
    `starved_corner`, `still_converging`) that says what KIND of failure it was
    and therefore what to do about it. A cold retry that also fails must not
    overwrite that with a second bare timeout.
    """
    def batch(label, jobs, prep=None, restore=None, timeout_min=None):
        return {k: {"failed": "Maximum_WallTime_Exceeded"} for k, _ in jobs}

    jobs = [("chain_eta_x0.90", {"inits": {"span": 2.0}, "eta_scale": 0.90})]
    seeded = {"chain_eta_x0.90": {
        "failed": "Maximum_WallTime_Exceeded",
        "convergence": {"verdict": solve.VERDICT_STARVED_CORNER},
    }}

    assert solve._cold_retry(batch, jobs, seeded, timeout_min=16.0) == {}


def test_nothing_is_retried_when_every_member_converged():
    """The cost is paid only on failure; a clean battery must cost nothing."""
    calls = []

    def batch(label, jobs, prep=None, restore=None, timeout_min=None):
        calls.append(label)
        return {k: {"objective_value": 1.0} for k, _ in jobs}

    jobs = [("chain_eta_x1.10", {"inits": {}, "eta_scale": 1.10})]
    good = {"chain_eta_x1.10": {"objective_value": 1.0}}

    assert solve._cold_retry(batch, jobs, good, timeout_min=16.0) == {}
    assert calls == []
