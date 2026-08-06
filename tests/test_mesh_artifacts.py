"""The IN-LOOP aero model can return negative drag, and did (FINDINGS §18).

Found by running: at AeroSandbox's default 4 panels per section, a highly
canted winglet contributed about -0.93 N and a span-3.0 m solve reported 0.0275 N
of TOTAL drag, an L/D of 889, and 222 minutes of endurance. The optimizer had not
found an aircraft — it had found a corner where the discretization produced
thrust, which to a maximizer is free endurance.

This is the same failure family as the VLM cross-check (§16.1, tests/test_vlm_check.py)
with one difference that matters: this model is IN THE LOOP, so the optimizer is
drawn to it rather than merely reporting it.

Two defences, both pinned here: every lifting-line call regularizes its vortex
cores so the in-loop model is not wrong to begin with, and the champion's drag is
re-checked against a finer mesh so a future artefact is reported rather than
shipped.

Refining the mesh was tried first — more stations on the winglet — and it is
recorded here as the rejected fix: it corrected the sign and then produced a NaN
in the real solve, because more panels on a small canted surface is more chances
of the near-coincident filaments that caused this in the first place.
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


#: The same design at the cant the champion actually uses — converged before the
#: fix and after it, which is what makes it the control.
CHAMPION_DV = {**ARTEFACT_DV, "span": 2.49246, "c_root": 0.21742,
               "washout_tip": -0.62744, "wl_cant": 55.0, "taper": 0.64382,
               "fullness": 1.0}


def _drag(aircraft, dv, resolution=4, core=None):
    plane = aircraft.geometry(dv).with_control_deflections(
        {getattr(aircraft, "pitch_control_name", "ruddervator"): DEFL}
    )
    r = asb.LiftingLine(
        airplane=plane, op_point=asb.OperatingPoint(velocity=V, alpha=ALPHA),
        xyz_ref=[X_CG, 0, 0], spanwise_resolution=resolution,
        vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS if core is None else core,
    ).run()
    return float(r["D"])


def test_the_vortex_core_is_regularized_at_all(sample_aircraft):
    """AeroSandbox's 1e-8 default is no regularization: a filament's induced
    velocity goes as 1/r, so a control point a micron away dominates the
    solution. It also must not be so large that it distorts a fine mesh — at
    1e-3 the 16-panel answer itself moves 8%."""
    assert 1e-5 <= aero.LL_VORTEX_CORE_RADIUS <= 5e-4


def test_the_artefact_geometry_no_longer_makes_thrust(sample_aircraft):
    """The exact design that reported an L/D of 889."""
    d = _drag(sample_aircraft, ARTEFACT_DV)
    assert d > 0, "an aircraft in level flight cannot produce thrust"
    assert d == pytest.approx(CONVERGED_DRAG_N, rel=0.10)


def test_the_unregularized_core_is_what_was_wrong(sample_aircraft):
    """The reproduction, kept: at AeroSandbox's default core this geometry still
    returns negative drag, so the fix is load-bearing rather than a coincidence
    of some other change."""
    assert _drag(sample_aircraft, ARTEFACT_DV, core=1e-8) < 0


def test_the_fix_does_not_move_designs_that_were_already_converged(sample_aircraft):
    """A fix that changed converged answers would be trading one artefact for
    another: on the champion's own cant the shift is a couple of percent, and it
    moves TOWARD the fine mesh rather than away."""
    fine = _drag(sample_aircraft, CHAMPION_DV, resolution=16)
    before = _drag(sample_aircraft, CHAMPION_DV, core=1e-8)
    after = _drag(sample_aircraft, CHAMPION_DV)
    assert after == pytest.approx(fine, rel=0.05)
    assert abs(after - fine) <= abs(before - fine)


def test_refining_the_mesh_would_also_have_worked_and_is_not_how_it_is_fixed():
    """Recorded because it is the fix a reader will reach for first, and it was
    tried: at 16 panels/section the shipped core radius is unnecessary. The
    reason it is not the answer is cost and NaNs, not correctness — the NLP
    builds four of these graphs per solve and already peaks near 12 GB."""
    assert aero.LL_CHECK_RESOLUTION > 4


# --------------------------------------------------------------- the guard


def _stub_ll(monkeypatch, by_resolution, seen=None):
    class _LL:
        def __init__(self, airplane, op_point, xyz_ref, spanwise_resolution=4,
                     vortex_core_radius=None):
            self.res = spanwise_resolution
            if seen is not None:
                seen.append((spanwise_resolution, vortex_core_radius))

        def run(self):
            return {"D": by_resolution[self.res], "L": 19.0, "CL": 0.7}

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
    """It must ask the SAME resolution and the SAME core radius the NLP used, or
    it is checking a different model and can only mislead."""
    seen = []
    _stub_ll(monkeypatch, {4: 0.7, aero.LL_CHECK_RESOLUTION: 0.7}, seen=seen)
    aero.mesh_convergence_check(_Plane(), 9.5, 5.0, -2.0, 0.4)

    assert [res for res, _ in seen] == [4, aero.LL_CHECK_RESOLUTION]
    assert aero.LL_CHECK_RESOLUTION > 4
    assert {core for _, core in seen} == {aero.LL_VORTEX_CORE_RADIUS}


# ------------------------------------------- the model-validity backstop
# The core-radius fix removes the artefact that was FOUND. A battery is ~24
# solves and only the champion gets a fine-mesh cross-check, so the next hole
# would again be discovered by reading an implausible number hours later.


def test_the_aircraft_declares_a_lift_to_drag_ceiling(sample_aircraft):
    """Declared, not predicted — the same posture as speed_sample's
    `aspect_ratio_min`: a limit on what this model may be believed about."""
    assert sample_aircraft.lift_to_drag_max == pytest.approx(45.0)


def test_the_ceiling_cannot_bind_on_a_real_design_of_this_class(sample_aircraft):
    """A validity bound that caps actual designs is a silent lie about the
    optimum. Both champions on record trim near L/D 25."""
    fine = _drag(sample_aircraft, CHAMPION_DV, resolution=16)
    lift_n = 18.79  # the 2.49 m champion's weight
    assert lift_n / fine < 0.75 * sample_aircraft.lift_to_drag_max


def test_the_ceiling_would_have_refused_the_artefact(sample_aircraft):
    """L/D 889 against a ceiling of 45 — the constraint the NLP now carries
    rejects that iterate instead of converging onto it."""
    artefact_ld = 24.47 / 0.02754  # the 2026-08-01 solve's own numbers
    assert artefact_ld > 10 * sample_aircraft.lift_to_drag_max


def test_the_ceiling_is_written_so_that_NEGATIVE_drag_violates_it():
    """The natural form — `L / drag <= ld_max` — is SATISFIED by negative drag,
    because a negative number is comfortably below any ceiling. It would have let
    the exact iterate this constraint exists to refuse walk straight through.

    Written as a drag floor against WEIGHT (`drag * ld_max / W >= 1`) it refuses
    both: an implausible L/D and a physically impossible sign.
    """
    W, LD = 24.47, 45.0

    def natural_form_ok(drag):
        return (W / drag) <= LD          # the tempting version

    def shipped_form_ok(drag):
        return (drag * LD / W) >= 1.0    # what _solve_nlp carries

    assert natural_form_ok(-0.03303) is True, "this is why the form matters"
    assert shipped_form_ok(-0.03303) is False
    # and both agree on the cases that are merely implausible or fine
    assert shipped_form_ok(W / 889) is False   # the artefact's own L/D
    assert shipped_form_ok(W / 25) is True     # a real champion


def test_the_ceiling_is_optional_at_the_framework_level():
    """An aircraft that declares nothing must solve exactly as before — the
    framework may not assume an aerodynamic limit on someone else's design."""
    import inspect

    from planeopt import solve

    src = inspect.getsource(solve._solve_nlp)
    assert 'getattr(aircraft, "lift_to_drag_max", None)' in src
    assert "if ld_max is not None:" in src
    # and it is the drag-floor form, not the one negative drag satisfies
    assert "drag * ld_max / weight_n >= 1.0" in src


# ------------------------------------- the static margin, asked the same way
# Drag is compared at ONE operating point. The static margin is a SLOPE over an
# alpha window, and a slope can be mesh-dependent while every individual point
# looks fine. Cm at the trim point is deliberately not the quantity compared:
# trim drives it to ~0 by construction, so a delta there is noise about nothing.
#
# Measured on the spec aircraft at the 2026-08-06 run's trim point:
#
#   4 panels/section   SM = +0.0541   local slopes  -0.0220 +0.0365 +0.1249 ...
#   8 panels/section   SM = +0.0515   local slopes  -0.0255 +0.0332 +0.1230 ...
#  16 panels/section   SM = +0.0491   local slopes  -0.0281 +0.0308 +0.1207 ...
#
# The sign change does not wash out under refinement — it deepens. That is the
# difference between "the mesh is lying" and "the aeroplane is like this".


@pytest.mark.slow  # ~3 s of real lifting-line sweeps
def test_the_spec_aircraft_sign_flip_is_not_a_mesh_artefact(sample_aircraft):
    """The finding, on the real aeroplane, through production code."""
    dv = dict(sample_aircraft.DV_DEFAULTS)
    r = aero.mesh_convergence_check(
        sample_aircraft.geometry(dv), 10.5, 6.0784982825928315, 0.0,
        0.4766442793775463, c_ref=0.19861110279967192,
        bodies=sample_aircraft.parasite_bodies(dv),
    )
    sm = r["static_margin"]
    assert sm["sign_flip_survives_refinement"] is True
    assert sm["sign_flip_is_mesh_artefact"] is False
    # both meshes see it, which is what makes refinement not the explanation
    assert sm["in_loop"]["sign_consistent"] is False
    assert sm["fine"]["sign_consistent"] is False
    # and the margin is still MOVING at 16 panels, by more than the magnitude
    # already known to flip this project's verdicts
    assert abs(sm["delta"]) > aero.LL_SM_MESH_TOL
    assert sm["converged"] is False


def _stub_sm(monkeypatch, by_resolution):
    """Drive `static_margin` per resolution without touching aerodynamics."""
    def fake(airplane, V, x_cg, c_ref, alpha0=2.0, bodies=None,
             spanwise_resolution=None):
        sm, locals_ = by_resolution[spanwise_resolution]
        return {
            "static_margin": sm,
            "x_np_m": x_cg + sm * c_ref,
            "sm_local_slopes": [{"alpha": 5.0 + i, "sm_local": v}
                                for i, v in enumerate(locals_)],
            "sm_alpha_window_deg": [4.0, 6.0, 8.0],
        }

    monkeypatch.setattr(aero, "static_margin", fake)


def _sm_check(monkeypatch, in_loop, fine):
    _stub_ll(monkeypatch, {4: 0.7, aero.LL_CHECK_RESOLUTION: 0.7})
    _stub_sm(monkeypatch, {4: in_loop, aero.LL_CHECK_RESOLUTION: fine})
    return aero.mesh_convergence_check(
        _Plane(), 9.5, 5.0, -2.0, 0.4, c_ref=0.2
    )["static_margin"]


def test_a_sign_flip_that_vanishes_under_refinement_is_named_an_artefact(monkeypatch):
    """The other outcome, which must be reachable or the check is one-sided.

    This is the FINDINGS §18 shape — a pathology that exists only at the coarse
    mesh the NLP runs at — and it demands the opposite response: read the fine
    mesh and stop believing the in-loop number.
    """
    sm = _sm_check(
        monkeypatch,
        in_loop=(0.054, [-0.022, 0.037, 0.125]),
        fine=(0.055, [0.101, 0.118, 0.130]),
    )
    assert sm["sign_flip_is_mesh_artefact"] is True
    assert sm["sign_flip_survives_refinement"] is False


def test_a_margin_that_moves_more_than_the_tolerance_is_not_converged(monkeypatch):
    sm = _sm_check(
        monkeypatch,
        in_loop=(0.054, [0.05, 0.06, 0.07]),
        fine=(0.041, [0.04, 0.05, 0.06]),
    )
    assert sm["converged"] is False
    assert sm["delta"] == pytest.approx(0.041 - 0.054)


def test_a_stable_margin_converges(monkeypatch):
    sm = _sm_check(
        monkeypatch,
        in_loop=(0.101, [0.09, 0.10, 0.11]),
        fine=(0.1005, [0.09, 0.10, 0.11]),
    )
    assert sm["converged"] is True
    assert sm["sign_flip_survives_refinement"] is False
    assert sm["sign_flip_is_mesh_artefact"] is False


def test_an_already_negative_margin_is_not_reported_as_a_hidden_sign_flip(monkeypatch):
    """Same rule `solve.sm_sign_flip` uses: an unstable aeroplane is obvious,
    not hidden, and calling it a 'sign flip' would bury the real headline."""
    sm = _sm_check(
        monkeypatch,
        in_loop=(-0.02, [-0.05, -0.01, 0.02]),
        fine=(-0.02, [-0.05, -0.01, 0.02]),
    )
    assert sm["in_loop"]["sign_consistent"] is True
    assert sm["sign_flip_survives_refinement"] is False


def test_the_margin_sweep_is_skipped_without_c_ref(monkeypatch):
    """Backward compatibility is deliberate: the drag question is answerable
    without a reference chord, and callers that only want it should not pay for
    ten extra lifting-line runs."""
    r = _check(monkeypatch, 0.700, 0.724)
    assert "static_margin" not in r
