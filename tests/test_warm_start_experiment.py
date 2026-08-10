"""The instrument for the seed question must survive answering it.

`tools/bughunt/warm_start_experiment.py` measures three configurations of the
champion seed. Its `bump_inits_only` arm used to build itself by stripping a key
that `_hot_start_kwargs` happened to send:

    kwargs |= solve._hot_start_kwargs(champion)
    kwargs.pop("warm_start")            # bare pop, no default

FINDINGS §35 then stopped `_hot_start_kwargs` sending that key, and the bare pop
became a `KeyError`. So the experiment that prices the seed was broken BY a
change to the seed — exactly when it was needed, and silently, because nothing
under `tools/` was covered. `test_price_caps.py` is the precedent for fixing
that by testing the tool rather than the intention.

What this pins is the arm CONTRACT, not the physics: each arm must ask for the
configuration it claims to measure, and everything it asks for must be something
`_solve_nlp` will accept. A solve is minutes and ~15 GB; this is milliseconds,
which is the point.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

from planeopt import solve

TOOL = Path(__file__).resolve().parents[1] / "tools/bughunt/warm_start_experiment.py"


@pytest.fixture(scope="module")
def experiment():
    spec = importlib.util.spec_from_file_location("warm_start_experiment", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHAMPION = {"dv": {"span": 2.0, "c_root": 0.275}, "V_ms": 9.5, "rpm": 3600.0}


def test_every_arm_builds_without_reaching_into_hot_start_kwargs_shape(experiment):
    """The regression itself: no arm may depend on a key `_hot_start_kwargs`
    merely happens to emit today."""
    for arm in experiment.ARMS:
        champion = CHAMPION if arm.startswith("bump_inits") else None
        experiment.arm_kwargs(arm, champion)  # must not raise


@pytest.mark.parametrize(
    "arm, seeded, options",
    [
        ("champion", False, None),
        ("bump_cold", False, None),
        ("bump_inits_only", True, False),
        ("bump_inits_and_options", True, True),
    ],
)
def test_each_arm_asks_for_the_configuration_it_names(experiment, arm, seeded, options):
    """Three configurations, and the ranking between them is the open question
    §35 left. An arm that quietly measures a different one answers it wrongly."""
    champion = CHAMPION if seeded else None
    kwargs = experiment.arm_kwargs(arm, champion)

    assert ("inits" in kwargs) is seeded
    assert kwargs.get("warm_start") is options
    # `champion` is the seed SOURCE and must carry no bump; the other three are
    # +20 g, which is what makes them comparable to each other.
    assert ("extra_mass_kg" in kwargs) is (arm != "champion")


def test_no_arm_can_send_a_kwarg_solve_nlp_would_reject(experiment):
    """A stray kwarg is a TypeError minutes into a ~15 GB solve, and the arms
    are run unattended by `run_warm_start_experiment.sh`."""
    accepted = set(inspect.signature(solve._solve_nlp).parameters)
    for arm in experiment.ARMS:
        champion = CHAMPION if arm.startswith("bump_inits") else None
        assert set(experiment.arm_kwargs(arm, champion)) <= accepted


def test_the_two_warm_arms_differ_in_exactly_the_thing_under_test(experiment):
    """If they differed in the seed as well, the experiment could not attribute
    its result to the options — which is the whole comparison."""
    only = experiment.arm_kwargs("bump_inits_only", CHAMPION)
    both = experiment.arm_kwargs("bump_inits_and_options", CHAMPION)

    assert only["inits"] == both["inits"]
    assert only["extra_mass_kg"] == both["extra_mass_kg"]
    assert {k: v for k, v in only.items() if k != "warm_start"} == {
        k: v for k, v in both.items() if k != "warm_start"
    }
    assert only["warm_start"] is False and both["warm_start"] is True
