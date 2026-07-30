"""Objective registry — MODEL_DETAILS.md section 5.1 as code.

Each mission module registers one Objective. Evaluators are implemented against the
module contracts (aero + propulsion outputs at an operating point); they become real
at M2. Wind mode is per-objective — there is no global wind rule (section 5.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

WindMode = Literal["constraint", "objective", "none"]


CurrentLimit = Literal["continuous", "burst"]


@dataclass(frozen=True)
class Objective:
    name: str
    direction: Literal["maximize", "minimize"]
    units: str
    wind_mode: WindMode
    description: str
    evaluator: Callable | None = None  # implemented from M2 onward
    # Which side of the powertrain rating this objective may run against
    # (MODEL_DETAILS section 2.5). Loiter objectives sit far inside either, but
    # a speed objective pushes to whichever cap it is allowed — so the choice
    # belongs to the objective, not to a global constant.
    current_limit: CurrentLimit = "continuous"
    #: Optional expression for the NLP to MINIMIZE in place of the evaluator.
    #:
    #: An evaluator is written to be *reported*: it says what the design is
    #: worth, in the objective's own units, and the natural way to write that is
    #: often a quotient. A quotient is a bad thing to hand an optimizer — it has
    #: a pole wherever the denominator vanishes, and the solver evaluates the
    #: objective at INFEASIBLE iterates where nothing pins the denominator away
    #: from zero. `endurance` cost four sessions of failed solves to exactly
    #: that (FINDINGS §14.5.5): a quarter of the sample aircraft's variable box
    #: has non-positive bus power, and the gradient reached 2.4e7 near the pole.
    #:
    #: A surrogate is any function with the SAME ARGMIN over the feasible set —
    #: a monotone transform of the true objective — chosen to be well behaved
    #: everywhere the solver might step. It is always MINIMIZED, so `direction`
    #: does not apply to it; the reported value still comes from `evaluator`, so
    #: nothing downstream changes units or meaning.
    #:
    #: Same signature as `evaluator`. Declaring one is a claim that wants a test
    #: (see tests/test_objectives.py).
    nlp_surrogate: Callable | None = None

    def nlp_expression(self, V_ms, P_elec_w, mission, powertrain):
        """The expression the NLP minimizes for this objective.

        The surrogate when one is declared, otherwise the evaluator with its
        sign flipped for a maximization. This is the ONE place the optimizer's
        objective is formed, so a surrogate cannot be half-adopted.
        """
        if self.nlp_surrogate is not None:
            return self.nlp_surrogate(V_ms, P_elec_w, mission, powertrain)
        value = self.evaluator(V_ms, P_elec_w, mission, powertrain)
        return -value if self.direction == "maximize" else value


OBJECTIVES: dict[str, Objective] = {}


def register(obj: Objective) -> Objective:
    OBJECTIVES[obj.name] = obj
    return obj


# Importing the modules populates the registry.
from . import cruise_speed, endurance, energy_per_km, max_speed, range  # noqa: E402,F401
