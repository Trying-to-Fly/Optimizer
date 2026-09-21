"""Max-speed mission for the conventional puller fixture.

Mission-type constraint values live here, not in the aircraft config: they say
what the aircraft is *for*, not what it *is*.

Two values below drive this design more than anything else, so they are worth
arguing with rather than accepting:

- `v_stall_max_ms = 14.0` — the real cost of a fast plane is the landing. A
  speed objective shrinks the wing until something stops it, and this is that
  something. 14 m/s (~50 km/h) is a brisk but hand-landable approach on a big
  field; drop it to 11-12 and the wing grows, raise it and the wing shrinks.
- `static_margin_range = (0.05, 0.13)` — lower than the loiter plane's
  (0.08, 0.15). A speed airframe is flown actively and benefits from a smaller
  tail and less trim drag, but this is a handling preference, not physics.

Wind is irrelevant here: max_speed is an airspeed objective (wind_mode="none"),
so `v_wind_ms` and the penetration margin do nothing and are left at zero.
"""

from planeopt.types import MissionSpec

MISSION = MissionSpec(
    name="max_speed_sample",
    objective="max_speed",
    v_wind_ms=0.0,
    penetration_margin_ms=0.0,
    v_stall_max_ms=14.0,
    static_margin_range=(0.05, 0.13),
    ballast_max_kg=0.120,
    notes="Speed fixture: conventional tail, nose (puller) motor, same 4S "
    "powertrain as the endurance plane. Bounded by pack voltage (full "
    "throttle), the 55 A burst current rating, and the airframe's declared "
    "45 m/s placard. Absolute speeds are uncalibrated — rankings and which "
    "limit binds are the trustworthy outputs.",
)
