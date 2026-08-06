"""Equipment manifest: the RC v2 BOM as a placed, packed, priced parts list.

The gates here are the ones that would let a manifest go quietly wrong:
transcription drift against the source sheet, an infeasible starting point on
ten new variables, a lane whose items overlap, a requirement that was written
down and never turned into a row, and the symbolic-safety rule.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from planeopt import equipment
from planeopt.cli import load_aircraft

REPO = Path(__file__).parent.parent


@pytest.fixture()
def rcv2():
    ac, _ = load_aircraft(REPO / "aircraft" / "vtail_rcv2")
    return ac


class _Stub:
    """Records constraint rows and which of them a numeric design violates."""

    def __init__(self):
        self.rows = 0
        self.violated = []

    def subject_to(self, c):
        self.rows += 1
        if not bool(c):
            frame = inspect.stack()[1]
            local = frame.frame.f_locals
            self.violated.append(
                (frame.lineno, {
                    k: getattr(local[k], "name", local[k])
                    for k in ("lane_name", "item", "prev", "stack", "sep")
                    if k in local
                })
            )


# --------------------------------------------------------------------------
# the manifest reproduces its source
# --------------------------------------------------------------------------


def test_bom_est_column_reconciles(rcv2):
    """The example-part masses add up to the sheet's own stated total.

    ELECTRONICS_SPEC.xlsx BOM totals row: "≈ 825 airborne". The propeller is
    carried separately here (its mass is the prop study's outcome), so it comes
    out of the comparison.
    """
    items = rcv2.manifest()
    prop = equipment.lookup(items, "propeller").mass("est")
    total = equipment.totals(items, "est")["total_kg"]
    assert abs((total - prop) - 0.8246) < 5e-4


def test_bom_max_column_does_not_match_its_own_stated_cap(rcv2):
    """The sheet says "≈ 895 cap" and its Max-wt column sums to 950 g.

    Pinned as a finding, not as a bug to be papered over: this package solves on
    the max basis, so the 55 g is the difference between the aeroplane the sheet
    claims and the aeroplane the sheet specifies. If someone corrects the
    spreadsheet, this test is the thing that says the model must move with it.
    """
    items = rcv2.manifest()
    prop = equipment.lookup(items, "propeller").mass("max")
    total = equipment.totals(items, "max")["total_kg"]
    assert abs((total - prop) - 0.950) < 5e-4
    assert (total - prop) - 0.895 > 0.05  # the sheet's cap is light, by ~55 g


def test_every_bom_row_is_present(rcv2):
    """20 BOM rows in, 25 items out — and the expansions are all deliberate."""
    items = rcv2.manifest()
    names = {i.name for i in items}
    # 4 servos from one qty-4 row, because they go in two different places
    assert {"servo_aileron_left", "servo_aileron_right",
            "servo_ruddervator_left", "servo_ruddervator_right"} <= names
    # the airspeed row splits into the board (on the shelf) and the probe (on
    # the wing), and the wiring row into the pod harness and the boom run
    assert {"airspeed_board", "pitot_probe", "wiring_pod", "wiring_boom"} <= names
    # ground/bench items are carried so the BOM reconciles, but fly nothing
    ground = [i for i in items if not i.airborne]
    assert {i.name for i in ground} == {
        "transmitter", "ground_station", "charger", "lipo_checker"
    }
    assert all(i.mass_kg == 0.0 for i in ground)
    assert not any(i.name in equipment.stations(items, rcv2.DV_DEFAULTS,
                                                rcv2.derived_stations(rcv2.DV_DEFAULTS))
                   for i in ground)


def test_every_item_has_a_station(rcv2):
    """No carried part is left without a placement — the whole point."""
    items = rcv2.manifest()
    where = rcv2.placements()
    assert set(where) == {i.name for i in equipment.carried(items)}
    assert all(-0.2 < float(v) < 1.6 for v in where.values())


def test_cards_ride_their_hosts(rcv2):
    """A card in a slot has no freedom of its own and must not be given any."""
    where = rcv2.placements()
    assert where["sd_card_fc"] == where["flight_controller"]
    assert where["sd_card_pi"] == where["companion_pi"]
    assert "x_sd_card_fc" not in rcv2.DV_DEFAULTS


# --------------------------------------------------------------------------
# placement: variables, feasibility, packing
# --------------------------------------------------------------------------


def test_placed_items_all_have_inits(rcv2):
    """A placement variable with no declared init is a KeyError mid-solve."""
    for item in equipment.placed(rcv2.manifest()):
        assert f"x_{item.name}" in rcv2.DV_DEFAULTS, item.name


@pytest.mark.parametrize("fit", ["full", "core"])
def test_declared_inits_are_feasible(rcv2, fit):
    """The starting point satisfies every packing row it is subject to.

    Ten new variables whose initial values violated their own lanes would spend
    the first hundred IPOPT iterations finding the bay rather than the
    aeroplane. Checked for the mount this aircraft actually flies — `puller`,
    which is the only candidate `discrete_options` carries.
    """
    rcv2.equipment_fit = fit
    stub = _Stub()
    d = dict(rcv2.DV_DEFAULTS)
    rcv2.packaging_constraints(stub, d, rcv2.pod_dims(d))
    assert stub.rows > 15
    assert stub.violated == []


def test_lane_contents_do_not_overlap(rcv2):
    """Declared order is fore-to-aft, and neighbours clear each other."""
    items = rcv2.manifest()
    where = rcv2.placements()
    d = dict(rcv2.DV_DEFAULTS)
    for name, lane in rcv2.lanes(d, items).items():
        contents = equipment.by_lane(items, name)
        for prev, item in zip(contents, contents[1:]):
            gap = (prev.length + item.length) / 2 + lane.gap_m
            assert float(where[item.name]) - float(where[prev.name]) >= gap - 1e-9, (
                f"{name}: {prev.name} -> {item.name}"
            )


def test_separations_are_enforced_not_merely_documented(rcv2):
    """Each declared separation is a row AND holds at the declared placement."""
    where = rcv2.placements()
    seps = rcv2.separations()
    assert {(s.a, s.b) for s in seps} >= {
        ("esc", "gps_compass"), ("telemetry_sik", "gps_compass"),
    }
    for sep in seps:
        d = float(where[sep.b]) - float(where[sep.a])
        if sep.min_m is not None:
            assert d >= sep.min_m - 1e-9, f"{sep.a}->{sep.b} {d}"
        if sep.max_m is not None:
            assert d <= sep.max_m + 1e-9, f"{sep.a}->{sep.b} {d}"


def test_aft_bay_section_stack_is_the_binding_kind_of_tight(rcv2):
    """ESC + widest shelf part + telemetry + play, against the interior width.

    The spec's 68 mm section leaves under a millimetre of margin. Pinned so that
    a future change to the section, the play allowance or any part's installed
    orientation surfaces here rather than in a solve that mysteriously grows the
    pod.
    """
    items = rcv2.manifest()
    d = dict(rcv2.DV_DEFAULTS)
    stack = next(s for s in rcv2.section_stacks(d, items) if s.axis == "width")
    need = stack.extra_m + sum(
        max(i.width for i in equipment.by_lane(items, ln))
        for ln in stack.lanes
        if equipment.by_lane(items, ln)
    )
    assert abs(need - 0.0607) < 1e-4
    assert 0.0 < float(stack.available) - need < 0.002


def test_dropping_the_optional_kit_drops_its_variables_too(rcv2):
    """`core` is a smaller NLP, not the same one with dead variables in it."""
    rcv2.equipment_fit = "core"
    core = {i.name for i in equipment.placed(rcv2.manifest())}
    rcv2.equipment_fit = "full"
    full = {i.name for i in equipment.placed(rcv2.manifest())}
    assert full - core == {"companion_pi", "bec_pi", "airspeed_board", "telemetry_sik"}
    # and the study is priced, never adopted
    assert rcv2.priced_options == {"equipment_fit": ["core"]}


# --------------------------------------------------------------------------
# mass model
# --------------------------------------------------------------------------


def test_solved_basis_is_max(rcv2):
    """This package designs the heaviest aeroplane its own BOM permits."""
    assert rcv2.equipment_mass_basis == "max"
    total = sum(pm.mass_kg for pm in rcv2.fixed_equipment())
    assert abs(total - equipment.totals(rcv2.manifest(), "max")["total_kg"]) < 1e-9


def test_closure_check_holds_placement_fixed(rcv2):
    """The max-vs-est comparison is a substitution, not a re-optimization."""
    items = rcv2.manifest()
    where = {k: float(v) for k, v in rcv2.placements().items()}
    other = [
        pm for pm in rcv2.structure_extras(dict(rcv2.DV_DEFAULTS))
    ]
    closure = equipment.mass_closure(items, where, other, "max")
    assert closure["max"]["auw_kg"] > closure["est"]["auw_kg"]
    assert abs(closure["delta"]["equipment_kg"] - 0.1254) < 1e-3
    # heavier parts, same stations -> the CG moves, and by how much is the point
    assert closure["delta"]["x_cg_m"] != 0.0


def test_unenforced_requirements_survive_into_the_report(rcv2):
    """A requirement this model cannot check must still reach the builder."""
    rows = equipment.rows(rcv2.manifest(), rcv2.placements(), "max")
    gps = next(r for r in rows if r["item"] == "gps_compass")
    assert "RF-transparent" in gps["not checked here"]
    rx = next(r for r in rows if r["item"] == "receiver_elrs")
    assert "ANTENNAS ARE THE REAL CONSTRAINT" in rx["not checked here"]
    ground = next(r for r in rows if r["item"] == "charger")
    assert ground["status"].startswith("ground/bench")
    assert ground["station_mm"] == ""


# --------------------------------------------------------------------------
# framework contracts
# --------------------------------------------------------------------------


def test_placement_variables_reach_the_design_vector(rcv2):
    """Symbolic safety, and the reason placements appear in run.json at all:
    they are ordinary design variables, so `dv` carries them for free."""
    import aerosandbox as asb

    opti = asb.Opti()
    dv = rcv2.design_variables(opti)
    assert "x_flight_controller" in dv
    assert "x_battery" in dv  # the balance knob keeps its name
    # and every row builds against symbolics without a branch on their values
    rcv2.packaging_constraints(opti, dv, rcv2.pod_dims(dv))


def test_manifest_hook_is_optional(sample_aircraft):
    """The sample has no manifest and must be completely unaffected."""
    assert not hasattr(sample_aircraft, "manifest")
    assert getattr(sample_aircraft, "equipment_report", None) is None
    assert len(sample_aircraft.fixed_equipment()) == 7


def test_sample_packaging_rows_are_unchanged_by_the_refactor(sample_aircraft):
    """`packaging_constraints` was extracted from `geometry_constraints` as a
    pure refactor — same six rows, same values."""
    stub = _Stub()
    d = dict(sample_aircraft.DV_DEFAULTS)
    sample_aircraft.packaging_constraints(stub, d, sample_aircraft.pod_dims(d))
    assert stub.rows == 6


# --------------------------------------------------------------------------
# did the freedom buy anything — the measurement EQUIPMENT_PLAN.md pre-registered
# --------------------------------------------------------------------------


def _lane(**kw):
    base = dict(name="l", x_lo=0.0, x_hi=1.0, end_margin_m=0.003, gap_m=0.003)
    return equipment.Lane(**(base | kw))


def _pair():
    return [
        equipment.Item("a", "g", 0.010, size_m=(0.040, 0.01, 0.01), lane="l", order=10),
        equipment.Item("b", "g", 0.010, size_m=(0.020, 0.01, 0.01), lane="l", order=20),
    ]


def test_an_item_touching_one_neighbour_is_still_a_live_variable():
    """Hard against the item in front, but a whole lane of room behind it.

    This is the distinction the measurement exists to make: `b` is AT a row, so
    a naive "is any row tight" test would call it pinned, but its station is not
    determined — the optimizer put it forward and could have put it anywhere in
    the next 900 mm. Calling that "the freedom bought nothing" would be wrong.
    """
    items = _pair()
    where = {"a": 0.003 + 0.020, "b": 0.003 + 0.020 + 0.030 + 0.003}
    act = equipment.placement_activity(items, {"l": _lane(x_hi=1.0)}, where)
    assert act["n_placed"] == 2
    # `a` is boxed in (lane front ahead, `b` behind); `b` is not
    assert act["n_determined"] == 1
    b = next(r for r in act["items"] if r["item"] == "b")
    assert b["pinned_by"] == ["gap behind a"]  # touching, but only on one side
    assert abs(b["room_fwd_mm"]) < 1e-3
    assert b["room_aft_mm"] > 900
    assert b["determined"] is False
    assert "still have room aft" in act["verdict"]


def test_placement_activity_reports_every_item_determined_when_the_lane_is_full():
    """A lane exactly long enough to hold its contents fixes both of them.

    This is the case the plan said to watch for: if every placed item is boxed
    in on both sides then the station variables were never free, and the lanes
    could collapse to derived packing without changing the design.
    """
    items = _pair()
    # front margin + a + gap + b + aft margin, to the millimetre
    lane = _lane(x_hi=0.003 + 0.040 + 0.003 + 0.020 + 0.003)
    where = {"a": 0.003 + 0.020, "b": 0.003 + 0.040 + 0.003 + 0.010}
    act = equipment.placement_activity(items, {"l": lane}, where)
    assert act["n_determined"] == act["n_placed"] == 2
    assert act["n_at_forward_stop"] == 2
    for r in act["items"]:
        # never negative zero: the artifact must not read as slightly violated
        assert r["room_fwd_mm"] == 0.0 and r["room_aft_mm"] == 0.0
    assert "boxed in on both sides" in act["verdict"]


def test_placement_activity_names_a_separation_as_the_thing_holding_an_item():
    """An item held off the lane front by an RF separation is reported as held
    BY THAT SEPARATION — a lane-end check alone would call it free."""
    items = _pair()
    seps = (equipment.Separation(a="a", b="b", min_m=0.200),)
    where = {"a": 0.023, "b": 0.223}  # b pushed aft to clear the 200 mm rule
    act = equipment.placement_activity(items, {"l": _lane(x_hi=2.0)}, where, seps)
    b = next(r for r in act["items"] if r["item"] == "b")
    assert b["pinned_by"] == ["separation from a"]
    assert abs(b["room_fwd_mm"]) < 1e-3   # the separation stops it moving forward
    assert b["room_aft_mm"] > 1000        # nothing stops it moving aft
    # and the partner is held the other way: `a` cannot move AFT without
    # closing the same gap
    a = next(r for r in act["items"] if r["item"] == "a")
    assert "separation to b" in a["pinned_by"]
    assert abs(a["room_aft_mm"]) < 1e-3


def test_placement_activity_covers_the_real_manifest(rcv2):
    """Every placed item on the real aircraft appears, by name."""
    act = rcv2.equipment_report()["placement_activity"]
    named = {r["item"] for r in act["items"]}
    assert named == {i.name for i in equipment.placed(rcv2.manifest())}
    assert act["n_placed"] == len(named) == 10
    assert all(r["room_fwd_mm"] >= 0.0 for r in act["items"])


def test_packing_rows_are_exact_at_the_ordering_limit(rcv2):
    """One micrometre either side of the ordering row's limit.

    This row was briefly rewritten as `(xi - x_prev) / gap >= 1.0` on
    2026-08-06 and reverted the same day for costing a member (see
    `equipment.constraints`). The gate stays: it is the tightest thing either
    form could get wrong, and it is what proves the revert did not move the
    feasible set back the other way.
    """
    items = rcv2.manifest()
    d = dict(rcv2.DV_DEFAULTS)
    contents = equipment.by_lane(items, "bay_shelf")
    prev, item = contents[0], contents[1]
    gap = (prev.length + item.length) / 2 + rcv2.lanes(d, items)["bay_shelf"].gap_m
    for delta, expect_ok in ((+1e-6, True), (-1e-6, False)):
        probe = dict(d)
        probe[f"x_{item.name}"] = probe[f"x_{prev.name}"] + gap + delta
        stub = _Stub()
        equipment.constraints(
            stub, items, rcv2.lanes(probe, items), probe,
            separations=(), stacks=(),
        )
        hit = any("prev" in ctx and ctx.get("item") == item.name
                  for _, ctx in stub.violated)
        assert hit is not expect_ok, f"delta={delta}"
