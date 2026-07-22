"""Shipped configs import cleanly and satisfy their contracts (M0 gate)."""

from planeopt.mission import OBJECTIVES
from planeopt.types import AircraftDefinition


def test_objective_library_complete():
    assert set(OBJECTIVES) == {
        "endurance", "range", "energy_per_km", "cruise_speed", "max_speed",
    }
    # No global wind rule: modes are per-objective (MODEL_DETAILS.md section 5.2)
    assert OBJECTIVES["endurance"].wind_mode == "constraint"
    assert OBJECTIVES["range"].wind_mode == "objective"
    assert OBJECTIVES["max_speed"].wind_mode == "none"


def test_sample_aircraft_contract(sample_aircraft):
    assert isinstance(sample_aircraft, AircraftDefinition)
    airplane = sample_aircraft.geometry(None)
    wing = airplane.wings[0]
    # DESIGN_SPEC.md numbers: span 1.8 m, area 35.7 dm2, AR 9.1
    assert abs(wing.span() - 1.8) < 0.01
    assert abs(wing.area() - 0.357) < 0.005
    assert abs(wing.aspect_ratio() - 9.1) < 0.15


def test_sample_mission(sample_mission):
    assert sample_mission.objective in OBJECTIVES
    assert abs(sample_mission.v_min_ms - 9.5) < 1e-9


def test_fixed_equipment_totals(sample_aircraft):
    from planeopt import massmodel

    totals = massmodel.totals(sample_aircraft.fixed_equipment())
    # spec: fixed equipment ~858 g
    assert abs(totals["auw_kg"] - 0.858) < 0.010
    assert 0.0 < totals["x_cg_m"] < 1.4
