"""Endurance: maximize time aloft. The sample mission (MODEL_DETAILS.md section 5.1).

Wind does not change loiter power at a given airspeed; it enters only as the
minimum-airspeed constraint V >= v_wind + margin — whether that constraint is
active is itself a key output.
"""

from . import Objective, register


def evaluate(V_ms, P_elec_w, mission, powertrain):
    """Minutes aloft; V enters only via P (wind is a constraint, not a term)."""
    p_total = P_elec_w + powertrain.avionics_power_w
    return powertrain.battery.usable_energy_wh * 60.0 / p_total


def surrogate(V_ms, P_elec_w, mission, powertrain):
    """What the NLP minimizes instead: total bus power. Same argmin, no pole.

    `usable_energy_wh` is fixed hardware — a constant, not a design variable —
    so on p_total > 0 endurance is a strictly DECREASING function of p_total.
    The design that draws least power is the design that stays up longest, and
    the two problems have the same solution exactly, not approximately.

    Why it matters (FINDINGS §14.5.5): `evaluate` divides by p_total, so its
    gradient goes as 1/p_total^2, and p_total is held positive only by
    `thrust == drag` — an EQUALITY, which an interior-point method violates on
    the way to a solution. Sampled over the sample aircraft's declared variable
    box, P_elec runs -109 W to +867 W and p_total is non-positive across 23% of
    it; near the pole the objective reached 5.5e4 minutes and its gradient
    2.4e7. That singularity, not the constraints, is what made the short-span,
    pusher and printed-mass solves burn hundreds of iterations without
    converging while never once being declared infeasible.

    Minimizing p_total is bounded, smooth and sign-stable over the same box.
    The reported endurance still comes from `evaluate`, so the artifact is
    unchanged.
    """
    return P_elec_w + powertrain.avionics_power_w


OBJECTIVE = register(
    Objective(
        name="endurance",
        direction="maximize",
        units="min",
        wind_mode="constraint",
        description="E_usable / (P_elec + P_avionics), pure cruise",
        evaluator=evaluate,
        nlp_surrogate=surrogate,
    )
)
