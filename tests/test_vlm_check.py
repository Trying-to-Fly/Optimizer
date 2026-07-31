"""The winglet study's VLM second opinion (HANDOFF issue 0a, 2026-07-31).

`aero.vlm_induced_check` shipped a physically impossible number in every run it
ever ran in: on the 2026-07-31 champion it reported `k_induced = -0.50`, i.e. an
INVISCID wing whose drag falls as CL^2 rises, with `CD = -0.54` in the raw sweep.
The cause was the VLM mesh, not the fit — AeroSandbox's default spanwise spacing
(cosspace, applied within each wing section) bunches panels against every section
boundary, and on a wing with unequally wide sections that leaves near-coincident
horseshoes, a near-singular AIC, and a garbage circulation. The tell was that the
answer swung with resolution: CL +0.63 at 8 chordwise panels, +285 at 16.

These tests pin the two properties that make the number worth reading at all:
it must be PHYSICAL (an inviscid polar has CD > 0 rising with CL^2) and it must
be MESH-INDEPENDENT — and when it is neither, it must say so rather than ship.
"""

import numpy as np
import pytest

from planeopt import aero

#: The 2026-07-31 chord275 champion's winglet-on design vector — the geometry
#: the defect was found on, and the one a regression has to be checked against.
#: (`run.json` of runs/20260731T152208-…-vtail_sample_v1-6_chord275, winglet-on
#: solve.) Only wing-shaping entries matter here; the rest fill from defaults.
CHAMPION_DV = {
    "span": 2.0, "c_root": 0.25334, "taper": 0.55254, "fullness": 1.31855,
    "le_shear": 1.0, "eta_break": 0.30954, "washout_tip": 0.0,
    "dihedral_tip": 4.65222, "d_exp": 0.0,
    "t_span": 0.44415, "t_c_root": 0.09523, "t_taper": 0.95990,
    "t_sweep": 0.98520, "t_dihedral": 55.0, "cs_frac": 0.40,
    "wl_len": 0.06510, "wl_cant": 87.09895, "wl_cr": 0.66667,
    "wl_taper": 1.0, "wl_toe": -2.69365,
}
CHAMPION_V = 9.5


@pytest.mark.slow  # ~70 s of real VLM solves; no NLP, no large memory footprint
def test_champion_geometry_reproduces_the_defect_fixed(sample_aircraft):
    """The exact case that reported k = -0.50, end to end through production.

    Everything the shipped number has to satisfy, asserted on the geometry it
    was wrong on: physical polars, an ensemble that agrees, and a winglet that
    makes induced drag BETTER rather than worse (the 2026-07-31 run reported
    the winglet raising k, which is how wrong the answer was).
    """
    on = sample_aircraft.geometry(CHAMPION_DV)
    sample_aircraft.winglet = False
    try:
        off = sample_aircraft.geometry(CHAMPION_DV)
    finally:
        sample_aircraft.winglet = True
    res = aero.vlm_induced_check({"on": on, "off": off}, CHAMPION_V)

    for label, r in res.items():
        assert r["reliable"], (label, r.get("unreliable_reason"))
        assert r["k_induced"] > 0, "inviscid CD cannot fall as CL^2 rises"
        assert len(r["meshes_in_consensus"]) >= aero.VLM_MIN_CONSENSUS
        for m in r["per_mesh"]:
            assert m["cl"] == sorted(m["cl"]), (label, "CL must rise with alpha")
            assert m["cd"] == sorted(m["cd"]), (label, "CD must rise with CL")
            assert all(cd > 0 for cd in m["cd"]), (label, m)
        # e is referenced to PROJECTED span, so e > 1 is the nonplanar payoff and
        # is expected — but an order of magnitude is not (a 2026-07-23 run
        # reported 10.12). Outside this band is a broken solve, not a clever
        # winglet.
        assert 0.5 < r["e_projected_span"] < 2.0, label
        # the fit intercept stands in for viscous drag the VLM does not model:
        # it is the residual of a straight line through a mildly curved
        # CD(CL^2), and must stay small against the drag it is an intercept of
        assert abs(r["cd0_inviscid"]) < 0.1 * max(r["per_mesh"][0]["cd"]), label

    assert res["on"]["k_induced"] < res["off"]["k_induced"]
    assert res["on"]["e_projected_span"] > res["off"]["e_projected_span"]


# ---------------------------------------------------------------- the guard
# A wrong VLM answer does not raise — it returns a plausible float. So the guard
# is the load-bearing part, and it is tested against synthesized polars rather
# than by hunting for a geometry that currently breaks.


CLS = [0.3, 0.6, 0.9]
ALPHAS = (2.0, 4.0, 6.0)


def _polar(k: float):
    """A clean inviscid polar of slope k, as (cls, cds)."""
    return CLS, [k * c**2 for c in CLS]


def _stub_polars(monkeypatch, *per_mesh):
    by_mesh = dict(zip(aero.VLM_MESHES, per_mesh))
    monkeypatch.setattr(aero, "_vlm_polar", lambda plane, V, alphas, mesh: by_mesh[mesh])


class _FakePlane:
    b_ref, s_ref = 2.0, 0.42


def _check(monkeypatch, *per_mesh):
    _stub_polars(monkeypatch, *per_mesh)
    return aero.vlm_induced_check({"x": _FakePlane()}, 9.5, alphas=ALPHAS)["x"]


def test_clean_ensemble_passes(monkeypatch):
    r = _check(monkeypatch, _polar(0.027), _polar(0.0275), _polar(0.0265))
    assert r["reliable"] is True
    assert "unreliable_reason" not in r
    assert r["k_induced"] == pytest.approx(0.027, rel=1e-2)
    assert len(r["meshes_in_consensus"]) == 3
    assert r["e_projected_span"] == pytest.approx(
        1 / (np.pi * (_FakePlane.b_ref**2 / _FakePlane.s_ref) * r["k_induced"])
    )


def test_one_blown_up_mesh_is_outvoted(monkeypatch):
    """The real failure: one mesh returns a plausible-looking but wrong k.

    Two agreeing meshes are enough, and the outlier must not move the answer —
    on the 2026-07-31 continuous-cant plane the three meshes returned 0.0226,
    0.0842 and 0.0219, and averaging them would have been 50% wrong.
    """
    r = _check(monkeypatch, _polar(0.0226), _polar(0.0842), _polar(0.0219))
    assert r["reliable"] is True
    assert r["k_induced"] == pytest.approx((0.0226 + 0.0219) / 2, rel=1e-2)
    assert r["meshes_in_consensus"] == [(8, 8), (16, 10)]


def test_negative_slope_mesh_is_dropped_not_averaged(monkeypatch):
    """CD falling as CL^2 rises is impossible — that mesh is not data."""
    r = _check(monkeypatch, (CLS, [0.010, 0.008, 0.005]), _polar(0.027), _polar(0.0275))
    assert r["reliable"] is True
    assert r["meshes_dropped_unphysical"] == [(8, 8)]
    assert r["k_induced"] == pytest.approx(0.02725, rel=1e-2)


def test_rounding_noise_at_the_lowest_alpha_does_not_condemn_a_mesh(monkeypatch):
    """A clean rising polar whose first point rounds a hair below zero is a good
    solve with a rounding error — the 2026-07-31 polyhedral run had CD = -9.4e-5
    at CL 0.28 and was otherwise identical to its neighbours."""
    cls, cds = _polar(0.027)
    noisy = (cls, [-9.4e-5] + cds[1:])
    r = _check(monkeypatch, _polar(0.0272), _polar(0.0268), noisy)
    assert r["meshes_dropped_unphysical"] == []
    assert r["reliable"] is True


def test_negative_drag_is_never_reported_as_reliable(monkeypatch):
    """The 2026-07-31 champion's actual sweep, on every mesh."""
    bad = (CLS, [-0.54, -0.87, -1.28])
    r = _check(monkeypatch, bad, bad, bad)
    assert r["reliable"] is False
    assert "agree" in r["unreliable_reason"]
    assert "unphysical" in r["unreliable_reason"]


def test_ensemble_disagreement_is_flagged(monkeypatch):
    """Three physical answers that do not agree is not an answer."""
    r = _check(monkeypatch, _polar(0.018), _polar(0.024), _polar(0.031))
    assert r["reliable"] is False
    assert "k_induced" in r["unreliable_reason"]
    # still reports its best guess, so the number can be audited
    assert r["k_induced"] > 0
