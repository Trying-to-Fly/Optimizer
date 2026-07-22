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
