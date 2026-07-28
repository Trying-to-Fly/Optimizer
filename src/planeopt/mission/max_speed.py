"""Raw max speed: full-throttle level flight (MODEL_DETAILS.md section 5.1).

The objective is the airspeed itself — everything interesting lives in the
constraints, which is what makes this objective different in character from the
energy ones. Three things bound it, all applied in solve._solve_nlp:

- **pack voltage**: motor terminal voltage <= battery voltage. This *is* the
  full-throttle condition; without it the solver quietly assumes a bigger
  battery than the aircraft carries.
- **burst current**: this objective is allowed the motor's burst rating rather
  than the ESC's continuous rating — a dash condition, not one to hold.
- **placard speed**: a declared `placard_speed_ms` on the aircraft. Flutter and
  divergence are beyond this model's fidelity, so the never-exceed speed is
  declared by the airframe, never predicted here.

Wind is irrelevant to an airspeed objective (wind_mode="none").
"""

from . import Objective, register


def evaluate(V_ms, P_elec_w, mission, powertrain):
    """Airspeed is the objective. P enters only through the constraints above."""
    return V_ms


OBJECTIVE = register(
    Objective(
        name="max_speed",
        direction="maximize",
        units="m/s",
        wind_mode="none",
        description="max V at full throttle, burst limits",
        evaluator=evaluate,
        current_limit="burst",
    )
)
