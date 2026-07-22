"""Minimum energy per distance, Wh/km (MODEL_DETAILS.md section 5.1).

Dual of range at fixed usable energy; its own entry for battery-sizing and
payload studies where E_usable varies.
"""

from . import Objective, register

OBJECTIVE = register(
    Objective(
        name="energy_per_km",
        direction="minimize",
        units="Wh/km",
        wind_mode="objective",
        description="(P_elec + P_avionics) / (V - v_wind)",
    )
)
