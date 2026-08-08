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
import re
import sys
from pathlib import Path

from ..types import MissionSpec

#: What may appear in a mission module's FILENAME. The New Run dialog takes the
#: name from a free-text field, and that one string was being used as two things
#: that disagree about what is legal in it: a path, and Python source.
#:
#: `missions/<name>.py` with a name a human would actually type:
#:   "endurance 3m/s wind"   -> created `missions/endurance 3m/` and put the
#:                              module inside it, where `workspace.missions()`
#:                              (a non-recursive glob) can never see it again
#:   "../aircraft/aircraft"  -> wrote OUTSIDE missions/ and overwrote a real
#:                              aircraft definition
#: Same rule as `assemble.write_run_dir`'s run-directory slug, so the two kinds
#: of artifact name in this project are legible the same way.
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")

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


def module_name(name: str) -> str:
    """A mission name reduced to something safe to be a filename.

    The name the user typed is kept verbatim in the `name=` field — that is the
    authoritative record and it round-trips exactly. This is only what the file
    is CALLED. Falls back to "mission" when nothing survives, which is the same
    fallback the dialog already applies to an empty field.
    """
    return _UNSAFE.sub("_", name).strip("_") or "mission"


def path_for(missions_dir: Path, mission: MissionSpec) -> Path:
    """Where `mission`'s module belongs. The one place that decides."""
    return Path(missions_dir) / f"{module_name(mission.name)}.py"


def _docstring_safe(name: str) -> str:
    """`name` with the three things that can break the docstring it lands in.

    A name is rendered into a `\"\"\"...\"\"\"` header, so a name containing a
    triple quote produced a module that would not parse — the dialog accepted
    it, queued the job, and the child died on a SyntaxError before it read the
    aircraft. Backslashes and newlines go for the same reason.
    """
    return name.replace("\\", " ").replace('"', "'").replace("\n", " ").replace("\r", " ").strip()


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
    return _TEMPLATE.format(
        name=_docstring_safe(mission.name) or module_name(mission.name),
        fields="\n".join(lines),
    )


def save(mission: MissionSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(mission), encoding="utf-8")
    return path
