"""Parametric fuselage loft (MODEL_DETAILS section 7): frozen-fixture
continuity, loft/spec agreement, mass calibration, topology flip, symbolics."""

import aerosandbox as asb


def test_spec_fixture_bodies_frozen(sample_aircraft):
    """dv=None must keep returning the M1 baseline numbers forever."""
    bodies = sample_aircraft.parasite_bodies()
    assert [b["name"] for b in bodies] == ["pod", "boom"]
    pod = bodies[0]
    assert pod["wetted_area_m2"] == 0.183
    assert pod["form_factor"] == 1.25
    assert pod["volume_m3"] == 0.00263


def test_default_loft_reproduces_spec_pod(sample_aircraft):
    """Defaults anchor the loft on the spec pod: nose tip at station 0,
    length 585 mm, and a fineness form factor matching the frozen 1.25."""
    p = sample_aircraft.pod_dims(sample_aircraft.DV_DEFAULTS)
    assert abs(p["nose_tip"]) < 1e-12
    assert abs(p["length"] - 0.585) < 1e-12
    assert abs(p["w"] - 0.068) < 1e-12 and abs(p["h"] - 0.088) < 1e-12

    bodies = sample_aircraft.parasite_bodies(dict(sample_aircraft.DV_DEFAULTS))
    pod = bodies[0]
    assert abs(pod["form_factor"] - 1.25) < 0.01
    # loft integrals: tapered ends make Swet < the prism's 0.183, volume near
    # the frozen shape-fill estimate
    assert 0.12 < pod["wetted_area_m2"] < 0.16
    assert 0.002 < pod["volume_m3"] < 0.003


def test_pod_mass_calibrated_to_frozen(sample_aircraft):
    """k_skin x Swet + overhead reproduces the frozen 250 g at the spec loft."""
    extras = sample_aircraft.structure_extras(dict(sample_aircraft.DV_DEFAULTS))
    pod = next(e for e in extras if e.name == "pod")
    assert abs(pod.mass_kg - 0.250) < 0.015
    names = {e.name for e in extras}
    assert "boom" in names and "tail_stiffener" not in names


def test_integrated_topology_flip(sample_aircraft):
    """Integrated: cone runs to the tail block (length from tail_arm), printed
    cone + stiffener replace the boom, single parasite body."""
    sample_aircraft.fuselage_topology = "integrated"
    try:
        d = dict(sample_aircraft.DV_DEFAULTS)
        p = sample_aircraft.pod_dims(d)
        x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
        assert abs(p["tail_len"] - (x_tail - 0.410)) < 1e-12
        extras = sample_aircraft.structure_extras(d)
        names = {e.name for e in extras}
        assert "tail_stiffener" in names and "boom" not in names
        assert [b["name"] for b in sample_aircraft.parasite_bodies(d)] == ["pod"]
    finally:
        sample_aircraft.fuselage_topology = "pod_boom"


def test_boom_emerges_from_geometry(sample_aircraft):
    """Boom length is an outcome: pod tail cap -> tail block, mass and drag
    both derived from it (no hardcoded stations)."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    p = sample_aircraft.pod_dims(d)
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    pod_end = p["bay_end"] + p["tail_len"]
    boom = next(e for e in sample_aircraft.structure_extras(d) if e.name == "boom")
    assert abs(boom.mass_kg - 0.056 * ((x_tail - pod_end) + 0.05)) < 1e-9
    bb = next(b for b in sample_aircraft.parasite_bodies(d) if b["name"] == "boom")
    assert abs(bb["length_m"] - (x_tail - pod_end)) < 1e-9
    # longer tail arm -> longer boom, more drag area
    d2 = d | {"tail_arm": 1.0}
    bb2 = next(b for b in sample_aircraft.parasite_bodies(d2) if b["name"] == "boom")
    assert bb2["wetted_area_m2"] > bb["wetted_area_m2"]


def test_loft_symbolic_safe(sample_aircraft):
    """Opti variables flow through pod_dims/loft/body_dict without branching."""
    opti = asb.Opti()
    dv = dict(sample_aircraft.DV_DEFAULTS)
    for k in ("pod_nose", "pod_bay", "pod_tail", "pod_xs"):
        dv[k] = opti.variable(init_guess=dv[k])
    bodies = sample_aircraft.parasite_bodies(dv)
    assert not isinstance(bodies[0]["wetted_area_m2"], float)  # stayed symbolic
    lofts = sample_aircraft.fuselage_lofts(dv)
    assert len(lofts) == 1 and isinstance(lofts[0], asb.Fuselage)
