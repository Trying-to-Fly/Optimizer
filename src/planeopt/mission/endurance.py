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


OBJECTIVE = register(
    Objective(
        name="endurance",
        direction="maximize",
        units="min",
        wind_mode="constraint",
        description="E_usable / (P_elec + P_avionics), pure cruise",
        evaluator=evaluate,
    )
)
