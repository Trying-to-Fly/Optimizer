"""Endurance: maximize time aloft. The sample mission (MODEL_DETAILS.md section 5.1).

Wind does not change loiter power at a given airspeed; it enters only as the
minimum-airspeed constraint V >= v_wind + margin — whether that constraint is
active is itself a key output.
"""

from . import Objective, register

OBJECTIVE = register(
    Objective(
        name="endurance",
        direction="maximize",
        units="min",
        wind_mode="constraint",
        description="E_usable / (P_elec + P_avionics), pure cruise",
    )
)
