"""endurance_sample — written by the planeopt GUI.

Mission-type constraint values live here, not in the aircraft config: they
describe what the aircraft is *for*, not what it *is*. Safe to hand-edit.
"""

from planeopt.types import MissionSpec

MISSION = MissionSpec(
    name='endurance_sample',
    objective='endurance',
    v_wind_ms=4.0,
    penetration_margin_ms=5.5,
    v_stall_max_ms=8.0,
    static_margin_range=(0.08, 0.15),
    ballast_max_kg=0.07,
    notes='written by the planeopt GUI',
)
