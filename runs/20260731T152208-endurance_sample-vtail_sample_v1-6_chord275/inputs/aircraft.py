"""`vtail_sample` with the root-chord cap moved 245 mm -> 275 mm.

An EXPERIMENT, not a new design. Everything except the cap is inherited from
`vtail_sample`, so any difference a run shows is attributable to the chord cap
alone. If the result is worth keeping, promoting it is a one-line change to
`VTailSample.c_root_max_m` rather than a merge.

WHY IT IS WORTH ASKING (2026-07-31)

`c_root` sits EXACTLY on its 245 mm cap in every solve that has ever converged —
both flatness members (span 2.0 and 1.9), and the champion. An always-active
bound is the optimizer saying it wants something it is not allowed to have.

Two candidate explanations were tested and REFUTED, so what the wing is buying
with that chord is genuinely not yet known:

- **Not the stall requirement.** The champion stalls at 7.715 m/s against a
  `v_stall_max_ms` of 8.0 — 7.5% of margin, so the constraint is inactive. It
  binds only below ~1.7 m of span.
- **Not the gust margin.** CL 0.781 against a 0.7*clmax_wing limit of 0.824.

And the static-margin floor is pushing chord the OTHER way — SM is a fraction of
MAC, so a fatter chord shrinks it, and SM is pinned at exactly 0.0800. Whatever
wants chord is therefore strong enough to beat both that and the added wetted
area. Prime suspect is Reynolds number: cruise Re is 134,000, which is the steep
part of the low-Re drag curve, chord is how you buy Re, and the model carries
explicit Re floors (wing tip 90e3, winglet and tail 60e3) that scale with chord.
The 1.8 m run has the winglet Re floor among its violations.

This run answers it directly. If `c_root` lands interior (< 275 mm) the true
optimum has been found and 245 mm was costing endurance; if it pins on 275 the
wing is still Reynolds-starved and the question is how much further to go.

WHY 275 mm IS BUILDABLE

The panel prints standing up — span along Z — so the bed footprint is chord x
thickness and Z height caps the segment LENGTH, not the chord. Rotated 45 deg in
plan on the Bambu A1's 256 mm square bed, a chord c with SD7037's 9.2% t/c needs
(1.092 c)/sqrt(2) per axis:

    245 mm -> 189 mm box (67 mm spare)
    275 mm -> 212 mm box (44 mm spare)
    332 mm -> 256 mm box (the geometric ceiling)

Axis-aligned the limit would be a flat 256 mm, which is why the rotation is what
makes 275 mm available at all. The airfoil still sits flush on the bed — this is
a yaw, not a tilt — so `LWPLA_A1` remains the right construction profile: same
material, same single-perimeter skin, same printed ribs. Nothing in the mass
model depends on how the part is oriented on the plate, so this is purely a
bound change.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent / "vtail_sample" / "aircraft.py"

# Loaded by path under a DISTINCT module name: `cli._load_attr` registers the
# module it loads as `sys.modules["aircraft"]`, so importing the sibling under
# its own stem would collide with whichever of the two was loaded second.
_spec = importlib.util.spec_from_file_location("vtail_sample_base", _BASE)
_base = importlib.util.module_from_spec(_spec)
sys.modules["vtail_sample_base"] = _base
sys.path.insert(0, str(_BASE.parent))  # it imports its own construction profile
try:
    _spec.loader.exec_module(_base)
finally:
    sys.path.remove(str(_BASE.parent))


class VTailChord275(_base.VTailSample):
    name = "vtail_sample_v1.6_chord275"
    #: The only change. Span cap deliberately left at 2.0 m so this run differs
    #: from the 2026-07-31 champion in exactly one number.
    c_root_max_m = 0.275


AIRCRAFT = VTailChord275()
