from pathlib import Path

import pytest

from planeopt.cli import load_aircraft, load_mission

REPO = Path(__file__).parent.parent


@pytest.fixture()
def sample_aircraft():
    ac, _ = load_aircraft(REPO / "aircraft" / "vtail_sample")
    return ac


@pytest.fixture()
def sample_mission():
    ms, _ = load_mission(REPO / "missions" / "endurance_sample.py")
    return ms


@pytest.fixture()
def rcv2_aircraft():
    """`vtail_sample` carrying the RC v2 electronics manifest.

    A second aircraft matters to the test suite for a reason the first cannot
    serve: every guard here had only ever been evaluated on designs that PASS
    it. `vtail_rcv2` is nose-heavy enough to fail its control-throw limit at
    every speed in the sweep, which is what first exercised the airworthiness
    filters' reporting at all (FINDINGS §26, §28).
    """
    ac, _ = load_aircraft(REPO / "aircraft" / "vtail_rcv2")
    return ac
