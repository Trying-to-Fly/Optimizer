"""Max cruise speed: fastest *sustained* level flight (MODEL_DETAILS.md section 5.1).

Sustained = continuous motor/ESC current ratings and a config throttle-fraction
cap. Wind is irrelevant (airspeed objective).
"""

from . import Objective, register

OBJECTIVE = register(
    Objective(
        name="cruise_speed",
        direction="maximize",
        units="m/s",
        wind_mode="none",
        description="max V s.t. sustained-operation limits",
    )
)
