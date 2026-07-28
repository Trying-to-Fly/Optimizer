"""Construction profiles for the speed airframe — same shop as the sample plane.

Identical LW-PLA / Bambu A1 process as `aircraft/vtail_sample/lwpla_a1.py`, with
one difference that matters: a speed airframe flies at higher q and takes higher
gust loads, so the skin is two perimeters rather than one. That is a heavier
`k_skin` and nothing else.

ALL VALUES UNCALIBRATED (calibrated=False) — ballparks from MODEL_DETAILS.md
section 1.2, to be replaced by tools/fit_profile.py from slicer data. Absolute
masses are therefore soft; rankings between designs are what this supports.
"""

import dataclasses

from planeopt.types import ConstructionProfile

LWPLA_A1_SPEED = ConstructionProfile(
    name="lwpla_a1_double_perimeter",
    k_skin_kg_m2=0.430,  # ~2 x 0.45 mm wall x ~0.6 g/cm3 foamed, minus shared corners
    k_rib_kg_m2=0.180,
    rib_pitch_m=0.070,  # closer rib pitch: thinner sections at higher loading
    k_joint_kg=0.008,
    section_length_m=0.225,
    overhead_kg=0.060,  # servo mounts, root tabs, tips, hinge hardware
    finish_factor=1.05,
    calibrated=False,
)

# Horizontal stabiliser: same lay-up, smaller per-surface overhead (root block +
# linkage rather than wing servo mounts and tips).
LWPLA_A1_SPEED_TAIL = dataclasses.replace(
    LWPLA_A1_SPEED, name="lwpla_a1_speed_tail", overhead_kg=0.030
)

# Vertical fin: root mount and rudder hinge hardware only — the tail servos are
# counted once in fixed_equipment.
LWPLA_A1_SPEED_FIN = dataclasses.replace(
    LWPLA_A1_SPEED, name="lwpla_a1_speed_fin", overhead_kg=0.020
)

# Winglet variant: a small surface — tip cap and glue face only. The root socket
# and pins are counted separately as winglet_joiners in structure_extras.
LWPLA_A1_SPEED_WINGLET = dataclasses.replace(
    LWPLA_A1_SPEED, name="lwpla_a1_speed_winglet", overhead_kg=0.010
)
