"""The lateral-directional second opinion (`aero.vlm_directional_check`).

MODEL_DETAILS 8.4 declared a vertical-tail-volume floor because "LL has no yaw
axis". On asb 4.2.10 that premise is measurably false — LiftingLine answers
sideslip with the right sign and a clean monotonic trend in V-angle — but its
MAGNITUDE is not usable: on the 2026-08-05 champion it over-predicts Cn_beta by
2.15x at t_dihedral 20 deg and 1.34x at 55 deg. This check is what supplies the
number, so it has to be right about two different things.

1. The DERIVATIVES, which the in-loop constraint is calibrated against.
2. The GUARD, because the failure mode here is not a crash. Measured on the
   sample aircraft's own DV_DEFAULTS geometry, the (8, 8) mesh returns
   `cn_beta = +1.849` with CL = 144.3, against +0.00223 with CL = 0.47 from the
   two finer meshes. That wrong answer is POSITIVE — it reads as a comfortably
   stable aeroplane — and it is perfectly antisymmetric. Symmetry alone lets it
   through. Both guards are load-bearing, which is what the tests below pin.
"""

import pytest

from planeopt import aero

#: The 2026-08-05 champion, as `test_vlm_check.py` carries it. `t_dihedral` sits
#: at 55.0 because that is its upper BOUND (aircraft.py:673) and it pins there
#: every run — the thing the directional work exists to interrogate.
CHAMPION_DV = {
    "span": 2.0, "c_root": 0.25334, "taper": 0.55254, "fullness": 1.31855,
    "le_shear": 1.0, "eta_break": 0.30954, "washout_tip": 0.0,
    "dihedral_tip": 4.65222, "d_exp": 0.0,
    "t_span": 0.44415, "t_c_root": 0.09523, "t_taper": 0.95990,
    "t_sweep": 0.98520, "t_dihedral": 55.0, "cs_frac": 0.40,
    "wl_len": 0.06510, "wl_cant": 87.09895, "wl_cr": 0.66667,
    "wl_taper": 1.0, "wl_toe": -2.69365,
}
CHAMPION_V, CHAMPION_ALPHA, CHAMPION_XCG = 9.5, 3.0, 0.19


@pytest.mark.slow  # ~2 s of real VLM solves — a sideslip sweep carries no polar
def test_champion_is_directionally_stable_and_mesh_independent(sample_aircraft):
    """The verdict the declared Vv floor has always been a stand-in for."""
    plane = sample_aircraft.geometry(CHAMPION_DV)
    r = aero.vlm_directional_check(
        {"champion": plane}, CHAMPION_V, CHAMPION_ALPHA, CHAMPION_XCG
    )["champion"]

    assert r["reliable"], r.get("unreliable_reason")
    assert r["directionally_stable"], "positive Cn_beta is weathercock stability"
    assert r["roll_stable"], "negative Cl_beta is the dihedral effect"
    assert len(r["meshes_in_consensus"]) >= aero.VLM_MIN_CONSENSUS
    # A symmetric aeroplane is antisymmetric in sideslip to solver precision;
    # the champion measures ~0 on every mesh. Anything else is a broken AIC.
    for m in r["per_mesh"]:
        assert m["worst_antisymmetry"] < aero.LAT_ASYM_TOL, m["mesh"]


#: Conventional directional-stiffness band for this class, per RADIAN. The unit
#: matters more than it looks: read per DEGREE, a shallow V-tail returns a
#: positive Cn_beta and reads acceptable, which is how you talk yourself into
#: loosening a floor that was correct (FINDINGS §21).
CNB_BAND_PER_RAD = (0.04, 0.10)
DEG_PER_RAD = 57.2958


@pytest.mark.slow  # ~3 s
def test_the_declared_Vv_floor_lands_Cn_beta_inside_the_conventional_band(
    sample_aircraft,
):
    """What the measurement actually settled about the 55 deg pin.

    `t_dihedral` pins at its bound every run because the floor prices angle
    through sin^2(gamma) at zero drag cost, so the natural suspicion is that the
    floor is loose and tail area is being wasted. The champion at 20 deg does
    still return a positive Cn_beta, which appears to confirm it.

    It does not. Per radian that value is ~0.012 — about four times BELOW the
    conventional band, i.e. weathercocking in the arithmetic sense only, while
    55 deg lands at ~0.072, inside it. The declared 0.030 was better than its
    own stated provenance. This test exists so a later session cannot repeat the
    per-degree mistake and loosen the floor.
    """
    res = aero.vlm_directional_check(
        {f"g{g:g}": sample_aircraft.geometry(CHAMPION_DV | {"t_dihedral": g})
         for g in (20.0, 55.0)},
        CHAMPION_V, CHAMPION_ALPHA, CHAMPION_XCG,
    )
    assert all(v["reliable"] for v in res.values())
    lo, hi = CNB_BAND_PER_RAD

    # the pinned angle, which the floor actually selects, is properly stiff
    assert lo <= res["g55"]["cn_beta"] * DEG_PER_RAD <= hi

    # and the shallow one is NOT, despite being "stable" by sign alone
    assert res["g20"]["directionally_stable"], "positive by sign..."
    assert res["g20"]["cn_beta"] * DEG_PER_RAD < lo, "...and inadequate by magnitude"

    assert res["g55"]["cn_beta"] > res["g20"]["cn_beta"]


# ---------------------------------------------------------------- the guard
# Stubbed sweeps, not hunted geometries: a wrong VLM answer returns a plausible
# float rather than raising, so the guard is tested against sweeps built to
# break each property one at a time.

CLEAN_CL = 0.55


def _sweep(cn_beta, *, cl_beta=-0.00225, cy_beta=-0.0038, lift=CLEAN_CL, offset=0.0):
    """A lateral sweep with the given derivatives.

    `offset` adds a constant to Cn, which leaves the fitted slope untouched and
    breaks the antisymmetry — the two failures are independent by construction.
    """
    return [
        {"CL": lift, "CY": cy_beta * b, "Cl": cl_beta * b, "Cn": cn_beta * b + offset}
        for b in aero.LAT_BETAS
    ]


def _check(monkeypatch, *per_mesh):
    by_mesh = dict(zip(aero.VLM_MESHES, per_mesh))
    monkeypatch.setattr(
        aero, "_vlm_lateral",
        lambda plane, V, alpha, betas, mesh, x_cg: by_mesh[mesh],
    )
    return aero.vlm_directional_check({"x": object()}, 9.5, 3.0, 0.19)["x"]


def test_clean_ensemble_passes(monkeypatch):
    r = _check(monkeypatch, _sweep(0.00125), _sweep(0.00127), _sweep(0.00123))
    assert r["reliable"] is True
    assert "unreliable_reason" not in r
    assert r["cn_beta"] == pytest.approx(0.00125, rel=1e-2)
    assert r["cl_beta"] == pytest.approx(-0.00225, rel=1e-6)
    assert r["directionally_stable"] is True
    assert r["roll_stable"] is True
    assert len(r["meshes_in_consensus"]) == 3


def test_the_measured_blowup_is_caught_by_CL_not_by_symmetry(monkeypatch):
    """The real (8, 8) failure on DV_DEFAULTS, with its real numbers.

    `cn_beta = +1.849` at CL = 144.3 is a POSITIVE, PERFECTLY ANTISYMMETRIC and
    entirely wrong answer — it reads as a very stable aeroplane. This pins that
    the sanity bound on CL is what rejects it, since the symmetry test cannot.
    """
    blown = _sweep(1.849481, lift=144.28)
    r = _check(monkeypatch, blown, _sweep(0.002230), _sweep(0.002231))

    # the property that makes the CL guard necessary rather than redundant
    assert all(
        m["worst_antisymmetry"] < aero.LAT_ASYM_TOL for m in r["per_mesh"]
    ), "the blown-up mesh is antisymmetric — symmetry alone would admit it"
    assert r["meshes_dropped_unphysical"] == [(8, 8)]
    assert r["reliable"] is True
    assert r["cn_beta"] == pytest.approx(0.0022305, rel=1e-3)


def test_broken_antisymmetry_is_dropped(monkeypatch):
    """A mesh whose two halves disagree has not solved a symmetric aeroplane."""
    lopsided = _sweep(0.00125, offset=0.0004)  # ~16% of the sweep's peak |Cn|
    r = _check(monkeypatch, lopsided, _sweep(0.00125), _sweep(0.00127))
    assert r["meshes_dropped_unphysical"] == [(8, 8)]
    assert r["reliable"] is True


def test_directional_INSTABILITY_is_reported_not_discarded(monkeypatch):
    """The finding this tool exists to be able to deliver.

    Cn_beta > 0 is deliberately not an admission test. An aeroplane that does
    not weathercock is the single most important thing this check could ever
    have to say, and a guard that threw it away as 'unphysical' would hide
    exactly the case the declared floor was protecting against.
    """
    r = _check(monkeypatch, _sweep(-0.0008), _sweep(-0.00082), _sweep(-0.00079))
    assert r["reliable"] is True
    assert r["directionally_stable"] is False
    assert r["cn_beta"] < 0


def test_ensemble_disagreement_is_flagged(monkeypatch):
    """Three admissible answers that do not agree is not an answer."""
    r = _check(monkeypatch, _sweep(0.0008), _sweep(0.0013), _sweep(0.0019))
    assert r["reliable"] is False
    assert "cn_beta" in r["unreliable_reason"]
    assert r["cn_beta"] > 0  # still reports a best guess, so it can be argued with


def test_all_meshes_unphysical_is_never_reliable(monkeypatch):
    blown = _sweep(1.849481, lift=144.28)
    r = _check(monkeypatch, blown, blown, blown)
    assert r["reliable"] is False
    assert "unphysical" in r["unreliable_reason"]


# ------------------------------------------------------------------ the report
# A measurement nobody can see is the shape of defect this project keeps
# finding: FINDINGS §20's audit turned up seven things a converged run was
# wrong about, none of them in its numbers and all of them in its claims.


def _render(direc):
    from types import SimpleNamespace

    from planeopt.report import html

    return html.render(SimpleNamespace(
        aircraft="x", mission="m", objective="endurance", status="s", created="c",
        geometry={}, masses={}, constraints={}, notes=[],
        performance={}, diagnostics={"directional_check": direc},
    ))


def _entry(**over):
    return {
        "cn_beta": 0.001251, "cl_beta": -0.002251, "cy_beta": -0.003812,
        "directionally_stable": True, "roll_stable": True,
        "meshes_in_consensus": [(8, 8), (12, 10), (16, 10)],
        "meshes_averaged": [(8, 8), (12, 10), (16, 10)],
        "meshes_dropped_unphysical": [], "betas_deg": [-4.0, -2.0, 2.0, 4.0],
        "alpha_deg": 3.0, "per_mesh": [{}, {}, {}], "reliable": True,
    } | over


def test_the_run_reports_the_directional_verdict():
    """The champion's real numbers, and the verdict beside them."""
    import re

    section = re.search(
        r"<h2>Directional stability.*?</table>", _render(_entry()), re.DOTALL
    )
    assert section, "the report dropped the directional block entirely"
    text = section.group(0)
    assert "+0.001251" in text          # Cn_beta, the number the floor stands for
    assert "-0.002251" in text          # Cl_beta
    assert "stable" in text             # the verdict, not merely the number
    assert "3 of 3 agreed" in text      # whether the ensemble agreed


def test_an_unstable_champion_is_not_quietly_printed():
    text = _render(_entry(cn_beta=-0.0008, directionally_stable=False))
    assert "UNSTABLE" in text


def test_an_unreliable_ensemble_says_so_next_to_its_number():
    text = _render(_entry(reliable=False, unreliable_reason="meshes disagree on cn_beta"))
    assert "not reliable" in text
    assert "meshes disagree on cn_beta" in text


def test_sideslip_stations_without_a_pair_are_refused(monkeypatch):
    """A guard that quietly stops guarding is worse than no guard.

    The antisymmetry test needs a -b for every +b. Given stations that have
    none it would compute over an empty set and admit everything, so the sweep
    is refused instead of returning numbers it cannot vouch for.
    """
    monkeypatch.setattr(
        aero, "_vlm_lateral",
        lambda plane, V, alpha, betas, mesh, x_cg: _sweep(0.00125),
    )
    with pytest.raises(ValueError, match="no .* pair"):
        aero.vlm_directional_check(
            {"x": object()}, 9.5, 3.0, 0.19, betas=(0.0, 2.0, 4.0)
        )
