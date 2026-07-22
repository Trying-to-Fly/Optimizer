"""Range: maximize distance over ground (MODEL_DETAILS.md section 5.1).

Ground speed puts wind in the objective: E_usable * (V - v_wind) / P_total.
The fly-faster-into-headwind result must emerge, not be assumed.
"""

from . import Objective, register

OBJECTIVE = register(
    Objective(
        name="range",
        direction="maximize",
        units="km",
        wind_mode="objective",
        description="E_usable * (V - v_wind) / (P_elec + P_avionics)",
    )
)
