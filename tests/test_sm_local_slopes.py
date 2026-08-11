"""The local-slope check must not vote on its own noise.

`sm_local` is a two-point difference quotient of `Cm`, and an airworthiness gate
acts on its sign. FINDINGS §38.3 measured what that costs: on the rcv2 champion
`Cm` moves 0.0024 across the whole +/-2 deg window at 9.5 m/s, and differencing
it reports a sign flip at a 1 deg alpha step, none at 0.5, and none at 2.0. The
step was selecting the verdict, and every candidate in the 2026-08-11 sweep was
rejected on it.

The numbers below are MEASURED, not invented — `spanwise_resolution=24` on the
`20260811T115713` champion at 9.5 m/s, trim alpha 6.2289 deg, captured with
`tools/bughunt/sm_resolution_experiment.py`. A test for a noise question written
against made-up data would prove nothing about the noise.
"""

from __future__ import annotations

import pytest

from planeopt import aero, solve

TRIM_ALPHA = 6.22888902251978

#: The production window: SM_ALPHA_OFFSETS (+/-2) plus SM_DIAGNOSTIC_OFFSETS
#: (+/-1). This is the reading that produced `sm_sign_consistent = False` and
#: sank every candidate.
PRODUCTION_CL = [0.678197, 0.762599, 0.837477, 0.904867, 0.960875]
PRODUCTION_CM = [-0.053389, -0.068659, -0.068399, -0.067083, -0.068748]
PRODUCTION = (PRODUCTION_CL, PRODUCTION_CM)

#: The SAME aeroplane at the same trim, differenced over half and double the
#: step. If the flip were the airframe these would agree with the above.
HALF_STEP_CL = [0.762599, 0.801072, 0.837477, 0.872153, 0.904867]
HALF_STEP_CM = [-0.068659, -0.069518, -0.068399, -0.06739, -0.067083]
DOUBLE_STEP_CL = [0.503708, 0.678197, 0.837477, 0.960875, 1.031049]
DOUBLE_STEP_CM = [-0.039974, -0.053389, -0.068399, -0.068748, -0.076091]
HALF_STEP = (HALF_STEP_CL, HALF_STEP_CM)
DOUBLE_STEP = (DOUBLE_STEP_CL, DOUBLE_STEP_CM)

ALPHAS = [4.2, 5.2, 6.2, 7.2]


def slopes(cls, cms):
    return aero.local_slopes_with_uncertainty(cls, cms, ALPHAS)


def test_the_production_reading_has_negative_slopes_that_are_not_significant():
    """The exact reading that rejected every 2026-08-11 candidate."""
    local, sigma = slopes(PRODUCTION_CL, PRODUCTION_CM)

    negative = [p for p in local if p["sm_local"] < 0]
    assert negative, "this measured window really does contain negative slopes"
    assert not any(p["locally_unstable"] for p in local), (
        "none of them exceeds its own uncertainty, so none is evidence"
    )
    # Each negative slope is an order of magnitude inside its own error bar.
    for p in negative:
        assert abs(p["sm_local"]) < 0.5 * p["sm_local_uncertainty"]
    assert sigma > 0


def test_the_production_step_no_longer_votes_but_a_half_step_still_would():
    """What the fix achieves, and what it does NOT — both pinned deliberately.

    At the PRODUCTION window (SM_ALPHA_OFFSETS +/-2 with SM_DIAGNOSTIC_OFFSETS
    +/-1) the negative slopes stop counting, which is the false rejection that
    sank every 2026-08-11 candidate. At double the step they never counted.

    At HALF the step two slopes are still flagged, and that is an honest
    limitation rather than an oversight: `sigma` is the residual of a straight
    line through the window, so over a narrow enough window a curve looks
    straight, `sigma` collapses (6.2e-04 against 5.2e-03 at the production step)
    and the error bars shrink with it. The estimator measures departure from
    linearity, not the evaluation's noise floor, and those coincide only when
    the window is wide enough to contain some curvature.

    So this fix removes a false rejection at the setting the gate actually uses.
    It does not make the diagnostic step-independent, and FINDINGS §38.5 says
    what would: a noise floor measured rather than inferred from the same five
    points it is judging.
    """
    production = any(p["locally_unstable"] for p in slopes(*PRODUCTION)[0])
    double = any(p["locally_unstable"] for p in slopes(*DOUBLE_STEP)[0])
    half = any(p["locally_unstable"] for p in slopes(*HALF_STEP)[0])

    assert production is False, "the reading the gate uses must stop voting"
    assert double is False
    assert half is True, (
        "if this ever goes False, the narrow-window sigma collapse has been "
        "fixed and §38.5's remaining work is done — update the docs, do not "
        "just relax the test"
    )

    # The bare sign disagreed across all three, which is why any of this exists.
    bare = [any(p["sm_local"] < 0 for p in slopes(*d)[0])
            for d in (HALF_STEP, PRODUCTION, DOUBLE_STEP)]
    assert len(set(bare)) == 2, f"the measured ambiguity must remain visible: {bare}"


def test_a_genuinely_unstable_slope_is_still_caught():
    """Softening the test must not disarm it. A Cm that turns hard upward
    against CL is real instability, not scatter."""
    cls = [0.60, 0.70, 0.80, 0.90, 1.00]
    cms = [-0.10, -0.12, -0.14, -0.05, 0.10]  # slope reverses, and by a lot
    local, _ = slopes(cls, cms)

    assert any(p["locally_unstable"] for p in local)
    worst = solve.sm_sign_flip({"static_margin": 0.09, "sm_local_slopes": local})
    assert worst is not None and worst["sm_local"] < 0


def test_a_narrower_interval_is_told_it_is_worse_conditioned():
    """WITHIN one reading, the error bar must grow as the CL interval shrinks —
    that is the mechanism. (Across readings it need not, because `sigma` moves
    too; see the half-step case above.)"""
    local, _ = slopes(*PRODUCTION)
    d_cl = [PRODUCTION[0][i + 1] - PRODUCTION[0][i] for i in range(4)]
    assert d_cl == sorted(d_cl, reverse=True), "this window's intervals narrow"

    u = [p["sm_local_uncertainty"] for p in local]
    assert u == sorted(u), f"uncertainty must rise as the interval narrows: {u}"


def test_sm_sign_flip_reads_the_flag_not_the_bare_sign():
    local = [{"alpha": 5.0, "sm_local": -0.004,
              "sm_local_uncertainty": 0.15, "locally_unstable": False}]
    assert solve.sm_sign_flip({"static_margin": 0.09, "sm_local_slopes": local}) is None


def test_an_artifact_written_before_the_flag_existed_is_judged_as_it_was():
    """Re-reading an old run must not silently re-judge it under a rule that
    did not exist when it was written."""
    old = [{"alpha": 5.0, "sm_local": -0.004}]
    assert solve.sm_sign_flip({"static_margin": 0.09, "sm_local_slopes": old}) is not None


@pytest.mark.parametrize("sm", [None, 0.0, -0.01])
def test_a_non_positive_margin_short_circuits(sm):
    """The predicate is about a POSITIVE margin hiding local instability."""
    local = [{"alpha": 5.0, "sm_local": -0.5,
              "sm_local_uncertainty": 0.01, "locally_unstable": True}]
    assert solve.sm_sign_flip({"static_margin": sm, "sm_local_slopes": local}) is None


#: Measured margin against spanwise panels, same champion and window
#: (FINDINGS §38.2). Monotone and converging DOWNWARD, which is why the default
#: cannot be what an airworthiness gate reads.
MARGIN_VS_RESOLUTION = {
    9.5: {None: 0.05229, 8: 0.04973, 12: 0.04893, 16: 0.04845, 24: 0.04804},
    10.5: {None: 0.08027, 8: 0.07728, 12: 0.07622, 16: 0.07566, 24: 0.07516},
}


def test_the_reeval_resolution_is_converged_rather_than_the_default():
    """The default overstates the margin by ~0.005 — a quarter of the declared
    0.08 floor, and the difference between passing it and not: at 10.5 m/s the
    reading falls from 0.08027 (inside the window) to 0.07516 (outside)."""
    for speed, by_res in MARGIN_VS_RESOLUTION.items():
        assert by_res[None] > by_res[24], f"{speed} m/s: default should be optimistic"
        assert by_res[aero.SM_REEVAL_SPANWISE] == pytest.approx(
            min(by_res.values()), abs=5e-4
        ), f"{speed} m/s: the chosen resolution must be on the converged plateau"

    assert aero.SM_REEVAL_SPANWISE >= 16, "16 is where the sequence goes flat"


def test_the_reeval_actually_asks_for_that_resolution():
    """A constant nothing passes is a comment. The gate reads the re-evaluated
    margin, so that call is the one that has to carry it."""
    import inspect

    src = inspect.getsource(solve)
    assert "spanwise_resolution=aero.SM_REEVAL_SPANWISE" in src
