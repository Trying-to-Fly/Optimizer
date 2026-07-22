"""Construction profile: LW-PLA on the Bambu A1, single-perimeter skin + printed ribs.

ALL VALUES UNCALIBRATED (calibrated=False): ballparks from MODEL_DETAILS.md
section 1.2, to be replaced by tools/fit_profile.py from slicer data
(section 1.4 — slice 2-3 scaled wing sections, regress the terms).
"""

from planeopt.types import ConstructionProfile

LWPLA_A1 = ConstructionProfile(
    name="lwpla_a1_single_perimeter",
    k_skin_kg_m2=0.270,   # 0.45 mm wall x ~0.6 g/cm3 foamed
    k_rib_kg_m2=0.180,    # rib mass ~ k * chord^2 per rib — pure placeholder
    rib_pitch_m=0.090,
    k_joint_kg=0.008,     # lip + pins + glue per section joint
    section_length_m=0.225,
    overhead_kg=0.060,    # servo mounts, root tabs, tips/winglets, hinge hardware
    finish_factor=1.05,
    calibrated=False,
)

import dataclasses

# V-tail variant: same construction, smaller per-surface overhead
# (root block ~22 g + linkages ~6 g instead of wing servo mounts/tips)
LWPLA_A1_TAIL = dataclasses.replace(LWPLA_A1, name="lwpla_a1_tail", overhead_kg=0.030)
