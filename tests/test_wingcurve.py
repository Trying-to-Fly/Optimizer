"""Wing dihedral curve (arch v3, MODEL_DETAILS section 9): one smooth family
delta(eta) = dihedral_tip * eta^d_exp replaces the per-panel d0-d3; straight
spars must fit inside the curved wing (sag constraint)."""

import math

import numpy as np


def test_spec_fixture_wing_frozen(sample_aircraft):
    """dv=None keeps the v1.2 spec panels: flat 700 mm center, 3 deg outer."""
    wing = sample_aircraft.geometry(None).wings[0]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    ys = [float(x.xyz_le[1]) for x in wing.xsecs]
    assert abs(zs[1]) < 1e-12 and abs(ys[1] - 0.350) < 1e-12  # flat center
    outer = (1.8 / 2 - 0.35) / 3
    assert abs(zs[4] - 3 * outer * math.sin(math.radians(3))) < 1e-9


def test_curve_exponent_zero_is_simple_dihedral(sample_aircraft):
    """d_exp = 0: one uniform angle root to tip — z rises linearly along the
    arc and the tip reaches semi * sin(delta)."""
    dv = {"dihedral_tip": 5.0, "d_exp": 0.0}
    wing = sample_aircraft.geometry(dv).wings[0]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    semi = 1.8 / 2
    assert abs(zs[4] - semi * math.sin(math.radians(5.0))) < 1e-9
    # every panel at the same angle: z increments proportional to widths
    widths = [0.35] + [(semi - 0.35) / 3] * 3
    for k in range(4):
        assert abs((zs[k + 1] - zs[k]) - widths[k] * math.sin(math.radians(5.0))) < 1e-9


def test_curve_exponent_builds_curvature_outboard(sample_aircraft):
    """d_exp > 0: flat at the root, local angle growing to the tip (the fully
    curved wing) — sampled angles strictly increase panel to panel."""
    d = dict(sample_aircraft.DV_DEFAULTS) | {"dihedral_tip": 12.0, "d_exp": 2.0}
    panels = sample_aircraft._wing_panels(d)
    angles = [float(a) for _, a in panels]
    assert all(angles[i] < angles[i + 1] for i in range(3))
    assert angles[0] < 1.0  # near-flat center (saddle region)
    assert angles[3] < 12.0  # tip PANEL midpoint stays below the tip value


def test_retired_polyhedral_variables(sample_aircraft):
    """d0-d3 are gone from the design vector; the curve pair replaced them."""
    import aerosandbox as asb

    opti = asb.Opti()
    dv = sample_aircraft.design_variables(opti)
    assert {"dihedral_tip", "d_exp"} <= set(dv)
    assert not any(k in dv for k in ("d0", "d1", "d2", "d3"))


def test_spar_sag_zero_for_simple_dihedral(sample_aircraft):
    """Analytic curve height is linear in eta at d_exp = 0 -> zero sag: a
    simple dihedral wing always passes a straight spar."""
    d = dict(sample_aircraft.DV_DEFAULTS) | {"dihedral_tip": 8.0, "d_exp": 0.0}
    z = lambda eta: float(sample_aircraft._wing_curve_z(d, eta))
    sag_mid = (z(0.0) + z(0.8)) / 2 - z(0.4)
    assert abs(sag_mid) < 1e-12
    # curved case: convex -> positive sag that grows with the exponent
    d2 = d | {"d_exp": 2.0}
    z2 = lambda eta: float(sample_aircraft._wing_curve_z(d2, eta))
    sag2 = (z2(0.4) + z2(0.9)) / 2 - z2(0.65)
    assert sag2 > 1e-4


def test_curve_geometry_matches_panel_samples(sample_aircraft):
    """geometry() places panels from the same _wing_panels sampling (shared
    helper — geometry and constraints cannot drift apart)."""
    dv = {"dihedral_tip": 10.0, "d_exp": 1.5}
    d = dict(sample_aircraft.DV_DEFAULTS) | dv
    wing = sample_aircraft.geometry(dv).wings[0]
    ys = [float(x.xyz_le[1]) for x in wing.xsecs]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    y, z = 0.0, 0.0
    for k, (w, delta) in enumerate(sample_aircraft._wing_panels(d)):
        y += w * math.cos(math.radians(float(delta)))
        z += w * math.sin(math.radians(float(delta)))
        assert abs(ys[k + 1] - y) < 1e-9
        assert abs(zs[k + 1] - z) < 1e-9
