"""`vtail_sample` with the projected-span cap moved 2.0 m -> 3.0 m.

An EXPERIMENT, not a design change, and deliberately a large one: the user asked
"what does it end at" with the cap effectively out of the way. Everything except
the cap is inherited from `vtail_sample`, so any difference is attributable to
the cap alone — which is why this is a subclass rather than a copy.

WHY IT IS WORTH RUNNING

`span` has sat exactly on its cap in every solve this project has ever done, at
2.2 m and at 2.0 m, and the span sweep has always been climbing into the bound.
So the optimizer has never once been allowed to show where the curve turns over,
and every "span is worth X" figure to date is a slope read against a wall.

The 2026-07-31 session sharpened the question rather than answering it
(FINDINGS section 15.8): at the 275 mm chord cap the clean span slope is
**+0.79 min/100 mm** between 1.9 and 2.0 m — less than half the 1.72 measured
before the chord cap moved, because half the apparent value of span was the wing
compensating for chord it was not allowed to have. And AUW is still FALLING with
span (1.884 kg at 1.8 m, 1.836 at 2.0 m), so the mass term that must eventually
turn the curve over has not begun to bite. Extrapolating 0.79 suggested
2.0 -> 2.2 m is worth roughly 1-1.5 min. **This run is what tests that
extrapolation, and it is exactly the kind of extrapolation this project has been
wrong about before.**

WHAT TO WATCH, BEYOND THE OBJECTIVE

- **The spar.** `spar_od_center` is already pinned at its 14 mm maximum at 2.0 m,
  and bending moment grows faster than span. If it stays pinned, the answer at
  3 m is a property of the declared spar stock rather than of aerodynamics — the
  same trap `c_root` set at the print bed. `active_bounds` in run.json now names
  this without anyone having to look for it.
- **Whether the flatness sweep finds an interior optimum.** It samples
  `linspace(1.5, 3.0, 6)`, so for the first time the upper half of the range is
  above every span ever solved.
- **Buildability, which the model does not see.** The declared 2.0 m cap is a
  manufacturing decision (user, 2026-07-24, 2.2 -> 2.0). A 3 m wing is a
  different aeroplane to transport, store, hand-launch and print; nothing here
  prices any of that. Treat the result as "what the aerodynamics wants", and let
  the cap stay a build decision.
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


class VTailSpan300(_base.VTailSample):
    name = "vtail_sample_v1.7_span300"
    #: The only change. The root-chord cap stays at the promoted 275 mm so this
    #: run differs from the current sample in exactly one number.
    span_cap_m = 3.0


AIRCRAFT = VTailSpan300()
