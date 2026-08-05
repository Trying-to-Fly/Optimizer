"""Motor-mount study (MODEL_DETAILS 2.4): puller default (adopted 2026-07-24,
FINDINGS section 10); mass placement + declared installation effects; dv=None
fixture stays the spec pusher.

The pusher was RETIRED as a candidate on 2026-07-31 (user decision) after being
priced like-for-like: 110.66 min against the puller's 120.12, both landing on
SM exactly 0.0800. The pusher MODEL is deliberately kept and still tested below —
retiring a candidate must not quietly delete the ability to price it again."""


def test_mount_is_a_declared_discrete_option(sample_aircraft):
    assert sample_aircraft.motor_mount == "puller"  # adopted default
    # pullers only (user, 2026-07-31) — priced twice, lost twice
    assert sample_aircraft.discrete_options["motor_mount"] == ["puller"]
    # judged first: the mount is the biggest CG lever
    assert list(sample_aircraft.discrete_options)[0] == "motor_mount"


def test_the_pusher_can_still_be_priced(sample_aircraft):
    """Retired is not deleted. Putting it back in the list must be all it takes,
    so the mount attribute has to keep working for a value no longer studied."""
    sample_aircraft.motor_mount = "pusher"
    try:
        assert sample_aircraft.powertrain().prop.folding_derate < 1.0  # in-wake derate
        assert sample_aircraft.parasite_bodies(dict(sample_aircraft.DV_DEFAULTS))
    finally:
        sample_aircraft.motor_mount = "puller"


def test_motor_mass_rides_the_mount(sample_aircraft):
    """The mount decides which END of the aeroplane the motor is on; the
    GEOMETRY decides where on that end it can actually sit.

    This used to pin `nose_tip + 0.02`. That literal was written when the pod
    was a frozen 585 mm prism, and it survived the pod becoming a loft the
    optimizer shrinks — by 2026-08-05 it placed a 42 mm motor at a station where
    the champion's pod is 39.9 mm wide. The station now comes from
    `nose_split`, the same arithmetic as the motor-fit constraint, so the mass
    model and the packaging rows cannot disagree about where the motor is
    (tests/test_afterbody.py has the CG consequence).
    """
    d = dict(sample_aircraft.DV_DEFAULTS)
    p = sample_aircraft.pod_dims(d)
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    # parametric default = puller: motor in the nose, behind the bulkhead
    motor = next(e for e in sample_aircraft.fixed_equipment(d) if e.name == "motor_prop")
    split = sample_aircraft.nose_split(d)
    assert abs(motor.x_m - split["x_motor"]) < 1e-12
    # aft of the bulkhead by construction. NOT also "ahead of the bay": these
    # are the DECLARED DEFAULTS, whose 30 mm nose predates the `1.0 x d_eq`
    # floor and is deliberately infeasible against it, so at this vector the can
    # does overhang into the bay — which is exactly what the constraint exists
    # to drive out, and asserting otherwise here would be asserting that an
    # infeasible start is feasible.
    assert motor.x_m > split["x_face"]
    sample_aircraft.motor_mount = "pusher"
    try:
        motor = next(e for e in sample_aircraft.fixed_equipment(d) if e.name == "motor_prop")
        assert abs(motor.x_m - (x_tail + 0.08)) < 1e-12  # pusher: boom tip
    finally:
        sample_aircraft.motor_mount = "puller"


def test_fixture_keeps_spec_pusher_layout(sample_aircraft):
    """dv=None is the frozen spec plane — a pusher — regardless of the
    adopted parametric default (M1 validation continuity)."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    motor = next(e for e in sample_aircraft.fixed_equipment() if e.name == "motor_prop")
    assert abs(motor.x_m - (x_tail + 0.08)) < 1e-12
    bodies = sample_aircraft.parasite_bodies()
    assert bodies[0]["form_factor"] == 1.25  # frozen M1 baseline untouched


def test_installation_effects_declared(sample_aircraft):
    """Pusher pays the prop-in-wake derate; puller pays pod scrubbing drag."""
    d = dict(sample_aircraft.DV_DEFAULTS)
    pt_pull = sample_aircraft.powertrain()
    pod_pull = sample_aircraft.parasite_bodies(d)[0]
    sample_aircraft.motor_mount = "pusher"
    try:
        pt_push = sample_aircraft.powertrain()
        pod_push = sample_aircraft.parasite_bodies(d)[0]
    finally:
        sample_aircraft.motor_mount = "puller"
    # blade derate is 1.00 on measured folding data, so what is left in this
    # product IS the mount effect: the pusher's prop-in-wake 0.95, and nothing
    # for the puller (which pays on pod drag below instead)
    assert abs(pt_push.prop.folding_derate - 1.00 * 0.95) < 1e-12
    assert abs(pt_pull.prop.folding_derate - 1.00) < 1e-12
    assert abs(pod_pull["form_factor"] / pod_push["form_factor"] - 1.10) < 1e-9
    # wetted area itself is untouched — only the drag factor moves
    assert abs(pod_pull["wetted_area_m2"] - pod_push["wetted_area_m2"]) < 1e-12


def test_span_cap_lowered(sample_aircraft):
    """2.0 m projected cap (user decision 2026-07-24) bounds the span variable."""
    import aerosandbox as asb

    assert abs(sample_aircraft.span_cap_m - 2.0) < 1e-12
    opti = asb.Opti()
    dv = sample_aircraft.design_variables(opti)
    opti.subject_to(dv["span"] <= sample_aircraft.span_cap_m)


def test_prop_is_a_declared_discrete_option(sample_aircraft):
    """Prop pitch is priced by a study, not declared (user decision 2026-07-27).

    Judged straight after the mount, because the mount's installation derate
    composes into the prop's folding knockdown.
    """
    order = list(sample_aircraft.discrete_options)
    assert order.index("prop_choice") == order.index("motor_mount") + 1
    # spec incumbent — the KEY changed with the derived list (was "cam_11x6"),
    # the propeller did not: same table, same size, same derate (asserted in
    # test_incumbent_powertrain_is_unchanged)
    assert sample_aircraft.prop_choice == "ancf_11x6"
    assert set(sample_aircraft.discrete_options["prop_choice"]) == set(
        sample_aircraft.PROP_CANDIDATES
    )


def test_prop_candidates_are_measured_folding_and_within_the_airframe_limit(sample_aircraft):
    """The shortlist is now a RULE over the shipped catalogue, not a hand-list
    (2026-07-31, M5.3): every measured folding table inside the declared
    diameter limit. It spans manufacturers as well as sizes, which the 8-entry
    hand-list did not — a screen makes that affordable, so the confound the old
    single-family list controlled for is now controlled by the DATA being
    measured rather than by the family being one.

    What must still hold: every candidate is measured folding data carrying the
    same installation knockdown, each with its own table, and none past the
    airframe's declared diameter — so no candidate wins on a friendlier
    assumption, and none wins by being unbuildable."""
    from planeopt import propulsion

    original = sample_aircraft.prop_choice
    seen = {}
    try:
        for key in sample_aircraft.PROP_CANDIDATES:
            sample_aircraft.prop_choice = key
            prop = sample_aircraft.powertrain().prop
            table = propulsion.PropTable(prop.proxy_table)  # must actually resolve
            assert table.meta.get("folding") is True, f"{key} is not a folding prop"
            assert table.meta.get("measured") is True, f"{key} is not measured data"
            seen[key] = (prop.diameter_m, prop.folding_derate, prop.pitch_m, prop.proxy_table)
    finally:
        sample_aircraft.prop_choice = original

    n = len(sample_aircraft.PROP_CANDIDATES)
    assert n > 20, "a screened study should search the catalogue, not a shortlist"
    assert len({f for _, f, _, _ in seen.values()}) == 1  # one installation rule
    assert len({t for _, _, _, t in seen.values()}) == n  # each its own table
    assert len({d for d, _, _, _ in seen.values()}) > 1  # diameter is in play now
    # Nominal SIZES may now repeat across manufacturers — an 11x6 CAM folder and
    # an 11x6 Graupner folder are different propellers that happen to share a
    # label, and telling them apart is exactly what measured data is for. What
    # must not repeat is the TABLE, asserted above: two candidates backed by one
    # measurement would be the same prop entered twice.
    sizes = [(d, p) for d, _, p, _ in seen.values()]
    assert len(set(sizes)) < n, "expected some shared nominal sizes across makers"
    limit = sample_aircraft.prop_diameter_max_in * 0.0254
    assert max(d for d, _, _, _ in seen.values()) <= limit + 1e-9


def test_a_bigger_prop_carries_its_own_mass(sample_aircraft):
    """The whole reason diameter was pinned: a disc that arrives weightless is
    free thrust, and it sits on the longest lever the airframe has. The 11 in
    reference must still reproduce the frozen 190 g exactly, so no champion
    solved before 2026-07-30 moves."""
    ref = sample_aircraft.PROP_MASS_REF_DIAMETER_IN
    assert sample_aircraft.MOTOR_MASS_KG + sample_aircraft.prop_assembly_mass_kg(ref) == 0.190
    # the frozen spec fixture keeps the literal value whatever the study picked
    sample_aircraft.prop_choice = "ancf_14x12"
    frozen = next(e for e in sample_aircraft.fixed_equipment() if e.name == "motor_prop")
    assert frozen.mass_kg == 0.190

    # and a parametric design pays for what it chose
    d = dict(sample_aircraft.DV_DEFAULTS)
    big = next(e for e in sample_aircraft.fixed_equipment(d) if e.name == "motor_prop")
    sample_aircraft.prop_choice = "ancf_11x6"
    small = next(e for e in sample_aircraft.fixed_equipment(d) if e.name == "motor_prop")
    assert big.mass_kg > small.mass_kg + 0.020, "14 in must cost real grams over 11 in"
    assert small.mass_kg == 0.190


def test_a_prop_past_the_declared_airframe_limit_is_refused(sample_aircraft):
    """Declared, not predicted — but enforced, so a candidate past it cannot win
    a study and be adopted as a champion nobody agreed could be built."""
    import pytest

    assert all(
        c["diameter_in"] <= sample_aircraft.prop_diameter_max_in
        for c in sample_aircraft.PROP_CANDIDATES.values()
    )
    sample_aircraft.PROP_CANDIDATES["ancf_16x8"] = {
        "name": "too_big", "diameter_in": 16.0, "pitch_in": 8.0,
        "proxy_table": "uiuc_ancf_16x8", "blade_derate": 1.00,
    }
    try:
        sample_aircraft.prop_choice = "ancf_16x8"
        with pytest.raises(ValueError, match="prop_diameter_max_in"):
            sample_aircraft.powertrain()
    finally:
        del sample_aircraft.PROP_CANDIDATES["ancf_16x8"]


def test_incumbent_powertrain_is_unchanged(sample_aircraft):
    """The incumbent is still the spec's 11x6 CAM folder — but it is now backed
    by MEASURED data rather than an APC rigid table times a 0.95 guess.

    This deliberately replaces the old "must not move the spec plane" assertion:
    the spec plane moved on purpose on 2026-07-29, and it had to. The derate is
    the point — a measured folding table already contains the folding penalty, so
    applying the rigid-blade proxy derate on top charged it twice."""
    p = sample_aircraft.powertrain().prop
    # the display name now comes from the table's own metadata rather than a
    # hand-written string — same propeller, named by the data that measured it
    assert p.name == "Aeronaut CAM Folding 11x6"
    assert abs(p.diameter_m - 0.2794) < 1e-12
    assert abs(p.pitch_m - 0.1524) < 1e-12
    assert p.proxy_table == "uiuc_ancf_11x6"
    # 1.00 blade x 1.00 puller mount: no proxy derate on measured folding data
    assert abs(p.folding_derate - 1.00) < 1e-12
