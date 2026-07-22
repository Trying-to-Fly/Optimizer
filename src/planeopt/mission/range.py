"""Range: maximize distance over ground (MODEL_DETAILS.md section 5.1).

Ground speed puts wind in the objective: E_usable * (V - v_wind) / P_total.
The fly-faster-into-headwind result must emerge, not be assumed.
"""

from . import Objective, register


def evaluate(V_ms, P_elec_w, mission, powertrain):
    """Kilometers over ground against the mission headwind."""
    p_total = P_elec_w + powertrain.avionics_power_w
    hours = powertrain.battery.usable_energy_wh / p_total
    return hours * (V_ms - mission.v_wind_ms) * 3.6  # (m/s x h) -> km


OBJECTIVE = register(
    Objective(
        name="range",
        direction="maximize",
        units="km",
        wind_mode="objective",
        description="E_usable * (V - v_wind) / (P_elec + P_avionics)",
        evaluator=evaluate,
    )
)
