"""Live solve frames (M5.4) — the writer, the wire format, and the latch.

The test that matters most in here is `test_a_poisoned_writer_cannot_fail_a_solve`.
Everything else is about a picture; that one is about a battery that runs for
hours not being lost to one.
"""

from __future__ import annotations

import logging

import pytest

from planeopt import liveframe

# A converged member, shaped exactly like `solve._solve_nlp`'s return value.
# Only the fields `liveframe` reads are here; it must not need the rest.
CONVERGED = {
    "V_ms": 11.0, "alpha_deg": 4.0, "deflection_deg": -1.2, "rpm": 3900.0,
    "objective_value": 118.24, "auw_kg": 1.58, "x_cg_m": 0.10,
    "static_margin": 0.08, "P_elec_w": 19.4, "motor_current_a": 1.7,
    "throttle_frac": 0.62, "drag_n": 0.72, "J": 0.55, "solve_minutes": 5.3,
}

#: `cl_max ~ A + B*ln(Re)` for a low-Re airfoil, as `aero.clmax_log_fit` returns
#: and `_solve_nlp` reports in `clmax_ab_used`. Literal rather than fitted here
#: because fitting it costs a NeuralFoil sweep to test arithmetic that is not
#: about NeuralFoil — the tests that care about the fit itself live in test_aero.
CLMAX_AB = (0.19, 0.113)


@pytest.fixture()
def dv(sample_aircraft):
    return {k: float(v) for k, v in sample_aircraft.DV_DEFAULTS.items()}


def _member(tmp_path, aircraft, sub="live"):
    writer = liveframe.FrameWriter(tmp_path / sub, aircraft)
    return writer, writer.member("multistart", "nominal", 2, 24)


# --- wire format ---------------------------------------------------------


def test_an_iterate_frame_round_trips(tmp_path, sample_aircraft, dv):
    writer, member = _member(tmp_path, sample_aircraft)
    member.iterate(7, dv, {"V_ms": 11.0, "alpha_deg": 4.0}, {"inf_pr": 5.6e-2})

    (path,) = liveframe.frame_paths(writer.dir)
    frame = liveframe.read_frame(path)
    assert frame["schema"] == liveframe.SCHEMA
    assert frame["kind"] == "iterate"
    assert frame["iter"] == 7
    assert frame["member_index"] == [2, 24]
    assert frame["dv"]["span"] == pytest.approx(dv["span"])
    assert frame["scalars"]["inf_pr"] == pytest.approx(5.6e-2)
    # An iterate is deliberately colourless: colouring one would cost a
    # lifting-line run per IPOPT iteration.
    assert frame.get("color") is None


def test_quads_decode_back_to_metres(tmp_path, sample_aircraft, dv):
    """The integer wire format must survive the trip within its own resolution."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.iterate(0, dv, {}, {})
    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])

    quads = liveframe.quad_points(frame)
    assert len(quads) == len(frame["mesh"]["surface_of"])
    assert all(len(q) == 4 for q in quads)
    ys = [p[1] for q in quads for p in q]
    # Symmetric surfaces are meshed on BOTH sides, so the model straddles the
    # centreline — the viewer shows a whole aeroplane, not a half one.
    assert max(ys) == pytest.approx(-min(ys), abs=2e-4)
    # ... and reaches at least the wing semi-span (the canted winglet adds a
    # little more, which is exactly why the cap is applied winglet-inclusive).
    assert max(ys) >= dv["span"] / 2 - 2e-4
    assert max(ys) == pytest.approx(
        frame["geometry"]["span_projected_m"] / 2, abs=2e-4
    )


def test_a_candidate_frame_carries_every_scalar_and_the_stats(tmp_path, sample_aircraft, dv):
    writer, member = _member(tmp_path, sample_aircraft)
    member.candidate({**CONVERGED, "dv": dv})

    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])
    assert frame["kind"] == "candidate"
    assert frame["color"]["name"] == "cl"
    n_quads = len(frame["mesh"]["surface_of"])
    for name in ("cl", "gamma", "lift_per_span"):
        assert len(liveframe.scalar_values(frame, name)) == n_quads
    # The dropdown is free because all three ship: switching it must not need
    # the solver.
    assert frame["scalars"]["CL"] > 0
    assert frame["scalars"]["L_over_D"] > 1
    assert frame["mesh"]["outlines"], "the pod and boom should be drawn"


def test_a_candidate_frame_carries_the_stall_margin_for_the_wing_alone(
    tmp_path, sample_aircraft, dv
):
    """`cl_max` here is the WING root airfoil's fit. A tail is a different
    section, so it gets no number rather than a borrowed one."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.candidate({**CONVERGED, "dv": dv, "clmax_ab_used": CLMAX_AB})

    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])
    margins = liveframe.scalar_values(frame, "stall_margin")
    surfaces = frame["mesh"]["surface_of"]
    assert len(margins) == len(surfaces)
    assert [m is None for m in margins] == [s != 0 for s in surfaces]
    on_wing = [m for m in margins if m is not None]
    assert on_wing, "the wing itself must be covered"
    # A converged cruise point is nowhere near the section limit; a margin over 1
    # would mean the frame disagrees with the constraint the solve satisfied.
    assert 0.0 < min(on_wing) and max(on_wing) < 1.0


def test_without_a_cl_max_fit_there_is_no_stall_margin_rather_than_a_guessed_one(
    tmp_path, sample_aircraft, dv
):
    """Inventing a second cl_max would be a different limit from the solve's."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.candidate({**CONVERGED, "dv": dv})  # no clmax_ab_used

    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])
    assert liveframe.scalar_values(frame, "stall_margin") is None
    assert liveframe.scalar_values(frame, "cl"), "the other channels are unaffected"


def test_a_candidate_frame_carries_a_wake_and_a_lift_distribution(
    tmp_path, sample_aircraft, dv
):
    writer, member = _member(tmp_path, sample_aircraft)
    member.candidate({**CONVERGED, "dv": dv, "clmax_ab_used": CLMAX_AB})
    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])

    lines = liveframe.streamline_points(frame)
    assert len(lines) == liveframe.LIVE_STREAMLINE_SEEDS
    assert all(len(line) == liveframe.LIVE_STREAMLINE_STEPS for line in lines)
    # Streamlines are a WAKE: every one of them ends aft of where it started.
    # (Model axes put aft at +x.) A sign error here would draw the air blowing
    # off the leading edge and look, at a glance, entirely plausible.
    assert all(line[-1][0] > line[0][0] for line in lines)

    lift = liveframe.lift_overlay(frame)
    assert lift and len(lift["sticks"]) == len(lift["curve"])
    assert len(lift["elliptical"]) == len(lift["curve"])
    # The reference carries the same lift as the wing it is drawn against —
    # otherwise "same lift, same span" in the legend is just words.
    ys = [point[1] for point in lift["curve"]]
    assert lift["total_n"] > 0
    assert max(ys) - min(ys) > 0.5 * frame["geometry"]["span_m"]


def test_an_iterate_frame_carries_no_overlays(tmp_path, sample_aircraft, dv):
    """Both overlays need solved circulation. Reading it per IPOPT iteration is
    the 14.5 GB graph evaluation the whole design avoids (plan section 1.1)."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.iterate(3, dv, {}, {})

    frame = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])
    assert liveframe.streamline_points(frame) == []
    assert liveframe.lift_overlay(frame) is None


def test_the_timelapse_view_round_trips_and_travels_into_the_run(
    tmp_path, sample_aircraft, dv
):
    """Chosen before the run starts, so it has to outlive the live directory."""
    writer, member = _member(tmp_path, sample_aircraft)
    liveframe.write_view(writer.dir, {"view": "plan", "yaw_deg": 0.0})
    member.iterate(0, dv, {}, {})
    assert liveframe.read_view(writer.dir)["view"] == "plan"

    run_dir = tmp_path / "20260805T120000-run"
    run_dir.mkdir()
    dest = liveframe.relocate(writer.dir, run_dir)
    assert liveframe.read_view(dest)["view"] == "plan"
    assert not writer.dir.exists(), "the sidecar must not keep the directory alive"


def test_an_unreadable_view_sidecar_is_no_view_rather_than_an_error(tmp_path):
    (tmp_path / liveframe.VIEW_FILE).write_text("{not json", encoding="utf-8")
    assert liveframe.read_view(tmp_path) is None
    assert liveframe.read_view(tmp_path / "nowhere") is None


def test_strip_lift_integrates_to_the_lifting_lines_own_lift(sample_aircraft, dv):
    """The per-strip loads must be READ off the model, not paraphrased from it.

    `sum(lift_per_span * span)` differs from the run's L only by the profile
    drag's contribution to lift, which is a fraction of a percent. A wider gap
    means the reconstruction has stopped tracking what the solver saw.
    """
    import aerosandbox as asb

    from planeopt import aero

    plane = sample_aircraft.geometry(dv)
    ll = asb.LiftingLine(
        airplane=plane,
        op_point=asb.OperatingPoint(velocity=11.0, alpha=4.0),
        xyz_ref=[0.1, 0, 0],
        vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS,
    )
    run = ll.run()
    loads = liveframe.strip_loads(ll, 4.0, 11.0)

    import numpy as np

    span = np.linalg.norm(ll.vortex_bound_leg, axis=1)
    total = float(np.sum(np.array(loads["lift_per_span"]) * span))
    assert total == pytest.approx(float(run["L"]), rel=0.01)
    assert loads["induced_drag_n"] > 0


# --- ordering and durability --------------------------------------------


def test_filenames_sort_chronologically(tmp_path, sample_aircraft, dv):
    """Lexicographic order IS chronological order — the timelapse's contract."""
    writer, member = _member(tmp_path, sample_aircraft)
    for i in range(12):
        member.iterate(i, dv, {}, {})

    names = [p.name for p in liveframe.frame_paths(writer.dir)]
    assert names == sorted(names)
    iters = [liveframe.read_frame(p)["iter"] for p in liveframe.frame_paths(writer.dir)]
    assert iters == list(range(12))


def test_the_sequence_resumes_after_a_pause(tmp_path, sample_aircraft, dv):
    """A resumed battery appends to its frames; it does not overwrite them."""
    first, member = _member(tmp_path, sample_aircraft)
    for i in range(3):
        member.iterate(i, dv, {}, {})

    resumed = liveframe.FrameWriter(first.dir, sample_aircraft)
    later = resumed.member("flatness sweep", 1.85, 1, 6)
    later.iterate(0, dv, {}, {})

    paths = liveframe.frame_paths(first.dir)
    assert len(paths) == 4
    assert paths[-1].name.startswith("f000003__")
    assert liveframe.read_frame(paths[-1])["label"] == "flatness sweep"


def test_a_float_member_key_survives_the_filename(tmp_path, sample_aircraft, dv):
    """The flatness sweep keys its members by SPAN, which is not a valid name."""
    writer = liveframe.FrameWriter(tmp_path / "live", sample_aircraft)
    writer.member("flatness sweep", 1.8523, 1, 6).iterate(0, dv, {}, {})

    (path,) = liveframe.frame_paths(writer.dir)
    assert "1.8523" in path.name
    assert liveframe.read_frame(path)["key"] == "1.8523"


def test_a_half_written_frame_is_never_visible(tmp_path, sample_aircraft, dv):
    """Frames land by rename, so a killed write leaves a `.part`, not a frame."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.iterate(0, dv, {}, {})
    (writer.dir / "f000001__multistart__nominal__i0001.json.gz.999.part").write_bytes(b"\x1f\x8b")

    paths = liveframe.frame_paths(writer.dir)
    assert len(paths) == 1
    assert all(liveframe.read_frame(p) for p in paths)


def test_relocate_moves_frames_into_the_run_directory(tmp_path, sample_aircraft, dv):
    writer, member = _member(tmp_path, sample_aircraft)
    for i in range(3):
        member.iterate(i, dv, {}, {})
    run_dir = tmp_path / "20260805T120000-run"
    run_dir.mkdir()

    dest = liveframe.relocate(writer.dir, run_dir)
    assert dest == run_dir / "frames"
    assert len(liveframe.frame_paths(dest)) == 3
    assert not writer.dir.exists()


# --- the guarantees ------------------------------------------------------


def test_an_undrawable_iterate_is_skipped_not_raised(tmp_path, sample_aircraft, dv):
    """Interior-point methods walk through negative chords; that is not an error."""
    writer, member = _member(tmp_path, sample_aircraft)
    member.iterate(1, {**dv, "span": float("nan")}, {}, {})
    member.iterate(2, {**dv, "span": 1e6}, {}, {})  # meshes, but is not an aeroplane

    assert liveframe.frame_paths(writer.dir) == []
    assert not writer.disabled, "a skipped frame must not disable the writer"

    member.iterate(3, dv, {}, {})
    assert len(liveframe.frame_paths(writer.dir)) == 1


def test_the_writer_disables_itself_once_and_says_so(
    tmp_path, sample_aircraft, dv, monkeypatch, caplog
):
    writer, member = _member(tmp_path, sample_aircraft)

    def explode(*a, **kw):
        raise OSError("no space left on device")

    monkeypatch.setattr(liveframe.gzip, "open", explode)
    with caplog.at_level(logging.WARNING, logger="planeopt"):
        for i in range(5):
            member.iterate(i, dv, {}, {})
        member.candidate({**CONVERGED, "dv": dv})

    assert writer.disabled
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, "the latch must not turn a full disk into a log flood"
    assert "live frames disabled" in warnings[0].getMessage()


def test_a_failed_member_writes_no_candidate_frame(tmp_path, sample_aircraft):
    writer, member = _member(tmp_path, sample_aircraft)
    member.candidate({"failed": "Maximum_WallTime_Exceeded", "return_status": "x"})
    assert liveframe.frame_paths(writer.dir) == []
    assert not writer.disabled


def test_the_iterate_cap_stops_iterates_but_not_candidates(
    tmp_path, sample_aircraft, dv, monkeypatch
):
    monkeypatch.setattr(liveframe, "MAX_ITERATE_FRAMES", 2)
    writer, member = _member(tmp_path, sample_aircraft)
    for i in range(5):
        member.iterate(i, dv, {}, {})
    member.candidate({**CONVERGED, "dv": dv})

    kinds = [liveframe.read_frame(p)["kind"] for p in liveframe.frame_paths(writer.dir)]
    assert kinds == ["iterate", "iterate", "candidate"]


# --- the guarantee that matters ------------------------------------------


def test_a_poisoned_writer_cannot_fail_a_solve(tmp_path):
    """A frame writer that raises mid-solve must cost a picture, not a member.

    The callback runs inside IPOPT's iteration loop, so an exception escaping it
    is an ABORTED SOLVE rather than a missing frame — and a member solve is 5-30
    minutes of a battery measured in hours. A two-variable toy NLP is enough:
    what is under test is the wrapping, not the physics.
    """
    import aerosandbox as asb

    from planeopt import solve

    class Poisoned(liveframe.FrameWriter):
        def __init__(self, directory):
            super().__init__(directory, aircraft=None)
            self.calls = 0

    class PoisonedMember(liveframe._Member):
        def iterate(self, *a, **kw):
            self.writer.calls += 1
            if self.writer.calls >= 3:
                raise MemoryError("frame writer went bad")

    writer = Poisoned(tmp_path / "live")
    member = PoisonedMember(writer, "toy", "nominal", 1, 1)

    opti = asb.Opti()
    x = opti.variable(init_guess=0.4, lower_bound=-2, upper_bound=2)
    y = opti.variable(init_guess=0.4, lower_bound=-2, upper_bound=2)
    opti.subject_to(x + y >= 0.5)
    opti.minimize((x - 1.3) ** 2 + (y + 0.7) ** 2)

    callback = solve._live_frame_callback(opti, member, {"x": x, "y": y}, {"V_ms": x})
    sol = opti.solve(verbose=False, callback=callback)

    assert opti.debug.stats()["return_status"] == "Solve_Succeeded"
    assert float(sol(x)) == pytest.approx(1.3, abs=1e-4)
    assert writer.calls >= 3, "the callback must actually have been reached"
    assert writer.disabled, "and the failure must have latched the writer off"


def test_the_callback_reads_the_design_vector_and_ipopts_own_numbers(tmp_path):
    """dv comes from one stacked `debug.value`; inf_pr comes free from stats."""
    import aerosandbox as asb

    from planeopt import solve

    seen = []

    class Recorder(liveframe._Member):
        def iterate(self, iter_n, dv, state, scalars):
            seen.append((iter_n, dv, state, scalars))

    opti = asb.Opti()
    x = opti.variable(init_guess=0.4, lower_bound=-2, upper_bound=2)
    v = opti.variable(init_guess=9.0, lower_bound=6, upper_bound=25)
    opti.subject_to(x + v >= 1.0)
    opti.minimize((x - 1.3) ** 2 + (v - 11.0) ** 2)

    member = Recorder(liveframe.FrameWriter(tmp_path / "live"), "toy", "k", 1, 1)
    opti.solve(
        verbose=False,
        callback=solve._live_frame_callback(opti, member, {"span": x}, {"V_ms": v}),
    )

    assert seen, "the callback should fire once per iterate"
    assert [row[0] for row in seen] == sorted(row[0] for row in seen)
    last_iter, last_dv, last_state, last_scalars = seen[-1]
    assert set(last_dv) == {"span"}
    assert set(last_state) == {"V_ms"}
    assert last_dv["span"] == pytest.approx(1.3, abs=1e-3)
    assert last_state["V_ms"] == pytest.approx(11.0, abs=1e-3)
    # Free, from IPOPT's own iteration log — no CasADi function is built.
    assert "inf_pr" in last_scalars
    assert "ipopt_objective" in last_scalars


# --- wiring into the batch runner ----------------------------------------


class _StubAircraft:
    """Just enough aircraft to be an attribute holder for a discrete study."""

    prop_key = "baseline"


def _stub_solve(monkeypatch, result: dict):
    from planeopt import solve

    monkeypatch.setattr(
        solve, "_solve_nlp",
        lambda aircraft, mission, frames=None, **kw: dict(result),
    )


def test_a_studys_candidate_frame_is_drawn_before_the_attribute_is_restored(
    tmp_path, sample_mission, monkeypatch
):
    """The frame has to be written while the member's own configuration is on.

    A discrete study brackets each member with prep/restore, so a candidate
    frame written after `restore` would draw the BASELINE aeroplane under the
    candidate's name — the same shape of failure as the 2026-08-05 flatness
    curve that described a superseded design (`solve.optimize`, "characterization
    of the FINAL design"). It cannot be caught by looking at the picture, which
    is exactly why it is pinned here.
    """
    from planeopt import solve

    aircraft = _StubAircraft()
    drawn = {}
    _stub_solve(monkeypatch, {"dv": {"span": 1.8}, "objective_value": 118.0})
    monkeypatch.setattr(
        liveframe._Member, "candidate",
        lambda self, result: drawn.__setitem__(self.key, aircraft.prop_key),
    )

    writer = liveframe.FrameWriter(tmp_path / "live", aircraft)
    solve._solve_many(
        aircraft, sample_mission, [("apc_12x10", {})], label="study prop_key",
        prep=lambda key: setattr(aircraft, "prop_key", key),
        restore=lambda: setattr(aircraft, "prop_key", "baseline"),
        live=writer,
    )

    assert drawn == {"apc_12x10": "apc_12x10"}
    assert aircraft.prop_key == "baseline", "restore must still happen"


def test_the_candidate_frame_is_not_charged_to_the_solve(
    tmp_path, sample_mission, monkeypatch
):
    """`solve_minutes` is the SOLVER's time, not the viewer's.

    The candidate frame runs its own lifting line; timing the member around it
    would quietly inflate every reported member time, and those numbers feed the
    phase-minutes breakdown the run artifact reports.
    """
    import time

    from planeopt import solve

    aircraft = _StubAircraft()
    _stub_solve(monkeypatch, {"dv": {"span": 1.8}, "objective_value": 118.0})
    monkeypatch.setattr(
        liveframe._Member, "candidate",
        lambda self, result: time.sleep(0.35),
    )

    writer = liveframe.FrameWriter(tmp_path / "live", aircraft)
    results = solve._solve_many(
        aircraft, sample_mission, [("nominal", {})], label="multistart", live=writer,
    )
    assert results["nominal"]["solve_minutes"] < 0.35 / 60.0


def test_members_are_numbered_in_the_frame(tmp_path, sample_mission, monkeypatch):
    """In forked mode the newest frame can belong to any member in flight."""
    from planeopt import solve

    aircraft = _StubAircraft()
    seen = []
    _stub_solve(monkeypatch, {"dv": {}, "objective_value": 1.0})
    monkeypatch.setattr(
        liveframe._Member, "candidate",
        lambda self, result: seen.append((self.index, self.total, self.key)),
    )

    writer = liveframe.FrameWriter(tmp_path / "live", aircraft)
    solve._solve_many(
        aircraft, sample_mission,
        [("nominal", {}), ("perturbed_0", {}), ("mass_bump", {})],
        label="multistart", live=writer,
    )
    assert seen == [(1, 3, "nominal"), (2, 3, "perturbed_0"), (3, 3, "mass_bump")]


# --- the stats block (pure formatting, no display needed) ----------------


def _synthetic(**overrides) -> dict:
    frame = {
        "schema": 1, "kind": "iterate", "label": "multistart", "key": "nominal",
        "member_index": [2, 24], "iter": 42, "t_member_s": 63.2,
        "dv": {"c_root": 0.22, "taper": 0.68},
        "state": {"V_ms": 11.0, "alpha_deg": 4.0},
        "geometry": {"span_m": 1.8, "area_m2": 0.333, "aspect_ratio": 9.73},
        "scalars": {"inf_pr": 0.056},
    }
    frame.update(overrides)
    return frame


def test_a_value_this_frame_lacks_renders_as_a_dash_not_a_stale_number():
    _, state = liveframe.stats_columns(_synthetic())
    rows = dict(state)
    assert rows["CL"] == liveframe.MISSING
    assert rows["V"] == "11.00 m/s"


def test_the_header_always_names_the_member():
    """In forked mode the newest frame may belong to any member in flight."""
    assert "multistart [2/24] nominal" in liveframe.header_text(_synthetic())
    assert "iter 42" in liveframe.header_text(_synthetic())
    assert "converged" in liveframe.header_text(_synthetic(kind="candidate"))


# --- end to end, against a real optimizer run ----------------------------


@pytest.mark.solve
def test_a_real_run_writes_frames_and_relocates_them(
    sample_aircraft, sample_mission, tmp_path
):
    """The M5.4 gate, minus the eyes: a real battery must produce a replayable
    frame stream that ends up beside the artifacts.

    Reduced to one multistart with no flatness sweep — what is under test is the
    plumbing (callback fires, iterates increase, one candidate per member,
    frames relocate), not the optimizer, which `test_m3_optimize_smoke` covers.
    """
    from planeopt import solve

    live_dir = tmp_path / "_live" / "endurance"
    _, run_dir = solve.optimize(
        sample_aircraft, sample_mission, runs_root=tmp_path,
        multistart=1, flatness=False, live_dir=live_dir,
    )

    assert not live_dir.exists(), "frames should have moved into the run directory"
    frames = liveframe.frame_paths(run_dir / "frames")
    assert frames, "a real solve must have produced frames"

    by_member: dict[tuple, list[dict]] = {}
    for path in frames:
        frame = liveframe.read_frame(path)
        assert frame["schema"] == liveframe.SCHEMA
        by_member.setdefault((frame["label"], frame["key"]), []).append(frame)

    for (label, key), member in by_member.items():
        iterates = [f for f in member if f["kind"] == "iterate"]
        candidates = [f for f in member if f["kind"] == "candidate"]
        where = f"{label}/{key}"
        assert iterates, f"{where} recorded no iterates"
        assert [f["iter"] for f in iterates] == sorted(f["iter"] for f in iterates), where
        assert len(candidates) <= 1, f"{where} produced more than one candidate frame"
        for frame in candidates:
            assert frame["color"]["name"] == "cl"
            assert len(frame["color"]["values"]) == len(frame["mesh"]["surface_of"])
            _, state = liveframe.stats_columns(frame)
            assert dict(state)["CL"] != liveframe.MISSING

    # ... and the whole thing replays.
    pytest.importorskip("PySide6")
    from planeopt.gui import timelapse

    result = timelapse.render(
        run_dir, tmp_path / "timelapse", size=(640, 480), hold_candidate=2
    )
    assert result["images"] >= len(frames)
    assert result["unreadable"] == 0


def test_wing_loading_is_derived_only_when_both_halves_are_present():
    geometry, _ = liveframe.stats_columns(_synthetic())
    assert ("wing loading", liveframe.MISSING) in geometry
    geometry, _ = liveframe.stats_columns(
        _synthetic(scalars={"auw_kg": 1.58})
    )
    assert dict(geometry)["wing loading"] == "47.4 g/dm2"


# --- recolouring finished iterates (M5.7) --------------------------------
#
# The claim under test is that the colours on an iterate can be computed AFTER
# the solve from what the frame already carries, and that doing so cannot
# quietly show a different aeroplane.


def _iterate_frames(tmp_path, aircraft, dv, n=3):
    """A little run of geometry-only iterates, as the solver would write them."""
    writer = liveframe.FrameWriter(tmp_path / "live", aircraft)
    member = writer.member("demo", "nominal", 1, 1)
    for i in range(n):
        moved = {**dv, "span": float(dv["span"]) * (1 + 0.01 * i)}
        member.iterate(i, moved, {"V_ms": 11.0, "alpha_deg": 4.0, "deflection_deg": -1.0}, {})
    return writer.dir


def test_recolouring_fills_in_the_aerodynamics_an_iterate_lacked(
    tmp_path, sample_aircraft, dv
):
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv)
    before = liveframe.read_frame(liveframe.frame_paths(src)[0])
    assert liveframe.scalar_values(before, "cl") is None
    assert liveframe.streamline_points(before) == []

    result = rc.recolour(src, sample_aircraft)
    assert result["recoloured"] == 3 and result["skipped"] == 0
    after = liveframe.read_frame(liveframe.frame_paths(result["out_dir"])[0])

    assert len(liveframe.scalar_values(after, "cl")) == len(after["mesh"]["surface_of"])
    assert liveframe.streamline_points(after), "the wake comes with it"
    assert liveframe.lift_overlay(after), "and so does the lift distribution"
    assert after["scalars"]["CL"] > 0
    # It is still the iterate the solver wrote: same identity, same place in the
    # run, same IPOPT numbers. Only the aerodynamics is new.
    for key in ("kind", "iter", "label", "key", "member_index", "t_member_s"):
        assert after[key] == before[key]
    assert after["dv"] == before["dv"]


def test_a_recoloured_frame_says_it_is_not_trimmed(tmp_path, sample_aircraft, dv):
    """CL and Cm on an iterate are real numbers for an aircraft still being
    trimmed. Unlabelled, they read as a result."""
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv, n=1)
    out = rc.recolour(src, sample_aircraft)["out_dir"]
    after = liveframe.read_frame(liveframe.frame_paths(out)[0])

    assert after[rc.MARK] is True
    assert liveframe.FOOTNOTE_RECOLOURED in liveframe.footnotes(after)
    assert "not trimmed" in liveframe.FOOTNOTE_RECOLOURED
    # A frame the solver coloured itself carries no such caption: a candidate IS
    # trimmed, and the note would be false there.
    assert liveframe.footnotes({"kind": "iterate"}) == [liveframe.FOOTNOTE_IPOPT]


def test_the_originals_are_left_alone_unless_in_place_is_asked_for(
    tmp_path, sample_aircraft, dv
):
    """The frames the solver wrote are the record of what it actually saw."""
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv, n=1)
    result = rc.recolour(src, sample_aircraft)
    assert result["out_dir"] != src
    assert liveframe.scalar_values(
        liveframe.read_frame(liveframe.frame_paths(src)[0]), "cl"
    ) is None

    rc.recolour(src, sample_aircraft, in_place=True)
    assert liveframe.scalar_values(
        liveframe.read_frame(liveframe.frame_paths(src)[0]), "cl"
    ) is not None


def test_a_candidate_frame_is_passed_through_untouched(tmp_path, sample_aircraft, dv):
    """It was already computed this way, by the solve, at the converged point —
    recomputing it could only introduce a disagreement with the artifact."""
    from planeopt import recolour as rc

    writer = liveframe.FrameWriter(tmp_path / "live", sample_aircraft)
    member = writer.member("demo", "nominal", 1, 1)
    member.candidate({**CONVERGED, "dv": dv, "clmax_ab_used": CLMAX_AB})
    original = liveframe.read_frame(liveframe.frame_paths(writer.dir)[0])

    result = rc.recolour(writer.dir, sample_aircraft)
    assert result["already_coloured"] == 1 and result["recoloured"] == 0
    assert liveframe.read_frame(liveframe.frame_paths(result["out_dir"])[0]) == original


def test_the_wrong_aircraft_is_refused_rather_than_drawn(tmp_path, sample_aircraft, dv):
    """The same failure shape as the restore() bug: it would converge, look
    perfect, and be a picture of a different aeroplane."""
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv, n=1)

    class Impostor:
        DV_DEFAULTS = {"span": 1.0, "c_root": 0.2, "something_else": 3.0}

    with pytest.raises(rc.AircraftMismatch, match="different aeroplane"):
        rc.recolour(src, Impostor())


def test_an_undrawable_iterate_is_kept_as_it_was_not_dropped(
    tmp_path, sample_aircraft, dv
):
    """An infeasible iterate is ordinary during a solve, and the geometry-only
    frame the solver wrote for it is still the truth about that iterate."""
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv, n=2)

    class Refuses:
        DV_DEFAULTS = sample_aircraft.DV_DEFAULTS

        def geometry(self, dv):
            raise ValueError("this iterate has a negative chord")

    result = rc.recolour(src, Refuses())
    assert result["skipped"] == 2 and result["recoloured"] == 0
    kept = liveframe.frame_paths(result["out_dir"])
    assert len(kept) == 2, "every frame still arrives"
    assert liveframe.read_frame(kept[0])["kind"] == "iterate"


def test_a_runs_own_input_snapshot_is_what_it_recolours_against(tmp_path):
    """The working tree's definition is a moving target; the snapshot is not."""
    from planeopt import recolour as rc

    run = tmp_path / "20260805T120000-run"
    (run / "frames").mkdir(parents=True)
    assert rc.snapshot_aircraft(run) is None
    (run / "inputs").mkdir()
    (run / "inputs" / "aircraft.py").write_text("AIRCRAFT = None", encoding="utf-8")
    assert rc.snapshot_aircraft(run) == run / "inputs" / "aircraft.py"
    # ... found from the frames directory too, which is what the CLI is handed
    assert rc.snapshot_aircraft(run / "frames") == run / "inputs" / "aircraft.py"


def test_the_recoloured_frames_keep_the_runs_timelapse_view(
    tmp_path, sample_aircraft, dv
):
    """Or the copy would render from the default view while the original did not."""
    from planeopt import recolour as rc

    src = _iterate_frames(tmp_path, sample_aircraft, dv, n=1)
    liveframe.write_view(src, {"view": "plan"})
    out = rc.recolour(src, sample_aircraft)["out_dir"]
    assert liveframe.read_view(out)["view"] == "plan"
