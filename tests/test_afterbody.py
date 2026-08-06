"""Fuselage afterbody drag, the fineness ceiling, and the motor-fit rows.

Until 2026-08-05 the complete information path from fuselage geometry to the
objective was four numbers per body — wetted area, length, fineness, volume — so
**any two fuselages agreeing on those four were identical to the optimizer, to
the last digit.** A well-faired body and a badly separated one scored the same.

The 2026-08-05 champion was exploiting exactly that: a 20.1 degree closure
half-angle through the middle of its boat-tail, charged nothing, with `pod_tail`
sitting exactly on the `1.8 x d_eq` floor that stood in for the missing physics.
These tests pin the term that replaces the proxy (docs/FUSELAGE_DRAG_PLAN.md,
MODEL_DETAILS 7.3), the fineness ceiling shipped with it so the exploit cannot
simply move from the tail cone to the whole pod, and the packaging rows that
stop the optimizer shrinking the pod below its own motor.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from planeopt import aero, fuselage
from planeopt.cli import load_aircraft

# The champion pod: 54.0 x 69.9 mm, so 61.4 mm equivalent diameter, with the end
# cap sized to pass the 12 mm boom through its NARROW dimension. tail_len is what
# the tests vary.
POD_W, POD_H = 0.068 * 0.7941176, 0.088 * 0.7941176
D_EQ, R_CAP = (POD_W * POD_H) ** 0.5, 0.012 / POD_W


@pytest.fixture(scope="module")
def sample():
    return load_aircraft(Path("aircraft/vtail_sample"))[0]


@pytest.fixture(scope="module")
def champion_dv(sample):
    """The 2026-08-05 champion's design vector, as the plan's own worked example.

    Inline rather than read from `runs/`, so the test cannot be silently
    disarmed by an artifact being moved, and so the numbers a reader wants to
    check against docs/FUSELAGE_DRAG_PLAN.md section 6 are visible here.
    """
    return dict(sample.DV_DEFAULTS) | {
        "pod_nose": 0.06143000680593114,
        "pod_bay": 0.2086124295920368,
        "pod_tail": 0.11057402025103502,
        "pod_xs": 0.7941176370653477,
        "pod_bay_end": 0.5406124435812831,
        "tail_arm": 0.9416234060752777,
    }


# --------------------------------------------------------------- the term


def test_an_attached_afterbody_is_charged_nothing():
    """Below the separation threshold the term must vanish, not merely shrink.

    `smooth_floor` is a hyperbola, so "exactly zero" means "smaller than the
    smallest drag area anyone could care about" — here 1e-12 m^2, against a
    champion body drag area of ~9e-4 m^2, i.e. nine orders down.
    """
    long_tail = 0.40  # theta_max ~ 5.6 deg
    terms = fuselage.afterbody_terms(D_EQ, long_tail, R_CAP)
    assert terms["afterbody"]["theta_max_deg"] < fuselage.THETA_SEP_DEG
    assert terms["base_drag_area_m2"] < 1e-12
    assert terms["base_drag_area_m2"] >= 0.0


def test_the_closed_form_max_angle_matches_the_actual_loft():
    """The angle is derived from the Hermite boat-tail on paper; the loft is
    where it is actually built. If `loft()`'s profile ever drifts from
    `1 - (1-r_cap)(3u^2 - 2u^3)`, this is what notices — the closed form would
    otherwise keep answering about a shape the aircraft no longer has.

    Finite-differenced off the loft's OWN stations, in the d_eq-equivalent
    convention: width and height both scale by r(u), so sqrt(w*h)/2 is the
    equivalent radius at every station whatever the section aspect ratio.
    """
    tail_len, n = 0.12, 400
    loft = fuselage.loft(
        0.06, 0.20, tail_len, POD_W, POD_H, n_tail=n, r_cap=R_CAP
    )
    tail = loft.xsecs[-(n + 1):]  # bay shoulder through end cap
    x = np.array([float(s.xyz_c[0]) for s in tail])
    r_eq = np.array([float(s.width * s.height) ** 0.5 / 2 for s in tail])
    tan_local = -np.diff(r_eq) / np.diff(x)

    closed = fuselage.afterbody_terms(D_EQ, tail_len, R_CAP)["afterbody"]["theta_max_deg"]
    assert math.degrees(math.atan(tan_local.max())) == pytest.approx(closed, rel=2e-3)
    # and the maximum really is at mid-cone, which is what makes it closed-form
    assert 0.49 < (x[tan_local.argmax()] - x[0] + 0.5 * np.diff(x)[0]) / tail_len < 0.51


def test_the_charge_falls_monotonically_as_the_tail_lengthens():
    """The gradient this whole change exists to create. `pod_tail` sat on its
    floor because lengthening the boat-tail bought the optimizer nothing; every
    millimetre must now buy something, over the whole range and not just near
    the champion."""
    lengths = np.linspace(0.05, 0.35, 60)
    charge = [fuselage.afterbody_terms(D_EQ, L, R_CAP)["base_drag_area_m2"] for L in lengths]
    assert all(b < a for a, b in zip(charge, charge[1:])), "not strictly decreasing"
    assert charge[0] > 100 * charge[-1], "the range is too flat to steer a solve"


def test_the_charge_is_continuous_across_onset():
    """The hidden discontinuity, and the reason for the ramp: at onset the
    separation station is u* = 1/2, where the radius fraction is ~0.6 rather
    than r_cap — so an unramped charge would JUMP from zero to most of the
    cross-section the instant the threshold was crossed. IPOPT cannot walk
    across that.

    Densely sampled either side; the largest step between neighbouring samples
    must stay far below the charge's own scale.
    """
    # tail lengths that put theta_max within a couple of degrees of 12
    tan_sep = math.tan(math.radians(fuselage.THETA_SEP_DEG))
    at = lambda deg: 1.5 * (D_EQ / 2) * (1 - R_CAP) / math.tan(math.radians(deg))
    lengths = np.linspace(at(15.0), at(9.0), 400)
    charge = np.array(
        [fuselage.afterbody_terms(D_EQ, L, R_CAP)["base_drag_area_m2"] for L in lengths]
    )
    assert charge[0] > 0 and charge[-1] < 1e-6 * charge[0]
    assert np.max(np.abs(np.diff(charge))) < 0.02 * charge.max(), "step at onset"
    # ...and the ramp really is what does it: lambda, not the area, goes to zero
    onset = fuselage.afterbody_terms(D_EQ, at(12.0), R_CAP)["afterbody"]
    assert onset["lambda"] < 1e-3
    assert onset["r_sep"] > 0.5, "u* -> 1/2 at onset, so the raw area does NOT vanish"
    assert tan_sep > 0  # the threshold is the thing being crossed


def test_the_terms_stay_finite_on_iterates_outside_the_box():
    """An interior-point method reaches its solution THROUGH infeasible points,
    and `tail_len` is a difference of design variables that enters a
    denominator. One NaN in a constraint row fails the SOLVE rather than the
    point — that is the boom-NaN lesson (HANDOFF issue 3, 52 warnings inside
    one pusher solve), and it is why nothing here uses a bare `max`.

    Built symbolically through CasADi and evaluated on a grid that deliberately
    includes zero and negative tail lengths, threshold-crossing angles, and a
    socket larger than the body it sockets into.
    """
    import casadi as cas

    # raw symbols, not `Opti.variable`: AeroSandbox hands back a SCALED
    # expression, and `cas.jacobian` refuses anything but pure symbols
    d_eq, tail, r_cap = (cas.MX.sym(n) for n in ("d_eq", "tail", "r_cap"))
    terms = fuselage.afterbody_terms(d_eq, tail, r_cap)
    stacked = cas.vertcat(
        terms["base_drag_area_m2"],
        *[terms["afterbody"][k] for k in ("theta_max_deg", "u_star", "r_sep", "lambda")],
    )
    f = cas.Function("t", [d_eq, tail, r_cap], [stacked, cas.jacobian(stacked, tail)])

    grid = [
        (de, tl, rc)
        for de in (0.02, 0.06143, 0.20)
        for tl in (-0.5, -1e-9, 0.0, 1e-9, 0.001, 0.11, 0.9)
        for rc in (0.0, 0.05, R_CAP, 0.9, 1.0, 1.5)
    ]
    for de, tl, rc in grid:
        value, grad = f(de, tl, rc)
        assert np.all(np.isfinite(np.array(value))), f"non-finite at {(de, tl, rc)}"
        assert np.all(np.isfinite(np.array(grad))), f"non-finite gradient at {(de, tl, rc)}"


# --------------------------------------------------------------- the seam


def test_base_drag_is_additive_and_escapes_the_excrescence_factor():
    """`EXCRESCENCE` pays for saddle steps, hatch lips, wires and hinge gaps on a
    WETTED SURFACE. A base has none of those, so the base term is added outside
    it — and a body without the key must leave the buildup bit-identical, which
    is what keeps every frozen dv=None fixture valid."""
    plain = {"name": "b", "wetted_area_m2": 0.10, "length_m": 0.50,
             "form_factor": 1.2, "volume_m3": 1e-3}
    based = dict(plain) | {"base_drag_area_m2": 3.15e-4}
    s_ref, V = 0.40561, 9.5

    without = aero.body_cd0([plain], V, s_ref)
    with_key = aero.body_cd0([based], V, s_ref)
    # absent key -> not merely close, IDENTICAL
    assert aero.body_cd0([dict(plain)], V, s_ref) == without
    # present -> exactly the drag area, referenced to s_ref, with NO 1.08 on it
    assert with_key - without == pytest.approx(3.15e-4 / s_ref, rel=1e-12)
    assert with_key - without != pytest.approx(aero.EXCRESCENCE * 3.15e-4 / s_ref, rel=1e-6)


def test_the_frozen_baseline_is_untouched(sample):
    """Validation continuity: `dv=None` returns hard-coded M1 dicts that never
    gain the new key, so the 0.183 m^2 pod's drag is exactly what it was."""
    from planeopt import geometry

    bodies = sample.parasite_bodies()
    assert not any("base_drag_area_m2" in b for b in bodies)
    hand = sum(
        0.074 / (1.225 * 9.5 * geometry.smooth_floor(b["length_m"]) / 1.81e-5) ** 0.2
        * b["form_factor"] * b["wetted_area_m2"]
        for b in bodies
    )
    assert aero.body_cd0(bodies, 9.5, 0.40561) == pytest.approx(
        aero.EXCRESCENCE * hand / 0.40561, rel=1e-12
    )


def test_the_end_cap_is_the_boom_socket(sample):
    """The inconsistency this change closed: the boom is 12 mm OD and the cap it
    plugs into was a flat 12% of d_eq — 7.4 mm at the champion, i.e. the boom
    was LARGER than its own socket. In pod-boom the cap IS the socket; the
    integrated topology keeps the tail-block joint convention.

    Sized on the NARROW dimension. Against d_eq the cap face comes out
    10.5 x 13.7 mm at the champion and a round 12 mm tube still will not pass
    through it — the fraction would have been made self-consistent in the
    equivalent-diameter convention while leaving the physical fault in place.
    """
    d = dict(sample.DV_DEFAULTS)
    cap = sample._pod_loft(d).xsecs[-1]
    # The requirement is "the tube passes through", not an exact identity: the
    # narrow dimension comes from a SMOOTH min (`pod_wh` is a design variable
    # now, so `min` would be a branch), which under-reports by tau/2 and so
    # opens the socket by ~20 um. Erring toward a larger hole is the safe
    # direction; erring the other way would be a boom that does not fit.
    assert float(cap.width) >= sample.BOOM_OD_M
    assert float(cap.width) == pytest.approx(sample.BOOM_OD_M, abs=1e-4)
    assert float(cap.height) > sample.BOOM_OD_M  # the wide axis has room to spare
    # the cap is now fully occluded by construction, so base drag can ONLY ever
    # arrive through separation — one mechanism, not two
    p = sample.pod_dims(d)
    assert p["r_cap"] == pytest.approx(sample.BOOM_OD_M / p["d_min"])

    sample.fuselage_topology = "integrated"
    try:
        assert sample.pod_dims(dict(sample.DV_DEFAULTS))["r_cap"] == 0.12
    finally:
        sample.fuselage_topology = "pod_boom"


def test_the_pod_body_carries_the_term_and_the_diagnostics(sample, champion_dv):
    """What `solve.run` reads at the champion. The numbers are the worked
    example in docs/FUSELAGE_DRAG_PLAN.md section 6 — estimated BEFORE the code
    existed, so agreement is a real check on the implementation rather than a
    snapshot of it. They land ~6% below the plan's, all of it the wider end cap
    the socket fix demands (18.0 degrees against the plan's 18.5).
    """
    pod = sample.parasite_bodies(champion_dv)[0]
    ab = pod["afterbody"]
    assert ab["theta_max_deg"] == pytest.approx(17.96, abs=0.05)
    assert ab["u_star"] == pytest.approx(0.2067, abs=0.005)
    assert ab["r_sep"] == pytest.approx(0.914, abs=0.005)
    assert ab["lambda"] == pytest.approx(0.802, abs=0.005)
    assert ab["area_charged_m2"] == pytest.approx(2.33e-3, rel=0.02)
    assert pod["base_drag_area_m2"] == pytest.approx(2.97e-4, rel=0.02)
    assert pod["fineness"] == pytest.approx(6.20, abs=0.01)
    # ~34% ON TOP of what the buildup used to charge the bodies — four times the
    # +8% the scoping hinge suggested, because the effective-base form charges
    # the area at the SEPARATION station, which at 18 degrees is most of the
    # cross-section. Decisive, not marginal, and that is the model being honest.
    bodies = sample.parasite_bodies(champion_dv)
    s_ref = 0.40561
    total = aero.body_cd0(bodies, 9.5, s_ref) * s_ref
    assert pod["base_drag_area_m2"] / (total - pod["base_drag_area_m2"]) == pytest.approx(
        0.34, abs=0.02
    )


# ------------------------------------------------- the section shape (pod_wh)


def test_the_spec_section_is_still_exactly_the_default(sample):
    """`pod_wh` was unlocked on 2026-08-05, and unlocking a variable must not
    move the aeroplane: the spec's 68 x 88 has to remain reachable *exactly*, or
    every number this project has ever recorded becomes a number about a
    different pod."""
    p = sample.pod_dims(dict(sample.DV_DEFAULTS))
    assert p["w"] == pytest.approx(0.068, rel=1e-12)
    assert p["h"] == pytest.approx(0.088, rel=1e-12)
    assert sample.DV_DEFAULTS["pod_wh"] == pytest.approx(0.068 / 0.088, rel=1e-12)


def test_the_ratio_is_orthogonal_to_the_size(sample):
    """`pod_xs` sizes the section and `pod_wh` shapes it, and the two must not
    interfere: `d_eq` is what the proportion floors, the fineness ceiling and the
    entire afterbody term are written against, so a ratio that moved it would
    silently re-scale six constraints while claiming to change only shape."""
    base = sample.pod_dims(dict(sample.DV_DEFAULTS))["d_eq"]
    for wh in (0.65, 0.80, 1.0, 1.294, 1.55):
        p = sample.pod_dims(dict(sample.DV_DEFAULTS) | {"pod_wh": wh})
        assert p["d_eq"] == pytest.approx(base, rel=1e-12), f"d_eq moved at pod_wh={wh}"
        assert p["w"] * p["h"] == pytest.approx(base**2, rel=1e-12)
        # ...and the ratio really is the ratio
        assert p["w"] / p["h"] == pytest.approx(wh, rel=1e-9)


def test_the_objective_can_actually_see_the_ratio(sample, champion_dv):
    """The reason this stayed locked. HANDOFF: *do not widen the fuselage
    parameterization until the drag model can see shape* — a variable the
    objective is blind to is a flat manifold, which IPOPT handles badly, on a
    solve already peaking near 14.5 GB.

    It is no longer blind. At fixed `d_eq` a superellipse has least perimeter
    when square, so the loft's own wetted-area integral prices eccentricity —
    and the afterbody term reads the ratio too, through `r_cap` on the narrow
    dimension. Both effects must be present and they pull OPPOSITE ways, which
    is what makes this a trade rather than a slide to a bound.
    """
    def at(wh):
        dv = dict(champion_dv) | {"pod_wh": wh}
        b = sample.parasite_bodies(dv)[0]
        return b["wetted_area_m2"], b["base_drag_area_m2"]

    square_s, square_b = at(1.0)
    spec_s, spec_b = at(0.068 / 0.088)
    flat_s, flat_b = at(1.55)

    # wetted area is minimised at square, and the gradient is not noise
    assert square_s < spec_s < flat_s
    assert (flat_s - square_s) / square_s > 0.03
    # base drag pulls the other way: squaring widens the narrow dimension, so
    # r_cap shrinks, the boat-tail closes harder and the charge RISES
    assert square_b > spec_b > flat_b


def test_the_narrow_dimension_follows_the_ratio_whichever_way_it_tips(sample, champion_dv):
    """Width was the narrow dimension for every pod the aircraft could describe,
    and three places quietly relied on it — the boom socket, the bulkhead and the
    motor row. With the ratio free, a pod wider than it is tall is now reachable,
    and every one of those must switch to the height.

    Checked by mirroring: a 68 x 88 pod and an 88 x 68 pod are the same section
    turned on its side, so every derived quantity must agree exactly.
    """
    spec, mirrored = 0.068 / 0.088, 0.088 / 0.068
    tall = sample.pod_dims(dict(champion_dv) | {"pod_wh": spec})
    wide = sample.pod_dims(dict(champion_dv) | {"pod_wh": mirrored})
    assert tall["w"] == pytest.approx(wide["h"], rel=1e-9)
    assert tall["d_min"] == pytest.approx(wide["d_min"], rel=1e-9)
    assert tall["r_cap"] == pytest.approx(wide["r_cap"], rel=1e-9)

    for key in ("cone_len", "usable_nose", "x_motor"):
        a = sample.nose_split(dict(champion_dv) | {"pod_wh": spec})[key]
        b = sample.nose_split(dict(champion_dv) | {"pod_wh": mirrored})[key]
        assert a == pytest.approx(b, rel=1e-9), f"{key} is not mirror-symmetric"

    a = sample.parasite_bodies(dict(champion_dv) | {"pod_wh": spec})[0]
    b = sample.parasite_bodies(dict(champion_dv) | {"pod_wh": mirrored})[0]
    assert a["wetted_area_m2"] == pytest.approx(b["wetted_area_m2"], rel=1e-9)
    assert a["base_drag_area_m2"] == pytest.approx(b["base_drag_area_m2"], rel=1e-9)


def test_squaring_the_section_relieves_the_motor_without_growing_the_pod(sample, champion_dv):
    """What unlocking the ratio actually buys, and why it was worth doing now.

    The motor-fit row was going to be paid for with `pod_xs` — growing the whole
    pod, and its wetted area with it. The ratio is the cheaper currency: at fixed
    `d_eq` the nose gains motor room purely by squaring up.
    """
    spec = sample.nose_split(dict(champion_dv))["usable_nose"]
    square = sample.nose_split(dict(champion_dv) | {"pod_wh": 1.0})["usable_nose"]
    assert square > spec + 0.010, "squaring buys less than 10 mm of motor bay"
    # and it does it without touching the size the drag terms are written against
    assert sample.pod_dims(dict(champion_dv) | {"pod_wh": 1.0})["d_eq"] == pytest.approx(
        sample.pod_dims(dict(champion_dv))["d_eq"], rel=1e-12
    )


# --------------------------------------------------------------- the rows


def _rows(aircraft, dv_overrides: dict):
    """(labelled g rows, their values) at one design vector.

    Constraints are built symbolically and evaluated at the initial point, which
    is the only way to see what the SOLVER sees — a row that reads correctly in
    the source and never reaches `opti.g` is the failure mode being guarded
    against (the 2026-07-30 infeasibility short-circuit shipped green and did
    nothing for 130 minutes a run).
    """
    import aerosandbox as asb

    from planeopt.solve import _ConstraintLabels

    opti = asb.Opti()
    dv = aircraft.design_variables(opti, dict(aircraft.DV_DEFAULTS) | dv_overrides)
    labels = _ConstraintLabels(opti)
    try:
        aircraft.geometry_constraints(opti, dv, 9.5)
    finally:
        labels.stop()
    # at the INITIAL point: `opti.debug.value` refuses to answer on a stack that
    # has never been solved, and solving here would cost minutes to learn
    # nothing about the rows themselves
    values = np.array(opti.value(opti.g, opti.initial())).ravel()
    return labels.as_dict(), values


def _row_matching(aircraft, dv_overrides: dict, needle: str) -> tuple[int, float]:
    labels, values = _rows(aircraft, dv_overrides)
    hits = [r for r, src in labels.items() if needle in src]
    assert len(hits) == 1, f"expected exactly one {needle!r} row, got {len(hits)}"
    return hits[0], values[hits[0]]


def test_the_fineness_row_reaches_the_solver_and_is_dimensionless(sample, champion_dv):
    """`fineness_max` is declared beside `lift_to_drag_max` and must be enforced,
    not documented. Dimensionless per the standing rule — a constraint vector
    spanning ten decades is what made the hard corners take hundreds of
    iterations (FINDINGS 14.5)."""
    row, value = _row_matching(sample, champion_dv, "fineness_max")
    assert value == pytest.approx(6.196 / 8.0, rel=1e-3)
    assert 0.1 < value < 10, "row is not of order 1 — check the scaling"
    # the champion is INSIDE the ceiling, so shipping this cannot invalidate it
    assert value < 1.0

    # and the attribute is what sets it, rather than a literal in the method
    variant = type(sample)()
    variant.fineness_max = 4.0
    _, halved = _row_matching(variant, champion_dv, "fineness_max")
    assert halved / value == pytest.approx(2.0, rel=1e-9)


def test_the_fineness_ceiling_is_not_imposed_on_the_integrated_topology(sample):
    """It would not BOUND that candidate, it would delete it: the integrated
    body runs to the tail block, so its length is set by `tail_arm` and it sits
    at f = 14.7 at the declared defaults. The only way to satisfy f <= 8 there
    is a maximally fat pod on a minimum tail arm — a priced alternative in the
    topology study would quietly become a garbage design that still converged.
    """
    sample.fuselage_topology = "integrated"
    try:
        p = sample.pod_dims(dict(sample.DV_DEFAULTS))
        assert p["length"] / p["d_eq"] == pytest.approx(14.7, abs=0.1)
        labels, _ = _rows(sample, {})
        assert not any("fineness_max" in src for src in labels.values())
    finally:
        sample.fuselage_topology = "pod_boom"


def test_the_motor_has_to_fit_inside_the_nose(sample, champion_dv):
    """A pod that cannot hold its own motor is not a cheaper aeroplane.

    Nothing checked this until 2026-08-05 and the optimizer had been shrinking
    the pod section for runs: at the champion the nose offers 25.8 mm of
    can-width room for a 51 mm can. The row asserts nothing about HOW the motor
    is mounted — the loft is the outer mould line, and the claim is only that
    the cylinder fits inside it, ahead of the bay.
    """
    motor = sample.COMPONENT_ENVELOPES["motor"]
    row, value = _row_matching(sample, champion_dv, "usable_nose")
    p = sample.pod_dims(champion_dv)
    can_w = motor["diameter"] + 2 * sample.POD_WALL_CLEARANCE
    usable = champion_dv["pod_nose"] * math.sqrt(1 - (can_w / p["w"]) ** 2)
    assert usable == pytest.approx(0.0258, abs=1e-4)
    # rel 1e-5, not tighter: the row carries `smooth_floor` so an iterate with a
    # section narrower than the can cannot produce sqrt(negative), and the hinge
    # costs 4e-6 relative here — 0.1 um on a 25.8 mm dimension
    assert value == pytest.approx(usable / motor["length"], rel=1e-5)
    assert value < 1.0, "the champion should FAIL this row — that is the finding"

    # and it is satisfiable: a pod at the spec section, with the nose its own
    # `1.0 x d_eq` floor already demands, clears it
    fatter = dict(champion_dv) | {"pod_xs": 1.0}
    fatter["pod_nose"] = sample.pod_dims(fatter)["d_eq"]
    _, ok = _row_matching(sample, fatter, "usable_nose")
    assert ok > 1.0


def test_the_nosecone_is_named_and_its_station_derived(sample, champion_dv):
    """The loft runs to a 0.1 mm point because it is the OUTER MOULD LINE — pod
    plus the nosecone that completes it. Nobody builds that, and until 2026-08-05
    no artifact said which part was which: the builder got a pointed body with
    no cut station and no opening diameter.

    The split is derived rather than chosen — the one station where the interior
    first clears the can — so it cannot drift from the constraint that keeps the
    motor fitting, because it IS that constraint read backwards.
    """
    split = sample.nose_split(champion_dv)
    motor = sample.COMPONENT_ENVELOPES["motor"]
    p = sample.pod_dims(champion_dv)

    # the bulkhead is exactly wide enough for the can plus its walls...
    assert split["face_w"] == pytest.approx(
        motor["diameter"] + 2 * sample.POD_WALL_CLEARANCE, rel=1e-5
    )
    # ...and the hole in it is the can
    assert split["opening"] == motor["diameter"]
    # nosecone + motor bay = the whole nose, with nothing unaccounted for
    assert split["cone_len"] + split["usable_nose"] == pytest.approx(
        champion_dv["pod_nose"], rel=1e-9
    )
    assert split["x_face"] == pytest.approx(p["nose_tip"] + split["cone_len"], rel=1e-9)
    assert split["cone_len"] == pytest.approx(0.0356, abs=2e-4)

    # the constraint and the report are the SAME arithmetic, not two copies
    _, row = _row_matching(sample, champion_dv, "usable_nose")
    assert row == pytest.approx(split["usable_nose"] / motor["length"], rel=1e-9)


def test_the_motor_rides_where_the_nose_can_hold_it(sample, champion_dv):
    """It was a flat `nose_tip + 0.02` — a station where the champion's pod is
    39.9 mm wide, i.e. a place a 42 mm motor cannot be. Harmless when the pod
    was a frozen 585 mm prism; not once the loft started shrinking.

    Moves the can's CG **41 mm aft** at the champion, which on a 190 g
    motor+prop group is ~4 mm of aircraft CG — on a design whose `x_battery` is
    pinned at its aft limit with the static margin exactly on its floor. It
    moves CG in the direction this aeroplane has been starved of.
    """
    from planeopt import massmodel

    split = sample.nose_split(champion_dv)
    p = sample.pod_dims(champion_dv)
    motor_pm = next(
        m for m in sample.fixed_equipment(champion_dv) if m.name == "motor_prop"
    )
    assert motor_pm.x_m == pytest.approx(split["x_motor"], rel=1e-9)
    assert motor_pm.x_m - (p["nose_tip"] + 0.02) == pytest.approx(0.041, abs=1e-3)
    # it sits behind the bulkhead — the only invariant that holds at a vector
    # which does not yet satisfy the motor-fit row (this champion predates it)
    assert motor_pm.x_m > split["x_face"]
    assert p["nose_tip"] < split["x_face"]

    # the CG delta is the point, and it is what the old placement was hiding
    plane = sample.geometry(champion_dv)
    new = massmodel.totals(massmodel.build(sample, plane, champion_dv)[0])
    real_split = sample.nose_split
    sample.nose_split = lambda d: dict(
        real_split(d), x_motor=sample.pod_dims(d)["nose_tip"] + 0.02
    )
    try:
        old = massmodel.totals(massmodel.build(sample, plane, champion_dv)[0])
    finally:
        sample.nose_split = real_split
    assert new["x_cg_m"] - old["x_cg_m"] == pytest.approx(0.0043, abs=5e-4)
    assert new["auw_kg"] == pytest.approx(old["auw_kg"], rel=1e-12), "mass must NOT move"


def test_the_builder_is_told_which_part_is_which(sample, champion_dv):
    """A derived split nobody can read is the same as no split. Both the CAD
    brief and the manufacturing sheet must name the nosecone as its own part —
    the parts list had a pod, a boom and two spars, and no fairing."""
    brief = sample.design_brief(champion_dv)
    nose = next(v for k, v in brief.items() if "NOSECONE" in k)
    assert "36 mm" in nose["NOSECONE — fairing, nose tip to bulkhead"]
    assert "42 mm" in nose["BULKHEAD — pod front face"]
    assert "opening" in nose["BULKHEAD — pod front face"]

    sheet = sample.manufacturing(champion_dv)
    parts = next(v for k, v in sheet.items() if k.startswith("Nose parts"))
    assert "nosecone" in " ".join(parts).lower()
    assert "42 mm" in parts["pod front bulkhead"]

    # a pusher has no nose fairing to print, and must not be handed one
    sample.motor_mount = "pusher"
    try:
        assert not any(k.startswith("Nose parts") for k in sample.manufacturing(champion_dv))
        pusher_nose = next(v for k, v in sample.design_brief(champion_dv).items()
                           if "NOSECONE" in k)
        assert "boom tip" in pusher_nose["note"]
    finally:
        sample.motor_mount = "puller"


def test_the_motor_envelope_is_declared_data(sample, champion_dv):
    """Swap the motor and one dict entry changes — the constraint must read the
    envelope, not a literal."""
    variant = type(sample)()
    variant.COMPONENT_ENVELOPES = dict(sample.COMPONENT_ENVELOPES) | {
        "motor": {"diameter": 0.042, "length": 0.102}
    }
    _, base = _row_matching(sample, champion_dv, "usable_nose")
    _, longer = _row_matching(variant, champion_dv, "usable_nose")
    assert base / longer == pytest.approx(2.0, rel=1e-9)


def test_the_run_says_what_the_afterbody_cost_it(sample, champion_dv):
    """The artifact half. A term that changes every objective and that nobody
    can see in the report is the shape of defect this project keeps finding:
    the 2026-08-05 audit turned up seven things a converged run was wrong about,
    none of them in its numbers and all of them in its claims.

    Built the way `solve.optimize` builds it, so this covers the plumbing and
    not only the template.
    """
    import re
    from types import SimpleNamespace

    from planeopt.report import html

    pod = sample.parasite_bodies(champion_dv)[0]
    bodies = sample.parasite_bodies(champion_dv)
    s_ref = 0.40561
    total = aero.body_cd0(bodies, 9.5, s_ref) * s_ref
    ab = {k: float(v) for k, v in pod["afterbody"].items()}
    ab["fineness"] = float(pod["fineness"])
    ab["share_of_body_drag"] = ab["base_drag_area_m2"] / total

    result = SimpleNamespace(
        aircraft="x", mission="m", objective="endurance", status="s", created="c",
        geometry={}, masses={}, constraints={}, notes=[], performance={},
        diagnostics={"afterbody": ab},
    )
    section = re.search(r"<h2>Afterbody.*?</table>", html.render(result), re.DOTALL)
    assert section, "the report dropped the afterbody block entirely"
    text = section.group(0)
    assert "18.0°" in text and "separated" in text  # the verdict, not just a number
    assert "12°" in text                            # against what threshold
    assert "6.20" in text                           # fineness, so a needle shows
    assert "25%" in text                            # its share of body drag
    # and a run whose afterbody is attached must say THAT, rather than nothing
    attached = dict(ab) | {"theta_max_deg": 9.0, "base_drag_area_m2": 0.0}
    result.diagnostics = {"afterbody": attached}
    assert "attached" in html.render(result)


def test_a_pusher_needs_no_nose_room(sample, champion_dv):
    """The mount hangs the motor off the boom tip, so the nose rows would be
    charging for a volume nothing occupies. Pusher is a retired CANDIDATE, not
    deleted machinery — putting it back in `discrete_options` re-opens the
    question, and it must not re-open it against the wrong constraint set."""
    sample.motor_mount = "pusher"
    try:
        labels, _ = _rows(sample, champion_dv)
        assert not any("usable_nose" in src for src in labels.values())
    finally:
        sample.motor_mount = "puller"
