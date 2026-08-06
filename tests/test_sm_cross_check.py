"""The pitching-moment second opinion (`aero.vlm_static_margin_check`).

Until 2026-08-06 drag had two cross-checks and Cm had none — backwards, because
Cm is the quantity this project already knows is its weakest and the only one
that decides whether the aeroplane is flyable. The 2026-08-05 champions report
`static_margin = 0.0646` against a required [0.08, 0.15], with the local
dCm/dCL running -0.0114 to +0.1805 over four degrees: a reported margin that is
a least-squares slope through points whose slope CHANGES SIGN.

Two very different things produce that and no LiftingLine number can separate
them — either Cm(alpha) really is that nonlinear, or LL's Cm is noisy at four
panels per section (FINDINGS §18 is a 4-panel artefact that produced an L/D of
889). This asks an independent method the same question over the same window.

Measured on the spec aircraft at the 2026-08-06 run's own trim point
(V = 10.5, alpha = 6.078, x_cg = 0.4766, c_ref = 0.1986):

    LiftingLine  SM = 0.054   local slopes  -0.022  +0.037  +0.125  +0.159
    VLM          SM = 0.113   local slopes  +0.124  +0.127  +0.131  +0.135

The VLM is very nearly linear and never changes sign. That does NOT prove the
airframe is linear — this sweep is inviscid and LL carries NeuralFoil's viscous
Cm at Re ~46k, which is exactly where a laminar separation bubble would put real
nonlinearity. It localizes the disagreement rather than settling it, and the
tests below pin that distinction so the check is never read as a verdict.
"""

import pytest

from planeopt import aero

TRIM = {"V": 10.5, "alpha": 6.0784982825928315,
        "x_cg": 0.4766442793775463, "c_ref": 0.19861110279967192}


@pytest.mark.slow  # ~10 s of real VLM solves
def test_the_VLM_does_not_reproduce_LLs_sign_flip_on_the_spec_aircraft(
    sample_aircraft,
):
    """The finding, end to end through both production estimators.

    Both are sampled over the same window and run through the same estimator
    (`static_margin_from_polar`, Munk term included), so the only difference
    between them is the aerodynamic method.
    """
    dv = dict(sample_aircraft.DV_DEFAULTS)
    plane = sample_aircraft.geometry(dv)
    bodies = sample_aircraft.parasite_bodies(dv)

    ll = aero.static_margin(
        plane, TRIM["V"], TRIM["x_cg"], TRIM["c_ref"],
        alpha0=TRIM["alpha"], bodies=bodies,
    )
    vlm = aero.vlm_static_margin_check(
        {"c": plane}, TRIM["V"], TRIM["alpha"], TRIM["x_cg"], TRIM["c_ref"],
        bodies=bodies,
    )["c"]

    assert vlm["reliable"], vlm.get("unreliable_reason")
    # LL changes sign inside its own window...
    assert any(p["sm_local"] < 0 for p in ll["sm_local_slopes"])
    # ...and the independent method does not, anywhere.
    assert vlm["sign_consistent"]
    assert all(p["sm_local"] > 0 for p in vlm["sm_local_slopes"])
    # The VLM's slopes are nearly constant — the spread that LL puts at a
    # factor of several, it puts at a few percent.
    slopes = [p["sm_local"] for p in vlm["sm_local_slopes"]]
    assert max(slopes) / min(slopes) < 1.5, slopes
    # and the levels are NOT expected to match, which is the point of the note
    assert vlm["static_margin"] != pytest.approx(ll["static_margin"], rel=0.2)


@pytest.mark.slow  # ~10 s
def test_the_coarse_mesh_that_blows_up_elsewhere_is_dropped_here_too(
    sample_aircraft,
):
    """(8, 8) returns CL = +123 on this geometry in the directional sweep. It
    is not a different mesh here, and the guard is not a different guard."""
    plane = sample_aircraft.geometry(dict(sample_aircraft.DV_DEFAULTS))
    vlm = aero.vlm_static_margin_check(
        {"c": plane}, TRIM["V"], TRIM["alpha"], TRIM["x_cg"], TRIM["c_ref"],
    )["c"]
    assert (8, 8) in vlm["meshes_dropped_unphysical"]
    assert vlm["reliable"], "the two finer meshes still carry it"


# ---------------------------------------------------------------- the guard

OFFSETS = sorted(aero.SM_ALPHA_OFFSETS + aero.SM_DIAGNOSTIC_OFFSETS)


def _pitch(sm, *, cl0=0.5, dcl=0.09, lift=None, curl=0.0):
    """A CL/Cm sweep with static margin `sm`.

    Cm = -sm * CL puts the requested margin in by construction. `curl` bends
    Cm quadratically in CL, which is how a sign flip is manufactured without
    touching anything else.
    """
    rows = []
    for i, _d in enumerate(OFFSETS):
        cl = cl0 + dcl * i if lift is None else lift[i]
        rows.append({"CL": cl, "Cm": -sm * cl + curl * cl**2})
    return rows


def _check(monkeypatch, *per_mesh, bodies=None):
    by_mesh = dict(zip(aero.VLM_MESHES, per_mesh))
    monkeypatch.setattr(
        aero, "_vlm_pitch",
        lambda plane, V, alphas, mesh, x_cg: by_mesh[mesh],
    )

    class _P:
        s_ref = 0.4

    return aero.vlm_static_margin_check(
        {"x": _P()}, 10.5, 6.0, 0.47, 0.2, bodies=bodies
    )["x"]


def test_clean_ensemble_recovers_the_margin_it_was_built_from(monkeypatch):
    r = _check(monkeypatch, _pitch(0.11), _pitch(0.112), _pitch(0.108))
    assert r["reliable"] is True
    assert r["static_margin"] == pytest.approx(0.11, rel=1e-2)
    assert r["sign_consistent"] is True
    assert r["x_np_m"] == pytest.approx(0.47 + r["static_margin"] * 0.2)


def test_a_sign_flip_inside_the_window_is_reported(monkeypatch):
    """The pathology this exists to detect, on the VLM side too.

    `sign_consistent` must be able to come back False — a check that could only
    ever exonerate would be worthless as a second opinion.

    Built to mirror LL's real shape rather than any curved sweep: a POSITIVE
    reported margin whose local slope is negative at the LOW-alpha end. With
    Cm = 0.6·CL − 0.5·CL², the local slope is −dCm/dCL = CL − 0.6, so it is
    negative below CL 0.6, while the regression over the window's own three CLs
    (0.50, 0.68, 0.86) still returns +0.08. Note a merely large curvature will
    NOT do: it drives the reported margin itself negative, and `sign_consistent`
    then short-circuits to True by design — the same guard `solve.sm_sign_flip`
    applies, since an already-negative margin is not a hidden sign flip.
    """
    rows = [
        {"CL": 0.5 + 0.09 * i, "Cm": 0.6 * (0.5 + 0.09 * i) - 0.5 * (0.5 + 0.09 * i) ** 2}
        for i in range(len(OFFSETS))
    ]
    r = _check(monkeypatch, rows, rows, rows)
    assert r["reliable"] is True
    assert r["static_margin"] > 0, "the reported margin must stay positive..."
    assert r["sign_consistent"] is False, "...while a local slope goes negative"
    assert any(p["sm_local"] < 0 for p in r["sm_local_slopes"])


def test_lift_that_falls_with_alpha_is_not_a_solve(monkeypatch):
    """A lifting surface whose CL drops as incidence rises has not converged,
    whatever margin the resulting slope implies."""
    backwards = _pitch(0.11, lift=[0.9, 0.8, 0.7, 0.6, 0.5])
    r = _check(monkeypatch, backwards, _pitch(0.11), _pitch(0.112))
    assert r["meshes_dropped_unphysical"] == [(8, 8)]
    assert r["reliable"] is True


def test_an_insane_CL_is_dropped(monkeypatch):
    """The measured (8, 8) failure mode: CL = 123 where LL returns 0.5."""
    blown = _pitch(0.11, lift=[120.0, 121.0, 122.0, 123.0, 124.0])
    r = _check(monkeypatch, blown, _pitch(0.11), _pitch(0.112))
    assert r["meshes_dropped_unphysical"] == [(8, 8)]
    assert r["reliable"] is True


def test_ensemble_disagreement_is_flagged(monkeypatch):
    r = _check(monkeypatch, _pitch(0.06), _pitch(0.11), _pitch(0.20))
    assert r["reliable"] is False
    assert "static_margin" in r["unreliable_reason"]


def test_the_fuselage_term_is_applied_when_bodies_are_given(monkeypatch):
    """Same estimator as the in-loop path, Munk term included — otherwise the
    comparison against LiftingLine is not like for like."""
    clean = _check(monkeypatch, _pitch(0.11), _pitch(0.11), _pitch(0.11))
    # `fuselage_cm_alpha` keys off volume_m3 specifically — a body without one
    # contributes nothing, so this test would pass vacuously with any other key
    bodies = [{"name": "pod", "volume_m3": 0.0042}]
    withbody = _check(
        monkeypatch, _pitch(0.11), _pitch(0.11), _pitch(0.11), bodies=bodies
    )
    assert withbody["static_margin"] != pytest.approx(clean["static_margin"])


# ------------------------------------------------------------------ the report
# The block was shipped without these and the omission is the point: a
# measurement nobody can see is the defect shape this project keeps finding
# (FINDINGS §20 — seven claims a converged run was not entitled to make, none
# of them in its numbers).


def _render(smc, ll_sign_consistent=False):
    from types import SimpleNamespace

    from planeopt.report import html

    return html.render(SimpleNamespace(
        aircraft="x", mission="m", objective="endurance", status="s", created="c",
        geometry={}, masses={}, notes=[], performance={},
        # `static_margin` rides along because the report's sign-flip explainer
        # quotes it, and `solve` always sets the two in the same dict literal —
        # a fixture that supplies one without the other is not a shape any run
        # produces, and testing against it would be testing a fiction.
        constraints={"sm_sign_consistent": ll_sign_consistent,
                     "static_margin": 0.05407},
        diagnostics={"sm_cross_check": smc},
    ))


def _entry(**over):
    return {
        "static_margin": 0.11329, "ll_static_margin": 0.05407,
        "x_np_m": 0.4992, "sign_consistent": True,
        "sm_local_slopes": [{"alpha": 4.08, "sm_local": 0.1235}],
        "alpha_window_deg": [4.08, 6.08, 8.08],
        "meshes_in_consensus": [(12, 10), (16, 10)],
        "meshes_averaged": [(12, 10), (16, 10)],
        "meshes_dropped_unphysical": [(8, 8)],
        "per_mesh": [{}, {}, {}], "reliable": True,
    } | over


def test_the_report_shows_both_methods_side_by_side():
    """Both numbers, or the comparison is not a comparison."""
    import re

    section = re.search(
        r"<h2>Static margin cross-check.*?</table>", _render(_entry()), re.DOTALL
    )
    assert section, "the report dropped the static-margin cross-check entirely"
    text = section.group(0)
    assert "0.1133" in text          # the VLM's
    assert "0.0541" in text          # LiftingLine's, beside it
    assert "2 of 3" in text          # whether the ensemble agreed


def test_the_disagreement_about_the_SIGN_is_what_the_report_highlights():
    """The levels are not expected to match — an inviscid sweep carries no
    viscous Cm — so the row that carries meaning is the sign one, and it must
    show the two methods disagreeing when they do."""
    text = _render(_entry(sign_consistent=True), ll_sign_consistent=False)
    assert "slope sign constant across the window" in text
    assert "yes" in text and "no" in text
    # and the caveat against reading it as a verdict must survive
    assert "inviscid" in text


def test_an_unreliable_ensemble_says_so_rather_than_printing_a_number_alone():
    text = _render(_entry(reliable=False, unreliable_reason="meshes disagree"))
    assert "not reliable" in text
    assert "meshes disagree" in text


def test_a_missing_LL_number_does_not_break_the_block():
    """The re-evaluation can fail while the cross-check still ran; the block
    must degrade rather than raise."""
    e = _entry()
    del e["ll_static_margin"]
    text = _render(e)
    assert "Static margin cross-check" in text
    assert "0.1133" in text
