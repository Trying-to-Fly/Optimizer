"""Motor-mount study (MODEL_DETAILS 2.4): puller default (adopted 2026-07-24,
FINDINGS section 10) with the spec pusher as a re-priced candidate; mass
placement + declared installation effects; dv=None fixture stays the spec
pusher."""


def test_mount_is_a_declared_discrete_option(sample_aircraft):
    assert sample_aircraft.motor_mount == "puller"  # adopted default
    assert sample_aircraft.discrete_options["motor_mount"] == ["puller", "pusher"]
    # judged first: the mount is the biggest CG lever
    assert list(sample_aircraft.discrete_options)[0] == "motor_mount"


def test_motor_mass_rides_the_mount(sample_aircraft):
    d = dict(sample_aircraft.DV_DEFAULTS)
    p = sample_aircraft.pod_dims(d)
    x_tail = 0.390 + 0.25 * 0.201 + d["tail_arm"]
    # parametric default = puller: motor in the nose
    motor = next(e for e in sample_aircraft.fixed_equipment(d) if e.name == "motor_prop")
    assert abs(motor.x_m - (p["nose_tip"] + 0.02)) < 1e-12
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
    assert sample_aircraft.prop_choice == "cam_11x6"  # spec incumbent
    assert set(sample_aircraft.discrete_options["prop_choice"]) == set(
        sample_aircraft.PROP_CANDIDATES
    )


def test_prop_candidates_differ_only_in_pitch(sample_aircraft):
    """Same diameter and knockdown, so the study isolates pitch. Diameter keeps
    the 190 g motor_prop point mass honest (it is not a function of diameter yet);
    the shared knockdown keeps no candidate advantaged by a friendlier
    installation assumption.

    Since 2026-07-29 every candidate is one MEASURED Aero-Naut CAM folding
    propeller, so blade section is controlled too — the confound that existed
    while the 11x6 rung was an APC sport blade is gone."""
    from planeopt import propulsion

    seen = {}
    for key in sample_aircraft.PROP_CANDIDATES:
        sample_aircraft.prop_choice = key
        prop = sample_aircraft.powertrain().prop
        table = propulsion.PropTable(prop.proxy_table)  # must actually resolve
        assert table.meta.get("folding") is True, f"{key} is not a folding prop"
        assert table.meta.get("measured") is True, f"{key} is not measured data"
        seen[key] = (prop.diameter_m, prop.folding_derate, prop.pitch_m, prop.proxy_table)
    n = len(sample_aircraft.PROP_CANDIDATES)
    assert len({(d, f) for d, f, _, _ in seen.values()}) == 1  # one family
    assert len({p for _, _, p, _ in seen.values()}) == n  # one pitch each
    assert len({t for _, _, _, t in seen.values()}) == n  # each with its own table


def test_incumbent_powertrain_is_unchanged(sample_aircraft):
    """The incumbent is still the spec's 11x6 CAM folder — but it is now backed
    by MEASURED data rather than an APC rigid table times a 0.95 guess.

    This deliberately replaces the old "must not move the spec plane" assertion:
    the spec plane moved on purpose on 2026-07-29, and it had to. The derate is
    the point — a measured folding table already contains the folding penalty, so
    applying the rigid-blade proxy derate on top charged it twice."""
    p = sample_aircraft.powertrain().prop
    assert p.name == "aeronaut_cam_11x6_folding"
    assert abs(p.diameter_m - 0.2794) < 1e-12
    assert abs(p.pitch_m - 0.1524) < 1e-12
    assert p.proxy_table == "uiuc_ancf_11x6"
    # 1.00 blade x 1.00 puller mount: no proxy derate on measured folding data
    assert abs(p.folding_derate - 1.00) < 1e-12
