"""The IN-LOOP aero model can return negative drag, and did (FINDINGS §18).

Found by running: at AeroSandbox's default 4 panels per section, a highly
canted winglet contributed about -0.93 N and a span-3.0 m solve reported 0.0275 N
of TOTAL drag, an L/D of 889, and 222 minutes of endurance. The optimizer had not
found an aircraft — it had found a corner where the discretization produced
thrust, which to a maximizer is free endurance.

This is the same failure family as the VLM cross-check (§16.1, tests/test_vlm_check.py)
with one difference that matters: this model is IN THE LOOP, so the optimizer is
drawn to it rather than merely reporting it.

Two defences, both pinned here: the winglet carries enough stations that the
in-loop mesh is not wrong to begin with, and the champion's drag is re-checked
against a finer mesh so that a future artefact is reported rather than shipped.
"""

from __future__ import annotations

import aerosandbox as asb
import pytest

from planeopt import aero

#: The span-3.0 m design the artefact was found on (2026-08-01 run, flatness
#: member at the cap). Wing-shaping and winglet entries only; the rest default.
ARTEFACT_DV = {
    "span": 3.0, "c_root": 0.23833, "taper": 0.90153, "fullness": 1.11471,
    "le_shear": 0.88349, "eta_break": 0.38536, "washout_tip": -3.85438,
    "dihedral_tip": 4.57511, "d_exp": 0.02980,
    "t_span": 0.70989, "t_c_root": 0.14669, "t_taper": 0.68206,
    "t_sweep": 7.48550, "t_dihedral": 53.26574, "cs_frac": 0.31296,
    "tail_arm": 1.12621,
    "wl_len": 0.05216, "wl_cant": 85.98260, "wl_cr": 0.52571,
    "wl_taper": 0.84479, "wl_toe": -1.14754,
}
V, ALPHA, DEFL, X_CG = 9.5, 5.44095, -2.25439, 0.4105

#: What a converged mesh says the drag actually is, in newtons. Measured across
#: spanwise resolutions 6, 8, 12, 16 and 24, which agree to within 4%.
CONVERGED_DRAG_N = 0.92


def _drag(aircraft, dv, resolution=4):
    plane = aircraft.geometry(dv).with_control_deflections(
        {getattr(aircraft, "pitch_control_name", "ruddervator"): DEFL}
    )
    r = asb.LiftingLine(
        airplane=plane, op_point=asb.OperatingPoint(velocity=V, alpha=ALPHA),
        xyz_ref=[X_CG, 0, 0], spanwise_resolution=resolution,
    ).run()
    return float(r["D"])


def test_the_winglet_carries_enough_stations_to_be_meshed(sample_aircraft):
    """`spanwise_resolution` panels go in each SECTION, so a two-station winglet
    is four panels of a small, highly loaded, near-vertical surface."""
    assert sample_aircraft.WL_STATIONS >= 3
    winglet = next(w for w in sample_aircraft.geometry({}).wings if w.name == "winglet")
    assert len(winglet.xsecs) == sample_aircraft.WL_STATIONS


def test_the_artefact_geometry_no_longer_makes_thrust(sample_aircraft):
    """The exact design that reported an L/D of 889."""
    d = _drag(sample_aircraft, ARTEFACT_DV)
    assert d > 0, "an aircraft in level flight cannot produce thrust"
    assert d == pytest.approx(CONVERGED_DRAG_N, rel=0.10)


def test_the_two_station_winglet_is_what_was_wrong(sample_aircraft):
    """Kept as the reproduction: with the old station count the in-loop mesh
    returns negative drag on this geometry, so the fix is load-bearing and not
    a coincidence of some other change."""
    sample_aircraft.WL_STATIONS = 2
    try:
        assert _drag(sample_aircraft, ARTEFACT_DV) < 0
    finally:
        sample_aircraft.WL_STATIONS = 3


def test_the_fix_does_not_move_designs_that_were_already_converged(sample_aircraft):
    """A mesh fix that changed converged answers would be trading one artefact
    for another. On the 2026-08-01 champion the shift is under 1%."""
    dv = {**ARTEFACT_DV, "span": 2.49246, "c_root": 0.21742, "washout_tip": -0.62744,
          "wl_cant": 55.0, "taper": 0.64382, "fullness": 1.0}
    fine = _drag(sample_aircraft, dv, resolution=16)
    assert _drag(sample_aircraft, dv) == pytest.approx(fine, rel=0.05)


# --------------------------------------------------------------- the guard


class _FakeRun(dict):
    pass


def _stub_ll(monkeypatch, by_resolution):
    class _LL:
        def __init__(self, airplane, op_point, xyz_ref, spanwise_resolution=4):
            self.res = spanwise_resolution

        def run(self):
            d = by_resolution[self.res]
            return {"D": d, "L": 19.0, "CL": 0.7}

    monkeypatch.setattr(aero.asb, "LiftingLine", _LL)


class _Plane:
    def with_control_deflections(self, _):
        return self


def _check(monkeypatch, in_loop, fine):
    _stub_ll(monkeypatch, {4: in_loop, aero.LL_CHECK_RESOLUTION: fine})
    return aero.mesh_convergence_check(_Plane(), 9.5, 5.0, -2.0, 0.4)


def test_negative_in_loop_drag_is_never_converged(monkeypatch):
    """The 2026-08-01 case: -0.033 N in the loop, +0.92 N converged."""
    r = _check(monkeypatch, -0.03303, 0.92344)
    assert r["converged"] is False
    assert r["in_loop"]["D_n"] < 0 < r["fine"]["D_n"]


def test_a_large_disagreement_is_flagged(monkeypatch):
    r = _check(monkeypatch, 0.50, 0.92)
    assert r["converged"] is False
    assert r["delta_frac"] == pytest.approx((0.50 - 0.92) / 0.92)


def test_agreement_passes(monkeypatch):
    r = _check(monkeypatch, 0.700, 0.724)
    assert r["converged"] is True
    assert abs(r["delta_frac"]) < aero.LL_CHECK_TOL


def test_the_check_compares_the_in_loop_resolution_against_a_finer_one(monkeypatch):
    """It must ask the SAME resolution the NLP used, or it is checking nothing."""
    seen = []

    class _LL:
        def __init__(self, airplane, op_point, xyz_ref, spanwise_resolution=4):
            seen.append(spanwise_resolution)

        def run(self):
            return {"D": 0.7, "L": 19.0, "CL": 0.7}

    monkeypatch.setattr(aero.asb, "LiftingLine", _LL)
    aero.mesh_convergence_check(_Plane(), 9.5, 5.0, -2.0, 0.4)
    assert seen == [4, aero.LL_CHECK_RESOLUTION]
    assert aero.LL_CHECK_RESOLUTION > 4
