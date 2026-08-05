"""Wing architecture v4 (MODEL_DETAILS section 9).

Planform is one smooth superellipse chord curve with a chosen LE convention
(9.1); dihedral is either the v3 smooth curve (9.2) or a two-panel polyhedral
with a free break station (9.3), the two priced against each other by a study.

The properties worth pinning are the ones a future reparameterization could
silently break: that the named planforms are EXACT members rather than
approximations, that the spec fixture never moves, and that geometry and
constraints keep reading the same shared panel list.
"""

import math

import pytest

from planeopt import geometry as geom


def test_spec_fixture_wing_frozen(sample_aircraft):
    """dv=None keeps the v1.2 spec panels: flat 700 mm center, 3 deg outer.

    This fixture has now survived three reparameterizations (v2 panel ratios ->
    v3 dihedral curve -> v4 superellipse) and must keep reporting identical M1
    numbers through all of them.
    """
    wing = sample_aircraft.geometry(None).wings[0]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    ys = [float(x.xyz_le[1]) for x in wing.xsecs]
    assert abs(zs[1]) < 1e-12 and abs(ys[1] - 0.350) < 1e-12  # flat center
    outer = (1.8 / 2 - 0.35) / 3
    assert abs(zs[4] - 3 * outer * math.sin(math.radians(3))) < 1e-9
    # frozen planform: 220 -> 150 mm over five stations, straight LE
    assert [round(float(x.chord), 6) for x in wing.xsecs] == [
        0.22, 0.22, 0.196667, 0.173333, 0.15
    ]
    xs = [float(x.xyz_le[0]) for x in wing.xsecs]
    assert max(xs) - min(xs) < 1e-12  # straight LE, all at the wing station


# --- 9.1 planform: the named shapes must be exact ------------------------


def test_rectangular_wing_is_an_exact_member():
    """taper = 1 is a constant-chord wing at every fullness — the user's
    'a full straight wing must still be reachable' requirement, as an exact
    point of the continuous family rather than a separate discrete case."""
    etas = geom.station_grid(0.5)
    for fullness in (1.0, 2.0, 4.0):
        chords = geom.superellipse_chords(etas, 0.22, 1.0, fullness)
        assert all(abs(c - 0.22) < 1e-12 for c in chords)


def test_straight_taper_is_an_exact_member():
    """fullness = 1 reproduces a linear chord distribution exactly."""
    etas = geom.station_grid(0.5)
    chords = geom.superellipse_chords(etas, 0.22, 0.5, 1.0)
    for eta, c in zip(etas, chords):
        assert abs(c - 0.22 * (1 - 0.5 * eta)) < 1e-12


def test_fullness_two_is_a_true_ellipse():
    """fullness = 2, taper = 0 is the ellipse c = c_root sqrt(1 - eta^2)."""
    etas = geom.station_grid(0.5)
    chords = geom.superellipse_chords(etas, 0.22, 0.0, 2.0)
    for eta, c in zip(etas, chords):
        assert abs(c - 0.22 * math.sqrt(1 - eta**2)) < 1e-12


@pytest.mark.parametrize("shear,straight", [(0.0, "le"), (0.25, "quarter"), (1.0, "te")])
def test_le_shear_spans_the_three_conventions(shear, straight):
    """One variable reaches straight-LE, straight-quarter-chord and straight-TE
    exactly, so the optimizer chooses the convention instead of inheriting it."""
    etas = geom.station_grid(0.5)
    chords = geom.superellipse_chords(etas, 0.22, 0.5, 2.0)
    le = geom.le_offsets(chords, shear)
    lines = {
        "le": le,
        "quarter": [x + 0.25 * c for x, c in zip(le, chords)],
        "te": [x + c for x, c in zip(le, chords)],
    }
    assert max(lines[straight]) - min(lines[straight]) < 1e-12
    # and the other two genuinely are NOT straight (the variable does something)
    for other in set(lines) - {straight}:
        assert max(lines[other]) - min(lines[other]) > 1e-3


def test_chord_endpoints_have_no_fullness_sensitivity():
    """c(0) and c(1) are c_root and taper*c_root for every fullness.

    Evaluating them through the symbolic power would form 0^(1/a) and log(0),
    whose derivatives are NaN and would poison the whole Jacobian; the helper
    returns them analytically instead. This test is the guard on that.
    """
    etas = geom.station_grid(0.5)
    for fullness in (1.0, 1.7, 4.0):
        chords = geom.superellipse_chords(etas, 0.22, 0.6, fullness)
        assert chords[0] == 0.22
        assert abs(chords[-1] - 0.22 * 0.6) < 1e-15


def test_retired_planform_variables(sample_aircraft):
    """r1-r3 and center_width are gone; the curve pair plus le_shear replaced
    them, and the equal-thirds panel widths went with them."""
    import aerosandbox as asb

    opti = asb.Opti()
    dv = sample_aircraft.design_variables(opti)
    assert {"taper", "fullness", "le_shear"} <= set(dv)
    assert not any(k in dv for k in ("r1", "r2", "r3", "center_width"))


# --- 9.2 dihedral curve (incumbent form) ---------------------------------


def test_curve_exponent_zero_is_simple_dihedral(sample_aircraft):
    """d_exp = 0: one uniform angle root to tip — z rises linearly along the
    arc and the tip reaches semi * sin(delta)."""
    sample_aircraft.wing_dihedral_form = "curve"
    dv = {"dihedral_tip": 5.0, "d_exp": 0.0}
    wing = sample_aircraft.geometry(dv).wings[0]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    semi = 1.8 / 2
    assert abs(zs[-1] - semi * math.sin(math.radians(5.0))) < 1e-9
    w = sample_aircraft._wing(dict(sample_aircraft.DV_DEFAULTS) | dv)
    for k, width in enumerate(w["widths"]):
        assert abs((zs[k + 1] - zs[k]) - width * math.sin(math.radians(5.0))) < 1e-9


def test_curve_exponent_builds_curvature_outboard(sample_aircraft):
    """d_exp > 0: flat at the root, local angle growing to the tip (the fully
    curved wing) — sampled angles strictly increase panel to panel."""
    sample_aircraft.wing_dihedral_form = "curve"
    d = dict(sample_aircraft.DV_DEFAULTS) | {"dihedral_tip": 12.0, "d_exp": 2.0}
    angles = [float(a) for a in sample_aircraft._wing(d)["dihedrals"]]
    assert all(angles[i] < angles[i + 1] for i in range(len(angles) - 1))
    assert angles[0] < 1.0  # near-flat root (saddle region)
    assert angles[-1] < 12.0  # tip PANEL midpoint stays below the tip value


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


# --- 9.3 two-panel polyhedral (the priced alternative) -------------------


def test_polyhedral2_is_two_angles_with_the_break_on_a_station(sample_aircraft):
    """Exactly two distinct dihedrals, and the break lands ON a station — which
    is what lets the form avoid comparing against a design-variable value."""
    sample_aircraft.wing_dihedral_form = "polyhedral2"
    d = dict(sample_aircraft.DV_DEFAULTS) | {
        "eta_break": 0.7, "dihedral_inner": 0.0, "dihedral_outer": 55.0
    }
    w = sample_aircraft._wing(d)
    assert set(round(float(a), 9) for a in w["dihedrals"]) == {0.0, 55.0}
    assert any(abs(float(e) - 0.7) < 1e-12 for e in w["etas"])
    # flat inboard, rising only outboard of the break: a genuine polyhedral tip
    zs = [float(z) for z in w["zs"]]
    n_in = sample_aircraft.WING_STATIONS_INNER
    assert all(abs(z) < 1e-12 for z in zs[: n_in + 1])
    assert zs[-1] > 0.2


def test_polyhedral2_cant_costs_projected_span(sample_aircraft):
    """Panels place by ARC length, so canting the outer panel spends projected
    span — the quantity the manufacturing cap is written against."""
    sample_aircraft.wing_dihedral_form = "polyhedral2"
    base = dict(sample_aircraft.DV_DEFAULTS) | {
        "span": 2.0, "eta_break": 0.7, "dihedral_inner": 0.0, "dihedral_outer": 0.0
    }
    flat = sample_aircraft.geometry(base)
    canted = sample_aircraft.geometry(base | {"dihedral_outer": 55.0})
    assert abs(float(flat.b_ref) - 2.0) < 1e-9  # flat wing: projected == material
    assert float(canted.b_ref) < 1.80  # cant is paid for in front-view width
    # material span is unchanged — the wing did not get shorter, it folded up
    assert abs(float(canted.wings[0].span()) - 2.0) < 3e-3


def test_spar_runs_reproduce_the_spec_carry_through(sample_aircraft):
    """The default joint station must reproduce v3's center_width = 0.700.

    Regression guard with teeth: eta_break replaced center_width, and the spar
    mass is computed from it. A default that merely LOOKS reasonable (0.60)
    silently moved the frozen fixture's spar mass by 6 g — which moves AUW,
    which moves every M1 number the validation anchors are written against.
    """
    from planeopt import structures

    d = dict(sample_aircraft.DV_DEFAULTS)
    w = sample_aircraft._wing(d)
    inner = w["eta_break"] * w["semi"]
    assert abs(2 * inner - 0.700) < 1e-12  # carry-through span, root to root
    assert abs((w["semi"] - inner) - 0.550) < 1e-12  # outer run per side
    # and the mass that falls out of them matches the v3 formula exactly
    v3 = (
        structures.tube_mass(d["spar_od_center"], d["spar_wall_center"], 0.700)
        + 2 * structures.tube_mass(d["spar_od_outer"], d["spar_wall_outer"], 0.85 * 0.550)
        + 0.035
    )
    got = {m.name: m.mass_kg for m in sample_aircraft.structure_extras(None)}
    assert abs(got["wing_spars_joiners"] - v3) < 1e-12


def test_polyhedral2_pays_for_its_joiner(sample_aircraft):
    """The kink carries one spar joint per side. The study only prices the form
    honestly if that mass is charged — v3's curve deleted these deliberately."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    sample_aircraft.wing_dihedral_form = "curve"
    smooth = {m.name: m.mass_kg for m in sample_aircraft.structure_extras(d)}
    sample_aircraft.wing_dihedral_form = "polyhedral2"
    kinked = {m.name: m.mass_kg for m in sample_aircraft.structure_extras(d)}
    delta = kinked["wing_spars_joiners"] - smooth["wing_spars_joiners"]
    assert abs(delta - 2 * sample_aircraft.DIHEDRAL_JOINER_KG) < 1e-9


def test_dihedral_form_selects_its_own_variables(sample_aircraft):
    """Each form declares only the angles it uses — an unused variable would
    leave the NLP with a direction no constraint touches."""
    import aerosandbox as asb

    sample_aircraft.wing_dihedral_form = "curve"
    curve = set(sample_aircraft.design_variables(asb.Opti()))
    sample_aircraft.wing_dihedral_form = "polyhedral2"
    poly = set(sample_aircraft.design_variables(asb.Opti()))
    assert {"dihedral_tip", "d_exp"} <= curve
    assert not ({"dihedral_inner", "dihedral_outer"} & curve)
    assert {"dihedral_inner", "dihedral_outer"} <= poly
    assert not ({"dihedral_tip", "d_exp"} & poly)
    # the joint station belongs to the wing, not to either form
    assert "eta_break" in curve and "eta_break" in poly


def test_dihedral_form_is_a_priced_study(sample_aircraft):
    """Both forms are declared candidates, so a run prices the kink rather than
    assuming it — the same posture as tail type and fuselage topology."""
    assert sample_aircraft.discrete_options["wing_dihedral_form"] == ["curve", "polyhedral2"]


# --- shared-helper contract ---------------------------------------------


@pytest.mark.parametrize("form,dv", [
    ("curve", {"dihedral_tip": 10.0, "d_exp": 1.5}),
    ("polyhedral2", {"eta_break": 0.4, "dihedral_inner": 2.0, "dihedral_outer": 35.0}),
])
def test_geometry_matches_the_shared_panel_list(sample_aircraft, form, dv):
    """geometry() places panels from the same _wing() list the constraints read,
    so the two cannot drift apart (the v3 rule, still enforced in v4)."""
    sample_aircraft.wing_dihedral_form = form
    d = dict(sample_aircraft.DV_DEFAULTS) | dv
    wing = sample_aircraft.geometry(dv).wings[0]
    ys = [float(x.xyz_le[1]) for x in wing.xsecs]
    zs = [float(x.xyz_le[2]) for x in wing.xsecs]
    w = sample_aircraft._wing(d)
    y = z = 0.0
    for k, (width, delta) in enumerate(zip(w["widths"], w["dihedrals"])):
        y += float(width) * math.cos(math.radians(float(delta)))
        z += float(width) * math.sin(math.radians(float(delta)))
        assert abs(ys[k + 1] - y) < 1e-9
        assert abs(zs[k + 1] - z) < 1e-9


def test_station_count_is_unchanged_from_v3(sample_aircraft):
    """Stations are a fidelity knob that costs RAM: each becomes an asb section
    that LiftingLine subdivides again, and a solve already peaks near 14.5 GB.
    v4 buys its smooth planform without growing the graph."""
    for form in ("curve", "polyhedral2"):
        sample_aircraft.wing_dihedral_form = form
        assert len(sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS).wings[0].xsecs) == 5


def test_mac_and_ac_exact_for_a_rectangular_wing():
    """Closed form on a shape with a known answer: a rectangular unswept wing
    has MAC = chord and its quarter-chord AC at 0.25 c behind the root LE."""
    widths, chords, le = [0.5, 0.5], [0.2, 0.2, 0.2], [0.0, 0.0, 0.0]
    mac, x_ac = geom.mac_and_ac(widths, chords, le)
    assert abs(mac - 0.2) < 1e-12
    assert abs(x_ac - 0.05) < 1e-12


def test_le_shear_moves_the_aerodynamic_centre():
    """The reason the AC had to stop being 0.25*c_mean behind the root LE: with
    the same chords, sweeping the planform moves the AC aft by a real amount."""
    etas = geom.station_grid(0.5)
    chords = geom.superellipse_chords(etas, 0.22, 0.5, 2.0)
    widths = [(etas[k + 1] - etas[k]) * 1.0 for k in range(len(etas) - 1)]
    _, ac_straight_le = geom.mac_and_ac(widths, chords, geom.le_offsets(chords, 0.0))
    _, ac_straight_te = geom.mac_and_ac(widths, chords, geom.le_offsets(chords, 1.0))
    assert ac_straight_te - ac_straight_le > 0.02  # tens of mm on a 220 mm root
