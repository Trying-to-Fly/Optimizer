"""Parametric fuselage loft (MODEL_DETAILS section 7): frozen-fixture
continuity, loft/spec agreement, mass calibration, topology flip, symbolics."""

import aerosandbox as asb
import pytest


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

    # the frozen 1.25 is a spec-pusher number (no slipstream scrub) — pin the
    # mount so the loft-FF calibration identity stays mount-independent
    sample_aircraft.motor_mount = "pusher"
    try:
        bodies = sample_aircraft.parasite_bodies(dict(sample_aircraft.DV_DEFAULTS))
    finally:
        sample_aircraft.motor_mount = "puller"
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


def test_pod_top_meets_wing_root(sample_aircraft):
    """Saddle rule: the pod top must embed into the wing root plane (z = 0)
    regardless of pod height — a shrunken pod can't leave the wing floating."""
    for xs in (1.0, 0.794, 1.3):
        d = dict(sample_aircraft.DV_DEFAULTS) | {"pod_xs": xs}
        loft = sample_aircraft.fuselage_lofts(d)[0]
        h = sample_aircraft.POD_XS_SPEC[1] * xs
        top = float(loft.xsecs[8].xyz_c[2]) + h / 2  # bay-end section's top (full height)
        assert abs(top - sample_aircraft.SADDLE_EMBED) < 1e-9


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
    # sub-micron, not exact: the drag body's length carries the positivity guard
    # the NLP needs (geometry.smooth_floor), whose error at a 555 mm boom is
    # 0.45 um. The structural length above is unguarded and stays exact.
    assert abs(bb["length_m"] - (x_tail - pod_end)) < 1e-6
    # longer tail arm -> longer boom, more drag area
    d2 = d | {"tail_arm": 1.0}
    bb2 = next(b for b in sample_aircraft.parasite_bodies(d2) if b["name"] == "boom")
    assert bb2["wetted_area_m2"] > bb["wetted_area_m2"]


def test_the_boom_is_drawn_and_bridges_the_gap(sample_aircraft):
    """Long-standing cosmetic gap: the boom had no loft, so the three-view and
    the interactive model showed a pod and a tail with empty space between them.
    It must span exactly the gap it fills — anything else is a prettier lie."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    p = sample_aircraft.pod_dims(d)
    lofts = {loft.name: loft for loft in sample_aircraft.fuselage_lofts(d)}
    assert set(lofts) == {"pod", "boom"}

    xs = [float(x.xyz_c[0]) for x in lofts["boom"].xsecs]
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    assert min(xs) == pytest.approx(p["bay_end"] + p["tail_len"])  # pod tail cap
    assert max(xs) == pytest.approx(x_tail)                        # tail block


def test_drawing_the_boom_does_not_change_any_drag(sample_aircraft):
    """The loft is viz only. Boom drag comes from `boom_body` and pod drag from
    the pod loft, so a body added for drawing must not reach the buildup —
    `parasite_bodies` takes the pod from `_pod_loft`, never by indexing the
    drawable list."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    bodies = {b["name"]: b for b in sample_aircraft.parasite_bodies(d)}
    assert set(bodies) == {"pod", "boom"}
    # the pod body is the pod loft's own integral, not the first drawable
    pod_loft = sample_aircraft._pod_loft(d)
    assert float(bodies["pod"]["wetted_area_m2"]) == pytest.approx(
        float(pod_loft.area_wetted())
    )
    # and the boom's drag length is still the exposed span, not the drawn one
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    p = sample_aircraft.pod_dims(d)
    assert float(bodies["boom"]["length_m"]) == pytest.approx(
        x_tail - (p["bay_end"] + p["tail_len"]), abs=1e-6
    )


def test_the_integrated_topology_draws_no_boom(sample_aircraft):
    """There is no boom to draw when the tail cone runs to the tail block."""
    original = sample_aircraft.fuselage_topology
    sample_aircraft.fuselage_topology = "integrated"
    try:
        names = {l.name for l in sample_aircraft.fuselage_lofts(dict(sample_aircraft.DV_DEFAULTS))}
    finally:
        sample_aircraft.fuselage_topology = original
    assert names == {"pod"}


def test_boom_drag_stays_finite_on_an_infeasible_iterate():
    """The exposed boom length is a DIFFERENCE of design variables, kept
    positive only by the aircraft's clearance constraint — and an interior-point
    method reaches its solution through points that violate that constraint. A
    negative length used to make `(-Re)**0.2` NaN inside the drag build-up, and
    one NaN in a constraint row fails the SOLVE rather than the point (HANDOFF
    issue 3: 52 such warnings, all inside the pusher solve).
    """
    import numpy as np

    from planeopt import aero, fuselage

    for exposed in (-0.30, -1e-6, 0.0):
        b = fuselage.boom_body(exposed)
        assert b["length_m"] > 0
        assert b["wetted_area_m2"] > 0 and b["volume_m3"] > 0
        assert np.isfinite(aero.body_cd0([b], 11.0, 0.4))


def test_design_brief_renders(sample_aircraft):
    """CAD round-trip step (a): brief renders from declared data alone —
    framework must not need any aircraft-specific knowledge."""
    from planeopt import types
    from planeopt.report import brief

    result = types.RunResult(
        aircraft="x", mission="m", objective="endurance", status="s", created="t",
        performance={"optimization": {"champion": {
            "objective_value": 100.0, "V_ms": 10.0, "auw_kg": 1.9,
            "static_margin": 0.08, "dv": dict(sample_aircraft.DV_DEFAULTS),
        }, "shadow_price_obj_per_gram": -0.07}, "objective_units": "min"},
    )
    text = brief.render(result, sample_aircraft)
    assert "Cross-section" in text and "battery CG window" in text
    assert "Deviation prices" in text
    # graceful without the hook
    class Bare: ...
    assert "Design brief" in brief.render(result, Bare())


def test_loft_symbolic_safe(sample_aircraft):
    """Opti variables flow through pod_dims/loft/body_dict without branching."""
    opti = asb.Opti()
    dv = dict(sample_aircraft.DV_DEFAULTS)
    for k in ("pod_nose", "pod_bay", "pod_tail", "pod_xs"):
        dv[k] = opti.variable(init_guess=dv[k])
    bodies = sample_aircraft.parasite_bodies(dv)
    assert not isinstance(bodies[0]["wetted_area_m2"], float)  # stayed symbolic
    # pod AND boom now (the boom gained a loft 2026-07-30); both must survive
    # symbolic dv, since the viz twin is built from the champion's design vector
    lofts = sample_aircraft.fuselage_lofts(dv)
    assert [l.name for l in lofts] == ["pod", "boom"]
    assert all(isinstance(l, asb.Fuselage) for l in lofts)
