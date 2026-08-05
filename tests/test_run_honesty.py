"""What a run is entitled to CLAIM, as distinct from what it computed.

Every property here comes from the 2026-08-05 battery, which converged cleanly
and whose artifact was nonetheless wrong about four things — not in its numbers,
in its claims:

  - it reported 142.09 min as the aeroplane's best, when the sweep's own optimum
    was 143.01 min and only the minimum-speed requirement stood between them;
  - it reported V = 8.0 m/s "infeasible" on the strength of a message about
    IPOPT's step size;
  - it reported a static margin of 0.0800 for an aircraft whose local dCm/dCL at
    its own trim alpha is negative;
  - it reported multistart and the flatness sweep at 0.0 minutes, which reads as
    "skipped" and meant "resumed".

None of those needs an aircraft to reproduce, which is the point: they are
properties of how the run describes itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from planeopt import solve

MAXIMIZE = 1


def _pt(v, obj):
    return {"V_ms": v, "objective_value": obj}


# --- the minimum-speed requirement, priced --------------------------------


def test_v_min_price_names_the_peak_the_requirement_excludes():
    """The 2026-08-05 shape: the sweep peaks below v_min, so the headline number
    is the requirement's, not the airframe's."""
    airworthy = [_pt(8.5, 139.45), _pt(9.0, 143.01), _pt(9.5, 142.09), _pt(10.0, 139.23)]
    best = _pt(9.5, 142.09)

    priced = solve.v_min_price(airworthy, best, v_min_ms=9.5, sign=MAXIMIZE)

    assert priced is not None
    assert priced["unconstrained_best_V_ms"] == 9.0
    assert priced["cost_of_v_min"] == pytest.approx(143.01 - 142.09)


def test_no_price_when_the_optimum_is_already_legal():
    """An interior optimum owes v_min nothing, and saying otherwise would put a
    scary note on every run that does not need one."""
    airworthy = [_pt(9.5, 140.0), _pt(10.0, 143.0), _pt(10.5, 141.0)]

    assert solve.v_min_price(airworthy, _pt(10.0, 143.0), 9.5, MAXIMIZE) is None


def test_the_price_follows_the_objective_direction():
    """A minimized objective (mass, energy per km) peaks the other way; the
    requirement is still what excludes the winner."""
    airworthy = [_pt(8.0, 10.0), _pt(9.0, 25.0)]

    priced = solve.v_min_price(airworthy, _pt(9.0, 25.0), v_min_ms=9.0, sign=-1)

    assert priced["unconstrained_best_V_ms"] == 8.0
    assert priced["cost_of_v_min"] == pytest.approx(15.0)


def test_an_empty_sweep_prices_nothing_rather_than_raising():
    """`run` already raises its own, far better, error when nothing trims — this
    must not pre-empt it with a max() on an empty sequence."""
    assert solve.v_min_price([], _pt(9.5, 1.0), 9.5, MAXIMIZE) is None


# --- a static margin that changes sign inside its own window ---------------


def test_sign_flip_is_caught_under_a_positive_reported_margin():
    """The champion's actual numbers. The regression says 0.0800 and passes; the
    local slope at the trim alpha says the aeroplane is unstable there."""
    sm = {
        "static_margin": 0.08000015740224872,
        "sm_local_slopes": [
            {"alpha": 3.68, "sm_local": 0.1867953836284154},
            {"alpha": 4.68, "sm_local": 0.13828341836237237},
            {"alpha": 5.68, "sm_local": -0.022067618955063283},
            {"alpha": 6.68, "sm_local": -0.019115899958615457},
        ],
    }

    worst = solve.sm_sign_flip(sm)

    assert worst is not None
    assert worst["alpha"] == 5.68  # the MOST negative, not merely the first
    assert worst["sm_local"] < 0


def test_a_margin_positive_throughout_raises_nothing():
    sm = {
        "static_margin": 0.12,
        "sm_local_slopes": [{"alpha": 4.0, "sm_local": 0.13}, {"alpha": 6.0, "sm_local": 0.11}],
    }

    assert solve.sm_sign_flip(sm) is None


def test_an_already_negative_margin_is_not_double_reported():
    """The guard exists to catch a margin that LOOKS fine. A design whose
    reported margin is itself negative already fails `sm_in_range` loudly."""
    sm = {"static_margin": -0.03, "sm_local_slopes": [{"alpha": 4.0, "sm_local": -0.05}]}

    assert solve.sm_sign_flip(sm) is None


def test_missing_slopes_are_not_an_accusation():
    """A caller that did not ask for the diagnostic must not be told its
    aircraft is unstable."""
    assert solve.sm_sign_flip({"static_margin": 0.09}) is None
    assert solve.sm_sign_flip({"static_margin": 0.09, "sm_local_slopes": []}) is None


# --- non-convergence is not infeasibility ----------------------------------


def test_a_trim_failure_is_classified_as_the_solver_giving_up():
    """`aero.trim`'s wording, verbatim from the 2026-08-05 artifact."""
    e = RuntimeError(
        "trim failed at V=8.0: The iteration is not making good progress, as "
        "measured by the \n improvement from the last ten iterations. / "
        "least-squares residual too large"
    )

    assert solve._is_trim_failure(e) is True


def test_a_propulsion_failure_is_not_a_trim_failure():
    """A chain that cannot close IS a statement about the aeroplane, and must
    keep saying so rather than being softened into 'unknown'."""
    assert solve._is_trim_failure(ValueError("advance ratio beyond the fitted table")) is False
    assert solve._is_trim_failure(RuntimeError("no motor operating point")) is False


# --- a resumed phase must not read as a skipped one ------------------------


def test_the_cache_counts_what_it_served_per_phase(tmp_path):
    """0.0 minutes plus 'from checkpoint' is a resume; 0.0 minutes alone reads
    as a phase that never ran."""
    cache = solve._SolveCache(tmp_path, "abc123abc123")
    cache.put("multistart", "nominal", {"objective_value": 1.0})
    cache.put("multistart", "perturbed_0", {"objective_value": 2.0})
    cache.put("flatness sweep", "2.0", {"objective_value": 3.0})

    assert cache.resumed == {}  # writing is not resuming

    assert cache.get("multistart", "nominal") is not None
    assert cache.get("multistart", "perturbed_0") is not None
    assert cache.get("flatness sweep", "2.0") is not None

    assert cache.resumed == {"multistart": 2, "flatness sweep": 1}


def test_a_miss_counts_as_nothing(tmp_path):
    cache = solve._SolveCache(tmp_path, "abc123abc123")

    assert cache.get("multistart", "never_solved") is None
    assert cache.resumed == {}


def test_a_corrupt_entry_is_a_miss_not_a_resume(tmp_path):
    """It will be re-solved, so counting it as resumed would overstate what came
    off disk."""
    cache = solve._SolveCache(tmp_path, "abc123abc123")
    cache._path("multistart", "nominal").write_text("{not json", encoding="utf-8")

    assert cache.get("multistart", "nominal") is None
    assert cache.resumed == {}


def test_numpy_valued_sweep_points_price_correctly():
    """Sweep points carry numpy scalars; the arithmetic must not care."""
    airworthy = [_pt(np.float64(9.0), np.float64(143.01)), _pt(np.float64(9.5), np.float64(142.09))]

    priced = solve.v_min_price(airworthy, airworthy[1], 9.5, MAXIMIZE)

    assert float(priced["cost_of_v_min"]) == pytest.approx(143.01 - 142.09)
