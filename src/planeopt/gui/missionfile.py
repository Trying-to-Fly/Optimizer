"""Mission modules <-> form values.

A mission is pure data (MissionSpec), which is what makes a form safe here and
not for an aircraft: there is nothing to express but numbers and a registry key.
So the GUI keeps missions as real `.py` files rather than inventing a parallel
format — runs stay reproducible, the `inputs/` snapshot keeps working, and a
mission written by the form can still be hand-edited afterwards.

Loading imports the module and reads the dataclass (no parsing). Writing renders
a readable module from the field values.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

from ..types import MissionSpec

_TEMPLATE = '''"""{name} — written by the planeopt GUI.

Mission-type constraint values live here, not in the aircraft config: they
describe what the aircraft is *for*, not what it *is*. Safe to hand-edit.
"""

from planeopt.types import MissionSpec

MISSION = MissionSpec(
{fields}
)
'''

# Fields the form exposes. `sweeps` is deliberately absent: it is an
# epsilon-constraint axis list, not a scalar, and belongs to the Pareto command.
FORM_FIELDS = (
    "name",
    "objective",
    "v_wind_ms",
    "penetration_margin_ms",
    "v_stall_max_ms",
    "static_margin_range",
    "ballast_max_kg",
    "notes",
)


def load(path: Path) -> MissionSpec:
    """Import a mission module and return its MISSION object."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    mission = getattr(module, "MISSION", None)
    if mission is None:
        raise ValueError(f"{path} does not define MISSION")
    return mission


def render(mission: MissionSpec) -> str:
    """Render a MissionSpec as a mission module's source."""
    lines = []
    for f in dataclasses.fields(mission):
        if f.name not in FORM_FIELDS:
            continue
        value = getattr(mission, f.name)
        if value is None and f.name in ("v_stall_max_ms", "ballast_max_kg"):
            lines.append(f"    {f.name}=None,")
        elif isinstance(value, str):
            lines.append(f"    {f.name}={value!r},")
        elif isinstance(value, tuple):
            lines.append(f"    {f.name}={value!r},")
        else:
            lines.append(f"    {f.name}={value!r},")
    return _TEMPLATE.format(name=mission.name, fields="\n".join(lines))


def save(mission: MissionSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(mission), encoding="utf-8")
    return path
