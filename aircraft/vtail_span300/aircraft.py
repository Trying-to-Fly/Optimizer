"""`vtail_sample` with the projected-span cap moved 2.0 m -> 3.0 m.

**RETIRED 2026-08-04 — it ran, it answered, and the answer was NOT adopted.**
`runs/20260801T043954-endurance_sample-vtail_sample_v1-7_span300` found the curve
turning over at **2.497 m interior** (150.53 min), and the user kept the 2.0 m
cap anyway: the cap is a build decision — transport, storage, hand-launch, print
— and this model prices none of that. The reasoning below is preserved because
the question is re-openable, not because it is open. Running this package again
is one command and still valid; what it must NOT do is quietly become the sample.
FINDINGS section 19 has the result; `VTailSample.span_cap_m` carries the decision
and its measured price.

Every question this file posed was answered, and the answers are in section 19:
the spar STAYED pinned at 14 mm, the flatness sweep DID find an interior optimum
(6 of 6 members converged, both sides of the curve drawn), and the 1-1.5 min
extrapolation it was built to test was **wrong by a factor of four** — 2.0 -> 2.5 m
is worth ~6.3 min at the incumbent prop. That is the fourth time this project has
extrapolated a slope measured against a wall and been wrong about it.

An EXPERIMENT, not a design change, and deliberately a large one: the user asked
"what does it end at" with the cap effectively out of the way. Everything except
the cap is inherited from `vtail_sample`, so any difference is attributable to
the cap alone — which is why this is a subclass rather than a copy.

WHY IT WAS WORTH RUNNING

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
    #: DERIVED from the base name rather than restated, so a retired package
    #: cannot drift into claiming a version whose feasible set it no longer
    #: shares. The version is the sample's; the suffix is the one difference.
    name = _base.VTailSample.name + "_span300"
    #: The only change. The root-chord cap stays at the promoted 275 mm so this
    #: run differs from the current sample in exactly one number.
    span_cap_m = 3.0


AIRCRAFT = VTailSpan300()
