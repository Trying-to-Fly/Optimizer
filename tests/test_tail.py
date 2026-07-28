"""Tail phase (MODEL_DETAILS section 8): per-dimension tail variables, three
declared types, mass mapping, v-tail-volume floor math, throw policy, symbolics."""

import math

import aerosandbox as asb
import numpy as np
import pytest


def test_spec_fixture_tail_frozen(sample_aircraft):
    """dv=None keeps the v1.2 spec V-tail exactly (validation continuity)."""
    airplane = sample_aircraft.geometry(None)
    assert [w.name for w in airplane.wings] == ["wing", "vtail"]
    vt = airplane.wings[1]
    assert abs(vt.xsecs[0].chord - 0.150) < 1e-12
    assert abs(vt.xsecs[1].chord - 0.110) < 1e-12
    dy = vt.xsecs[1].xyz_le[1] - vt.xsecs[0].xyz_le[1]
    dz = vt.xsecs[1].xyz_le[2] - vt.xsecs[0].xyz_le[2]
    assert abs(np.hypot(dy, dz) - 0.320) < 1e-12
    assert abs(np.degrees(np.arctan2(dz, dy)) - 38.0) < 1e-9
    cs = vt.xsecs[0].control_surfaces[0]
    assert cs.name == "ruddervator" and abs(cs.hinge_point - 0.73) < 1e-12


def test_parametric_vtail_defaults_match_spec_panel(sample_aircraft):
    """Per-dimension defaults reproduce the spec panel (chords, arc, V-angle,
    sweep) — only the root LE moves (AC placement now includes sweep)."""
    airplane = sample_aircraft.geometry({})
    vt = next(w for w in airplane.wings if w.name == "vtail")
    r, t = vt.xsecs
    assert abs(r.chord - 0.150) < 1e-12 and abs(t.chord - 0.110) < 1e-9
    dy, dz = t.xyz_le[1] - r.xyz_le[1], t.xyz_le[2] - r.xyz_le[2]
    assert abs(np.hypot(dy, dz) - 0.320) < 1e-9
    assert abs(np.degrees(np.arctan2(dz, dy)) - 38.0) < 1e-9
    assert abs((t.xyz_le[0] - r.xyz_le[0]) - 0.320 * np.tan(np.radians(7.125))) < 1e-6
    cs = r.control_surfaces[0]
    assert cs.name == "ruddervator" and abs(cs.hinge_point - 0.73) < 1e-9


def test_tail_ac_sits_at_tail_arm(sample_aircraft):
    """AC placement: root LE + sweep offset + 0.25 MAC = wing AC + tail_arm,
    so sweep cannot buy free moment arm.

    The wing reference is its TRUE area-weighted quarter-chord AC (v4): with a
    sheared planform the AC no longer sits 0.25 c_mean behind the root LE, and
    the old proxy would have handed the tail tens of millimetres of unpaid arm.
    """
    from planeopt import geometry as geom

    d = dict(sample_aircraft.DV_DEFAULTS) | {"t_sweep": 20.0}
    airplane = sample_aircraft.geometry(d)
    vt = airplane.wings[1]
    w = sample_aircraft._wing(d)
    _, x_ac_local = geom.mac_and_ac(w["widths"], w["chords"], w["le_x"])
    ac_expected = 0.390 + x_ac_local + d["tail_arm"]
    lam = d["t_taper"]
    semi = d["t_span"] / 2
    mac = (2 / 3) * d["t_c_root"] * (1 + lam + lam**2) / (1 + lam)
    s_mac = semi * (1 + 2 * lam) / (3 * (1 + lam))
    ac_actual = (
        float(vt.xsecs[0].xyz_le[0])
        + s_mac * math.tan(math.radians(d["t_sweep"]))
        + 0.25 * mac
    )
    assert abs(ac_actual - ac_expected) < 1e-9


@pytest.mark.parametrize("tail_type,names,control", [
    ("vtail", ["wing", "vtail", "winglet"], "ruddervator"),
    ("conventional", ["wing", "hstab", "fin", "winglet"], "elevator"),
    ("ttail", ["wing", "hstab", "fin", "winglet"], "elevator"),
])
def test_tail_type_geometry_contract(sample_aircraft, tail_type, names, control):
    """Each declared type produces its surface set, pitch-control name, and
    construction-profile coverage (massmodel maps by wing name)."""
    sample_aircraft.tail_type = tail_type
    try:
        assert sample_aircraft.pitch_control_name == control
        airplane = sample_aircraft.geometry({})
        assert [w.name for w in airplane.wings] == names
        profiles = sample_aircraft.construction()
        for w in airplane.wings:
            assert w.name in profiles, f"no construction profile for {w.name}"
        # the pitch surface exists and hinge follows cs_frac
        tail = airplane.wings[1]
        cs = tail.xsecs[0].control_surfaces[0]
        assert cs.name == control
        assert abs(cs.hinge_point - (1 - sample_aircraft.DV_DEFAULTS["cs_frac"])) < 1e-9
    finally:
        sample_aircraft.tail_type = "vtail"


def test_ttail_geometry_and_mount_mass(sample_aircraft):
    """T-tail: hstab rides at the fin tip height; declared mount mass appears
    (and only for the T-tail)."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    sample_aircraft.tail_type = "ttail"
    try:
        airplane = sample_aircraft.geometry(d)
        hstab = next(w for w in airplane.wings if w.name == "hstab")
        assert abs(float(hstab.xsecs[0].xyz_le[2]) - d["fin_height"]) < 1e-9
        extras = sample_aircraft.structure_extras(d)
        mount = next(e for e in extras if e.name == "ttail_fin_mount")
        assert abs(mount.mass_kg - sample_aircraft.TTAIL_FIN_MOUNT_KG) < 1e-12
    finally:
        sample_aircraft.tail_type = "vtail"
    extras = sample_aircraft.structure_extras(d)
    assert not any(e.name == "ttail_fin_mount" for e in extras)


def test_conventional_mass_mapping(sample_aircraft):
    """massmodel builds printed_hstab + printed_fin with their own profiles;
    fin mass uses its height as span (front-view arc length)."""
    from planeopt import massmodel

    sample_aircraft.tail_type = "conventional"
    try:
        airplane = sample_aircraft.geometry({})
        comps, breakdown = massmodel.build(sample_aircraft, airplane, {})
        names = {c.name for c in comps}
        assert {"printed_hstab", "printed_fin"} <= names
        assert "printed_vtail" not in names
        assert breakdown["fin"]["profile"] == "lwpla_a1_fin"
        fin_mass = next(c.mass_kg for c in comps if c.name == "printed_fin")
        assert 0.01 < fin_mass < 0.15
    finally:
        sample_aircraft.tail_type = "vtail"


def test_vertical_tail_volume_spec_value(sample_aircraft):
    """The declared floor (0.030) sits just under the spec design's own
    Vv = S_tail sin^2(38 deg) * l_v / (S b) ~ 0.034 — the floor value's
    provenance, kept as a regression check."""
    d = sample_aircraft.DV_DEFAULTS
    s_tail = d["t_span"] * d["t_c_root"] * (1 + d["t_taper"]) / 2
    s_v = s_tail * math.sin(math.radians(d["t_dihedral"])) ** 2
    vv = s_v * d["tail_arm"] / (0.357 * 1.8)
    assert abs(vv - 0.0343) < 0.001
    assert sample_aircraft.v_tail_volume_min <= vv


def test_throw_policy_limit(sample_aircraft):
    """Degree cap = (1/3 throw) / control chord: spec defaults ~6.5 deg; a
    bigger hinge fraction tightens the cap (real trade, not a free knob)."""
    lim = sample_aircraft.trim_deflection_limit_deg(None)
    c_cs = 0.27 * 0.150 * (1 + 110 / 150) / 2
    assert abs(lim - math.degrees(0.004 / c_cs)) < 1e-9
    lim_big = sample_aircraft.trim_deflection_limit_deg({"cs_frac": 0.40})
    assert lim_big < lim


def test_tail_symbolic_safe_all_types(sample_aircraft):
    """Opti variables flow through design_variables -> geometry ->
    geometry_constraints for every declared tail type (no value branching)."""
    for tail_type in sample_aircraft.discrete_options["tail_type"]:
        sample_aircraft.tail_type = tail_type
        try:
            opti = asb.Opti()
            dv = sample_aircraft.design_variables(opti)
            expected = {"t_span", "t_c_root", "t_taper", "t_sweep", "cs_frac"}
            if tail_type == "vtail":
                expected |= {"t_dihedral"}
                assert "fin_height" not in dv
            else:
                expected |= {"fin_height", "fin_c_root", "fin_taper", "fin_sweep"}
                assert "t_dihedral" not in dv
            assert expected <= set(dv)
            assert "tail_scale" not in dv  # retired
            airplane = sample_aircraft.geometry(dv)
            assert len(airplane.wings) == (3 if tail_type == "vtail" else 4)
            V = opti.variable(init_guess=11.0)
            defl = opti.variable(init_guess=0.0)
            sample_aircraft.geometry_constraints(opti, dv, V, deflection_deg=defl)
        finally:
            sample_aircraft.tail_type = "vtail"


@pytest.mark.parametrize("tail_type", ["conventional", "ttail"])
def test_tail_trim_converges(sample_aircraft, sample_mission, tail_type):
    """Numeric LL trim with hstab + vertical fin present (junction sanity —
    first execution of LL over a pure vertical surface in this project)."""
    from planeopt import aero, massmodel

    sample_aircraft.tail_type = tail_type
    try:
        airplane = sample_aircraft.geometry({})
        comps, _ = massmodel.build(sample_aircraft, airplane, {})
        totals = massmodel.totals(comps)
        t = aero.trim(
            airplane, 11.0, totals["auw_kg"] * 9.81, totals["x_cg_m"],
            sample_aircraft.parasite_bodies(),
            control_name=sample_aircraft.pitch_control_name,
        )
        assert 0.2 < t["CL"] < 1.2
        assert t["L_over_D"] > 5.0
    finally:
        sample_aircraft.tail_type = "vtail"
