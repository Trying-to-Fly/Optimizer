"""Motor-mount study (MODEL_DETAILS 2.4): puller default (adopted 2026-07-24,
FINDINGS section 10) with the spec pusher as a re-priced candidate; mass
placement + declared installation effects; dv=None fixture stays the spec
pusher."""

import math


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
    assert abs(pt_push.prop.folding_derate - 0.95 * 0.95) < 1e-12
    assert abs(pt_pull.prop.folding_derate - 0.95) < 1e-12
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
