"""Sample mission: endurance for the test aircraft (MODEL_DETAILS.md section 5.1).

Mission-type constraint values live here, not in the aircraft config.
"""

from planeopt.types import MissionSpec

MISSION = MissionSpec(
    name="endurance_sample",
    objective="endurance",
    v_wind_ms=4.0,
    penetration_margin_ms=5.5,   # -> v_min 9.5 m/s
    v_stall_max_ms=8.0,
    static_margin_range=(0.08, 0.15),
    ballast_max_kg=0.070,
    notes="DESIGN_SPEC.md sample plane; Phase 1 gate targets: stall ~8.3 m/s, "
          "80-110 W cruise at 12-14 m/s, 30-40 min endurance.",
)
