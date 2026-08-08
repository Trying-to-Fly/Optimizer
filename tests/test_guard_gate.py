"""Guards that run DURING selection, not after it.

Every expensive failure this project has had was a selection-time one found
late. On 2026-08-01 a solve reported an L/D of 889 because at four panels per
section a high-cant winglet contributed about -0.93 N (FINDINGS §18); the
winglet cross-check was separately measuring its own mesh; the in-loop model
made thrust and a solve went looking for it. In each case the model was
untrustworthy WHILE the studies were choosing the design, and every phase after
that point spent its time characterizing the artefact.

`test_phase_order.py` fixed the other half of this — characterization must
describe the design being SHIPPED. This file pins the complementary property:
the design being characterized must be one whose objective is the aeroplane's
rather than the panel count's, and a candidate must not be ADOPTED on a number
the mesh invented.

Two properties, in cost order:

  - a candidate whose drag is mesh-dependent is not adopted (sub-second, and it
    prevents the artefact entering the design at all);
  - a champion whose drag is mesh-dependent does not get characterized (also
    sub-second, and it protects the flatness sweep plus four full
    re-optimizations — the most expensive phase after the multistart).
"""

from __future__ import annotations

import pytest

from planeopt import solve

CHARACTERIZATION_END = "re-solve battery"


def _mesh(converged: bool, in_loop=0.70, fine=0.72):
    return {
        "in_loop": {"spanwise_resolution": 4, "D_n": in_loop, "L_n": 19.0, "CL": 0.7},
        "fine": {"spanwise_resolution": 16, "D_n": fine, "L_n": 19.0, "CL": 0.7},
        "delta_frac": (in_loop - fine) / fine,
        "converged": converged,
    }


# --------------------------------------------------- the predicate on its own


def test_an_unanswerable_question_does_not_reject(monkeypatch):
    """Fail OPEN, deliberately.

    A failed member carries no operating point, and a guard that treated
    "I cannot tell" as "untrustworthy" would silently delete candidates for
    having crashed rather than for being wrong.
    """
    called = []
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: called.append(1) or _mesh(False))

    ok, check = solve.objective_is_mesh_trustworthy(object(), {"failed": "boom"})
    assert ok is True
    assert check is None
    assert not called, "it must not even try without an operating point"


def test_a_raising_check_does_not_reject(monkeypatch):
    """Same posture one level down: a guard is not allowed to cost the run."""
    def boom(*a, **k):
        raise RuntimeError("mesh exploded")

    monkeypatch.setattr(solve.aero, "mesh_convergence_check", boom)

    class _AC:
        def geometry(self, dv):
            return object()

    ok, check = solve.objective_is_mesh_trustworthy(_AC(), _FULL_RESULT)
    assert ok is True
    assert check is None


def test_a_mesh_dependent_objective_is_rejected(monkeypatch):
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: _mesh(False, in_loop=-0.033, fine=0.923))

    class _AC:
        def geometry(self, dv):
            return object()

    ok, check = solve.objective_is_mesh_trustworthy(_AC(), _FULL_RESULT)
    assert ok is False
    assert check["in_loop"]["D_n"] < 0 < check["fine"]["D_n"]


@pytest.mark.parametrize(
    ("mesh_ok", "constraints", "reeval_error", "expected_reason"),
    [
        (False, {"stall_ok": True, "sm_in_range": True, "sm_sign_consistent": True}, None,
         "mesh-dependent"),
        (True, {"stall_ok": True, "sm_in_range": False, "sm_sign_consistent": True}, None,
         "misses the static-margin window"),
        (True, {"stall_ok": True, "sm_in_range": True, "sm_sign_consistent": False}, None,
         "changes sign"),
        (True, {}, "trim failed", "re-evaluation failed"),
    ],
)
def test_final_design_trust_fails_closed_on_each_required_check(
    mesh_ok, constraints, reeval_error, expected_reason
):
    trusted, failures = solve.final_design_trust(
        mesh_ok, constraints, reeval_error,
    )
    assert trusted is False
    assert any(expected_reason in reason for reason in failures)


def test_final_design_trust_requires_both_stability_checks_to_pass():
    assert solve.final_design_trust(
        True, {"stall_ok": True, "sm_in_range": True, "sm_sign_consistent": True},
        None,
    ) == (True, [])


def test_final_design_trust_rejects_a_feasible_fallback():
    trusted, failures = solve.final_design_trust(
        True, {"stall_ok": True, "sm_in_range": True, "sm_sign_consistent": True},
        None, candidates_source="feasible_fallback",
    )
    assert trusted is False
    assert any("no airworthy operating point" in reason for reason in failures)


_FULL_RESULT = {
    "V_ms": 9.5, "alpha_deg": 5.0, "deflection_deg": -2.0, "x_cg_m": 0.4,
    "dv": {"span": 2.0},
}


# ------------------------------------------------- the two ordering behaviours


@pytest.fixture()
def harness(monkeypatch):
    """A fake NLP whose members carry a full operating point.

    `test_phase_order.py`'s fixture omits alpha/deflection/x_cg, so the guard
    there correctly declines to answer and nothing is exercised. These members
    are complete, which is what turns the guard on.
    """
    labels: list[str] = []
    jobs_seen: list[tuple[str, list[str]]] = []
    n = {"i": 0.0}

    def fake_solve_many(aircraft, mission, jobs, parallel, label=None, **kw):
        labels.append(label)
        jobs_seen.append((label, [k for k, _ in jobs]))
        results = {}
        for key, _ in jobs:
            n["i"] += 1.0
            results[key] = {
                # rising, so every discrete candidate beats the incumbent and
                # the adoption path is always taken
                "objective_value": 100.0 + n["i"],
                "V_ms": 9.5, "alpha_deg": 5.0, "deflection_deg": -2.0,
                "x_cg_m": 0.4, "auw_kg": 1.8, "drag_n": 0.83,
                "static_margin": 0.08,
                "dv": {"span": 2.0, "ballast_kg": 0.0, "dihedral_tip": 5.0,
                       "d_exp": 0.0},
                "dv_bounds": {"span": [1.5, 2.0]},
                "active_bounds": [],
            }
        if label == CHARACTERIZATION_END:
            raise solve.RunPaused("stop before the numeric re-evaluation")
        return results

    monkeypatch.setattr(solve, "_solve_many", fake_solve_many)
    monkeypatch.setattr(solve.aero, "vlm_induced_check", lambda *a, **k: {"stub": True})
    return labels, jobs_seen


def _run(aircraft, mission, tmp_path):
    with pytest.raises(solve.RunPaused):
        solve.optimize(aircraft, mission, runs_root=tmp_path, multistart=2)


def test_a_winning_candidate_with_mesh_dependent_drag_is_not_adopted(
    sample_aircraft, sample_mission, tmp_path, harness, monkeypatch
):
    """The root-cause half: keep the artefact out of the design entirely.

    Every candidate "wins" here by construction, so with the guard rejecting
    them all, the aircraft must come out of the studies still on its baseline
    attributes — the incumbent stands.
    """
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: _mesh(False, in_loop=-0.033, fine=0.923))

    options = dict(getattr(sample_aircraft, "discrete_options", None) or {})
    assert options, "the sample aircraft is supposed to declare discrete studies"
    baseline = {attr: getattr(sample_aircraft, attr) for attr in options}

    _run(sample_aircraft, sample_mission, tmp_path)

    for attr, was in baseline.items():
        assert getattr(sample_aircraft, attr) == was, (
            f"{attr} was adopted on a mesh-dependent objective"
        )


def test_a_trustworthy_candidate_is_still_adopted(
    sample_aircraft, sample_mission, tmp_path, harness, monkeypatch
):
    """The guard must not be a blanket refusal — the control case."""
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: _mesh(True))

    options = dict(getattr(sample_aircraft, "discrete_options", None) or {})
    baseline = {attr: getattr(sample_aircraft, attr) for attr in options}

    _run(sample_aircraft, sample_mission, tmp_path)

    assert any(getattr(sample_aircraft, a) != was for a, was in baseline.items()), (
        "with a clean mesh every candidate wins, so something must have been adopted"
    )


def test_an_untrustworthy_champion_skips_the_sensitivity_phases(
    sample_aircraft, sample_mission, tmp_path, harness, monkeypatch
):
    """The cost half: do not spend hours characterizing an artefact.

    The flatness sweep must not run at all, and the re-solve battery must be
    reduced to `mass_bump` alone — which is NOT a sensitivity member but the
    only source of the shadow price the rest of the run quotes.
    """
    labels, jobs_seen = harness
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: _mesh(False, in_loop=-0.033, fine=0.923))

    _run(sample_aircraft, sample_mission, tmp_path)

    assert "flatness sweep" not in labels, "the flatness sweep characterized an artefact"
    battery = [keys for label, keys in jobs_seen if label == CHARACTERIZATION_END]
    assert battery, "the battery phase must still be reached"
    assert battery[-1] == ["mass_bump"], (
        f"the perturbation members should have been dropped, got {battery[-1]}"
    )


def test_a_trustworthy_champion_characterizes_normally(
    sample_aircraft, sample_mission, tmp_path, harness, monkeypatch
):
    """The control case for the gate: nothing is skipped when nothing is wrong.

    Pins that the gate is a conditional and not a quiet permanent reduction of
    what a run does.
    """
    labels, jobs_seen = harness
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    monkeypatch.setattr(solve.aero, "mesh_convergence_check",
                        lambda *a, **k: _mesh(True))

    _run(sample_aircraft, sample_mission, tmp_path)

    assert "flatness sweep" in labels
    battery = [keys for label, keys in jobs_seen if label == CHARACTERIZATION_END][-1]
    assert "mass_bump" in battery
    assert len(battery) > 1, "the perturbation members should have run"


def test_the_gate_runs_before_the_phases_it_protects(
    sample_aircraft, sample_mission, tmp_path, harness, monkeypatch
):
    """Ordering, stated directly: the check is worthless after the spend.

    Recorded as its own property because the failure mode is silent — a gate
    that runs late still reports the right verdict and still costs the hours it
    existed to save.
    """
    labels, _ = harness
    monkeypatch.setattr(sample_aircraft, "winglet", False, raising=False)
    seen_at: list[int] = []

    def spy(*a, **k):
        seen_at.append(len(labels))
        return _mesh(True)

    monkeypatch.setattr(solve.aero, "mesh_convergence_check", spy)

    _run(sample_aircraft, sample_mission, tmp_path)

    assert "flatness sweep" in labels
    # the gate's call on the final champion happens once the studies are done
    # and before any characterization phase is dispatched
    assert min(seen_at) <= labels.index("flatness sweep")
