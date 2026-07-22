"""Objective registry — MODEL_DETAILS.md section 5.1 as code.

Each mission module registers one Objective. Evaluators are implemented against the
module contracts (aero + propulsion outputs at an operating point); they become real
at M2. Wind mode is per-objective — there is no global wind rule (section 5.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

WindMode = Literal["constraint", "objective", "none"]


@dataclass(frozen=True)
class Objective:
    name: str
    direction: Literal["maximize", "minimize"]
    units: str
    wind_mode: WindMode
    description: str
    evaluator: Callable | None = None  # implemented from M2 onward


OBJECTIVES: dict[str, Objective] = {}


def register(obj: Objective) -> Objective:
    OBJECTIVES[obj.name] = obj
    return obj


# Importing the modules populates the registry.
from . import cruise_speed, endurance, energy_per_km, max_speed, range  # noqa: E402,F401
