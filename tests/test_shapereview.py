"""Shape review rules — calibrated so the app's own loft family passes and
the old boxy shapes fail. STEP loader is exercised only when the optional
CAD kernel is installed."""

import pytest

from planeopt import fuselage, shapereview


def _sections(loft):
    return [(float(xs.xyz_c[0]), float(xs.width), float(xs.height)) for xs in loft.xsecs]


def test_own_loft_at_floors_passes():
    """Floor-proportioned streamlined loft (nose 1.0 d_eq, tail 1.8 d_eq)
    must pass its own review — thresholds are self-consistent."""
    d_eq = (0.054 * 0.070) ** 0.5
    loft = fuselage.loft(1.0 * d_eq, 0.33, 1.8 * d_eq, 0.054, 0.070)
    r = shapereview.review(_sections(loft))
    assert r["ok"], r["findings"]


def test_boxy_pod_fails_nose():
    """The spec pod's 30 mm nose (the shape the user rejected) gets flagged."""
    loft = fuselage.loft(0.030, 0.380, 0.175, 0.068, 0.088)
    r = shapereview.review(_sections(loft))
    nose = next(f for f in r["findings"] if f["check"] == "nose_fineness")
    assert not nose["ok"]


def test_steep_boat_tail_fails():
    d_eq = (0.054 * 0.070) ** 0.5
    loft = fuselage.loft(1.2 * d_eq, 0.33, 0.6 * d_eq, 0.054, 0.070)  # stubby tail
    r = shapereview.review(_sections(loft))
    bt = next(f for f in r["findings"] if f["check"] == "boat_tail_half_angle")
    assert not bt["ok"]


def test_wetted_area_pricing():
    d_eq = (0.054 * 0.070) ** 0.5
    loft = fuselage.loft(1.0 * d_eq, 0.33, 1.8 * d_eq, 0.054, 0.070)
    r = shapereview.review(
        _sections(loft), swet_m2=0.110, reference_swet_m2=0.100,
        k_skin_kg_m2=1.465, shadow_per_g=-0.074, objective_units="min",
    )
    p = r["wetted_area_price"]
    assert abs(p["delta_swet_m2"] - 0.01) < 1e-9
    assert abs(p["delta_mass_g"] - 14.65) < 0.1
    assert "min" in p["cost_mass_route"]


def test_step_loader_roundtrip(tmp_path):
    """Full .STEP round-trip (needs the optional cad extra): export a box-ish
    solid, reload, check integrals within tolerance."""
    cq = pytest.importorskip("cadquery")
    from planeopt import cadimport

    p = tmp_path / "pod.step"
    cq.Workplane("YZ").ellipse(0.030, 0.040).extrude(0.5).val().exportStep(str(p))
    shape = cadimport.load_step(p)
    import math

    assert abs(shape.length_m - 0.5) < 1e-6
    assert abs(shape.volume_m3 - math.pi * 0.030 * 0.040 * 0.5) < 1e-5
    assert shape.swet_m2 > 0 and len(shape.sections) > 10
    bd = shape.body_dict()
    assert bd["form_factor"] > 1.0 and bd["wetted_area_m2"] == shape.swet_m2
