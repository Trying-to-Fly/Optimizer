"""The objective registry, and the NLP-surrogate contract.

A surrogate is a claim — "minimizing this picks the same design as maximizing
the real objective" — and a wrong one would silently optimize for the wrong
thing while every report still looked plausible. So the claim is tested, not
trusted: same ranking over the operating range, and well-behaved exactly where
the evaluator is not.
"""

from __future__ import annotations

import numpy as np
import pytest

from planeopt.mission import OBJECTIVES


def _powertrain(sample_aircraft):
    return sample_aircraft.powertrain()


# ------------------------------------------------------------------ registry

def test_every_objective_can_form_an_nlp_expression(sample_aircraft, sample_mission):
    """`nlp_expression` is the single seam solve._solve_nlp uses. An objective
    with an evaluator must be able to produce one, surrogate or not."""
    pt = _powertrain(sample_aircraft)
    for obj in OBJECTIVES.values():
        if obj.evaluator is None:
            continue  # declared but not implemented yet (cruise_speed)
        value = obj.nlp_expression(11.0, 25.0, sample_mission, pt)
        assert np.isfinite(value), obj.name


def test_an_objective_without_a_surrogate_still_flips_sign_to_minimize(
    sample_aircraft, sample_mission
):
    """The fallback path must be unchanged: maximize -> minimize the negative."""
    pt = _powertrain(sample_aircraft)
    speed = OBJECTIVES["max_speed"]
    assert speed.nlp_surrogate is None and speed.direction == "maximize"
    assert speed.nlp_expression(17.0, 90.0, sample_mission, pt) == pytest.approx(-17.0)

    per_km = OBJECTIVES["energy_per_km"]
    assert per_km.direction == "minimize"
    assert per_km.nlp_expression(11.0, 25.0, sample_mission, pt) == pytest.approx(
        per_km.evaluator(11.0, 25.0, sample_mission, pt)
    )


# ------------------------------------------------- the endurance surrogate

def test_endurance_surrogate_ranks_designs_identically(sample_aircraft, sample_mission):
    """The whole claim: argmin(surrogate) == argmax(endurance).

    Swept over the powers a real design plausibly draws, the two orderings must
    be exact mirrors — not merely correlated.
    """
    pt = _powertrain(sample_aircraft)
    obj = OBJECTIVES["endurance"]
    assert obj.nlp_surrogate is not None

    powers = np.linspace(5.0, 400.0, 200)
    endurance = [obj.evaluator(11.0, p, sample_mission, pt) for p in powers]
    surrogate = [obj.nlp_surrogate(11.0, p, sample_mission, pt) for p in powers]

    # ranking by ascending surrogate == ranking by descending endurance
    assert list(np.argsort(surrogate)) == list(np.argsort(endurance)[::-1])
    # and the best design agrees
    assert int(np.argmin(surrogate)) == int(np.argmax(endurance))


def test_endurance_surrogate_does_not_depend_on_airspeed(sample_aircraft, sample_mission):
    """Endurance has no V term of its own (wind is a constraint, not a term),
    so neither may its surrogate — otherwise it would quietly re-weight the
    speed the optimizer picks."""
    pt = _powertrain(sample_aircraft)
    obj = OBJECTIVES["endurance"]
    at_v = [obj.nlp_surrogate(v, 25.0, sample_mission, pt) for v in (7.0, 11.0, 20.0)]
    assert len(set(at_v)) == 1


def test_endurance_surrogate_is_finite_where_the_evaluator_blows_up(
    sample_aircraft, sample_mission
):
    """The point of the reformulation (FINDINGS §14.5.5).

    An interior-point method evaluates the objective at infeasible iterates,
    where nothing holds bus power positive: sampled over the sample aircraft's
    variable box, p_total is non-positive across 23% of it. The evaluator has a
    pole there. The surrogate must not.
    """
    pt = _powertrain(sample_aircraft)
    obj = OBJECTIVES["endurance"]
    avionics = pt.avionics_power_w

    # straddle the pole, including the exact singularity
    for p_elec in (-avionics, -avionics + 1e-9, -avionics - 1e-9, -100.0, -3.0, 0.0):
        s = obj.nlp_surrogate(11.0, p_elec, sample_mission, pt)
        assert np.isfinite(s), f"surrogate not finite at P_elec = {p_elec}"

    # and the evaluator really does blow up there — if this ever stops being
    # true the reformulation is no longer load-bearing and should be revisited
    at_pole = obj.evaluator(11.0, -avionics + 1e-9, sample_mission, pt)
    assert abs(at_pole) > 1e9

    # the sign flip either side of the pole is what made the merit function
    # unusable; the surrogate is monotone straight through it
    below = obj.nlp_surrogate(11.0, -avionics - 1.0, sample_mission, pt)
    above = obj.nlp_surrogate(11.0, -avionics + 1.0, sample_mission, pt)
    assert below < above


def test_reported_endurance_is_unchanged_by_the_reformulation(
    sample_aircraft, sample_mission
):
    """The surrogate changes what the SOLVER minimizes, never what the artifact
    says. `evaluate` is still the reported number, in minutes."""
    pt = _powertrain(sample_aircraft)
    obj = OBJECTIVES["endurance"]
    minutes = obj.evaluator(9.5, 18.1, sample_mission, pt)
    expected = pt.battery.usable_energy_wh * 60.0 / (18.1 + pt.avionics_power_w)
    assert minutes == pytest.approx(expected)
    assert obj.units == "min" and obj.direction == "maximize"
