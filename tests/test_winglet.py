"""Winglet + span-cap architecture (v1.3): geometry contract, cap math, mass."""

import numpy as np


def test_spec_fixture_has_no_winglet(sample_aircraft):
    """dv=None must still reproduce the v1.2 spec plane exactly — no winglet."""
    airplane = sample_aircraft.geometry(None)
    assert len(airplane.wings) == 2
    assert [w.name for w in airplane.wings] == ["wing", "vtail"]


def test_parametric_geometry_grows_winglet(sample_aircraft):
    airplane = sample_aircraft.geometry({})
    names = [w.name for w in airplane.wings]
    assert names == ["wing", "vtail", "winglet"]
    wl = airplane.wings[2]
    # defaults: 120 mm at 75 deg cant, root chord = 0.8 x wing tip chord
    r0, r1 = wl.xsecs[0], wl.xsecs[-1]
    dy = r1.xyz_le[1] - r0.xyz_le[1]
    dz = r1.xyz_le[2] - r0.xyz_le[2]
    assert abs(np.hypot(dy, dz) - 0.12) < 1e-9
    assert abs(np.degrees(np.arctan2(dz, dy)) - 75.0) < 1e-6
    assert abs(r0.chord - 0.8 * airplane.wings[0].xsecs[-1].chord) < 1e-9
    # winglet root sits at the wing tip LE position
    tip = airplane.wings[0].xsecs[-1]
    assert abs(r0.xyz_le[1] - tip.xyz_le[1]) < 1e-9
    assert abs(r0.xyz_le[2] - tip.xyz_le[2]) < 1e-9


def test_projected_span_cap_math(sample_aircraft):
    """b_ref is projected (front-view) span: sum of panel widths x cos(local
    dihedral), sampled from the v3 curve at panel midpoints."""
    dv = {"span": 2.2, "center_width": 0.8, "dihedral_tip": 15.0, "d_exp": 1.0}
    airplane = sample_aircraft.geometry(dv)
    cw2 = 0.4
    w3 = (2.2 / 2 - cw2) / 3
    semi, s = 0.0, 0.0
    for w in (cw2, w3, w3, w3):
        eta = (s + w / 2) / 1.1
        semi += w * np.cos(np.radians(15.0 * eta))
        s += w
    assert abs(float(airplane.b_ref) - 2 * semi) < 1e-9
    # material span is unchanged by dihedral (mm-level: span() follows the
    # quarter-chord line, which twist shifts slightly)
    assert abs(float(airplane.wings[0].span()) - 2.2) < 2e-3


def test_winglet_mass_accounting(sample_aircraft):
    from planeopt import massmodel

    airplane = sample_aircraft.geometry({})
    comps, breakdown = massmodel.build(sample_aircraft, airplane, {})
    names = {c.name for c in comps}
    assert "printed_winglet" in names
    assert "winglet_joiners" in names
    assert "winglet" in breakdown
    # small surface: printed pair well under the wing's mass
    wl = next(c.mass_kg for c in comps if c.name == "printed_winglet")
    wing = next(c.mass_kg for c in comps if c.name == "printed_wing")
    assert 0.005 < wl < 0.10 < wing


def test_winglet_off_toggle(sample_aircraft):
    """The on/off study path: disabling the attr removes surface, dv keys, mass."""
    sample_aircraft.winglet = False
    try:
        airplane = sample_aircraft.geometry({})
        assert [w.name for w in airplane.wings] == ["wing", "vtail"]
        from planeopt import massmodel

        comps, _ = massmodel.build(sample_aircraft, airplane, {})
        assert not any("winglet" in c.name for c in comps)
    finally:
        sample_aircraft.winglet = True


def test_winglet_trim_converges(sample_aircraft, sample_mission):
    """Numeric LL trim with the winglet surface present (junction sanity)."""
    from planeopt import aero, massmodel

    airplane = sample_aircraft.geometry({})
    comps, _ = massmodel.build(sample_aircraft, airplane, {})
    totals = massmodel.totals(comps)
    t = aero.trim(
        airplane, 11.0, totals["auw_kg"] * 9.81, totals["x_cg_m"],
        sample_aircraft.parasite_bodies(),
    )
    assert 0.2 < t["CL"] < 1.2
    assert t["L_over_D"] > 5.0
