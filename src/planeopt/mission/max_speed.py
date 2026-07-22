"""Raw max speed: full-throttle level flight (MODEL_DETAILS.md section 5.1).

P_available = P_required with burst current limits. Flutter/divergence are beyond
model fidelity — V_max is reported against a declared config placard speed.
"""

from . import Objective, register

OBJECTIVE = register(
    Objective(
        name="max_speed",
        direction="maximize",
        units="m/s",
        wind_mode="none",
        description="max V at full throttle, burst limits",
    )
)
