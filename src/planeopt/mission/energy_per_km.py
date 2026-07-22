"""Minimum energy per distance, Wh/km (MODEL_DETAILS.md section 5.1).

Dual of range at fixed usable energy; its own entry for battery-sizing and
payload studies where E_usable varies.
"""

from . import Objective, register


def evaluate(V_ms, P_elec_w, mission, powertrain):
    """Wh per km over ground."""
    p_total = P_elec_w + powertrain.avionics_power_w
    return p_total / (3.6 * (V_ms - mission.v_wind_ms))


OBJECTIVE = register(
    Objective(
        name="energy_per_km",
        direction="minimize",
        units="Wh/km",
        wind_mode="objective",
        description="(P_elec + P_avionics) / (V - v_wind)",
        evaluator=evaluate,
    )
)
