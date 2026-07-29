"""The build document (report/manufacturing.py).

These guard the two properties a build document lives on: that it describes the
SAME aircraft the solver analysed (not a summary of it that has drifted), and
that the balance numbers a builder will actually trim to are derived from the
same reference the static-margin constraint used.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from planeopt import types
from planeopt.report import manufacturing


@pytest.fixture()
def built(sample_aircraft):
    return sample_aircraft, sample_aircraft.geometry(None)


def _result(**over) -> types.RunResult:
    base = dict(
        aircraft="fixture", mission="m", objective="endurance", status="test",
        created="2026-07-29T00:00:00",
        masses={"auw_kg": 1.8, "x_cg_m": 0.50,
                "components": {"battery": 0.43, "nose_ballast": -0.0}},
        performance={"objective_units": "min", "optimization": {"champion": {"dv": None}}},
        constraints={"static_margin": 0.10, "static_margin_range": [0.08, 0.15]},
        diagnostics={"neutral_point_m": 0.52},
    )
    base.update(over)
    return types.RunResult(**base)


# ---------------------------------------------------------------- geometry out

def test_surfaces_lists_every_surface_the_airplane_carries(built):
    _, airplane = built
    rows = manufacturing.surfaces(airplane)
    assert {r["surface"] for r in rows} == {w.name for w in airplane.wings}
    assert all(r["span_mm"] > 0 and r["root_chord_mm"] > 0 for r in rows)


def test_edges_give_both_edges_at_every_station(built):
    _, airplane = built
    rows = manufacturing.edges(airplane)
    for wing in airplane.wings:
        mine = [r for r in rows if r["surface"] == wing.name]
        assert len(mine) == 2 * len(wing.xsecs)
        assert {r["edge"] for r in mine} == {"LE", "TE"}


def test_edge_points_match_the_analysed_geometry(built):
    """The whole point of the document: these are asb's own placement calls."""
    _, airplane = built
    wing = airplane.wings[0]
    rows = [r for r in manufacturing.edges(airplane)
            if r["surface"] == wing.name and r["edge"] == "LE"]
    for i, row in enumerate(rows):
        le = np.array(wing._compute_xyz_le_of_WingXSec(i), dtype=float).flatten()
        assert (row["x_m"], row["y_m"], row["z_m"]) == pytest.approx(tuple(le), abs=1e-6)


def test_edge_span_station_accumulates_along_the_surface(built):
    _, airplane = built
    le = [r for r in manufacturing.edges(airplane)
          if r["surface"] == "wing" and r["edge"] == "LE"]
    stations = [r["span_station_m"] for r in le]
    assert stations[0] == 0
    assert all(b > a for a, b in zip(stations, stations[1:]))


def test_hinge_line_lies_between_leading_and_trailing_edge(built):
    _, airplane = built
    rows = manufacturing.hinges(airplane)
    assert rows, "the fixture declares a pitch control surface"
    for r in rows:
        wing = next(w for w in airplane.wings if w.name == r["surface"])
        i = r["from_station"]
        le = np.array(wing._compute_xyz_le_of_WingXSec(i), dtype=float).flatten()
        te = np.array(wing._compute_xyz_te_of_WingXSec(i), dtype=float).flatten()
        expect = le + r["hinge_frac_chord"] * (te - le)
        assert (r["x_in_m"], r["y_in_m"], r["z_in_m"]) == pytest.approx(tuple(expect), abs=1e-6)
        # control chord is what is left aft of the hinge
        chord = float(wing.xsecs[i].chord)
        assert r["control_chord_in_m"] == pytest.approx((1 - r["hinge_frac_chord"]) * chord, abs=1e-6)


# ------------------------------------------------------------------- balance

def test_cg_window_is_derived_from_the_same_reference_as_the_constraint(built):
    """SM = (x_np - x_cg) / c_ref. Using any other mean chord moves the target."""
    _, airplane = built
    bal = manufacturing.balance(_result(), airplane)
    c_ref = float(airplane.c_ref)
    assert bal["cg_aft_limit_m"] == pytest.approx(0.52 - 0.08 * c_ref)
    assert bal["cg_fwd_limit_m"] == pytest.approx(0.52 - 0.15 * c_ref)
    assert bal["cg_window_mm"] == pytest.approx((0.15 - 0.08) * c_ref * 1000)


def test_more_static_margin_means_a_more_forward_cg(built):
    _, airplane = built
    bal = manufacturing.balance(_result(), airplane)
    assert bal["cg_fwd_limit_m"] < bal["cg_aft_limit_m"]


def test_balance_degrades_without_a_neutral_point(built):
    _, airplane = built
    assert manufacturing.balance(_result(diagnostics={}), airplane) is None


def test_cg_window_omitted_when_the_run_never_recorded_the_range(built):
    _, airplane = built
    bal = manufacturing.balance(_result(constraints={"static_margin": 0.1}), airplane)
    assert "cg_aft_limit_m" not in bal
    doc = manufacturing.render(_result(constraints={"static_margin": 0.1}), airplane)
    assert "not available" in doc  # says so rather than quietly dropping it


# -------------------------------------------------------------------- render

def test_document_covers_the_build_critical_sections(built, sample_aircraft):
    doc = manufacturing.render(_result(), sample_aircraft.geometry(None), sample_aircraft)
    for heading in ("Balance", "Surfaces", "Control surfaces", "Mass budget"):
        assert heading in doc
    assert "+x aft" in doc  # the datum must never be implicit


def test_negative_zero_never_reaches_the_page(built):
    _, airplane = built
    doc = manufacturing.render(_result(), airplane)
    assert "-0.0" not in doc and "-0 g" not in doc


def test_generic_sections_survive_an_aircraft_without_the_hook(built):
    """The iron rule: an aircraft that declares nothing still gets a document."""
    _, airplane = built

    class Bare:
        pass

    doc = manufacturing.render(_result(), airplane, Bare())
    assert "Surfaces" in doc and "Balance" in doc


def test_write_emits_the_document_and_its_tables(tmp_path, sample_aircraft):
    airplane = sample_aircraft.geometry(None)
    out = manufacturing.write(_result(), airplane, sample_aircraft, tmp_path)
    for name in ("BUILD.md", "edges.csv", "hinges.csv", "surfaces.csv"):
        assert (out / name).is_file(), name
    rows = list(csv.DictReader((out / "edges.csv").open(encoding="utf-8")))
    assert len(rows) == len(manufacturing.edges(airplane))


def test_tabular_hook_sections_become_their_own_csv(tmp_path, sample_aircraft):
    """A cut list is only useful if it can go straight into a spreadsheet."""
    airplane = sample_aircraft.geometry(None)
    out = manufacturing.write(_result(), airplane, sample_aircraft, tmp_path)
    spars = next(p for p in out.glob("*.csv") if "spar" in p.name)
    rows = list(csv.DictReader(spars.open(encoding="utf-8")))
    assert rows and {"od_mm", "wall_mm", "length_mm", "stock_length_mm"} <= set(rows[0])


def test_spar_report_mirrors_the_sizing_constraint():
    """A build doc that re-derives stress its own way could disagree with the
    constraint the optimizer actually enforced."""
    from planeopt import structures

    r = structures.spar_report(0.014, 0.001, 0.5, 20.0)
    sec = structures.tube(0.014, 0.001)
    # reported to 0.1 MPa — bench precision, not solver precision
    assert r["stress_MPa"] == pytest.approx(20.0 * 0.007 / sec["I"] / 1e6, abs=0.05)
    assert r["stress_allow_MPa"] == pytest.approx(
        structures.SIGMA_ALLOW / structures.SAFETY_FACTOR / 1e6
    )
    assert r["mass_g"] == pytest.approx(structures.tube_mass(0.014, 0.001, 0.5) * 1000, abs=0.05)


# ------------------------------------------------- rebuilding a champion

def _optimized(**studies) -> types.RunResult:
    return _result(performance={
        "objective_units": "min",
        "optimization": {"champion": {"dv": None}, **studies},
    })


def test_champion_config_recovers_discrete_choices_from_the_studies():
    """Runs made before the configuration was recorded must still rebuild right."""
    from planeopt.report import assemble

    r = _optimized(
        discrete_studies={"tail_type": {"adopted": "ttail"},
                          "prop_choice": {"adopted": "cam_11x7"}},
        winglet_study={"winglet_rejected": True},
    )
    assert assemble.champion_config(r) == {
        "tail_type": "ttail", "prop_choice": "cam_11x7", "winglet": False,
    }


def test_recorded_configuration_wins_over_the_study_blocks():
    from planeopt.report import assemble

    r = _optimized(
        discrete_studies={"tail_type": {"adopted": "ttail"}},
        winglet_study={"winglet_rejected": True},
    )
    r.performance["optimization"]["champion"]["discrete"] = {"tail_type": "vtail"}
    assert assemble.champion_config(r) == {"tail_type": "vtail"}


def test_evaluation_runs_have_no_discrete_configuration():
    from planeopt.report import assemble

    assert assemble.champion_config(_result(performance={})) == {}


def test_as_champion_applies_then_restores(sample_aircraft):
    """The bug this exists for: rebuilding from dv alone gave the aircraft file's
    defaults, so a regenerated build document grew a winglet the champion had
    rejected."""
    from planeopt.report import assemble

    before = (sample_aircraft.winglet, sample_aircraft.tail_type)
    r = _optimized(discrete_studies={"tail_type": {"adopted": "ttail"}},
                   winglet_study={"winglet_rejected": True})
    with assemble.as_champion(r, sample_aircraft) as cfg:
        assert sample_aircraft.winglet is False
        assert sample_aircraft.tail_type == "ttail"
        assert cfg["winglet"] is False
    assert (sample_aircraft.winglet, sample_aircraft.tail_type) == before


def test_rejected_winglet_never_reaches_the_build_document(sample_aircraft):
    from planeopt.report import assemble

    r = _optimized(winglet_study={"winglet_rejected": True})
    with assemble.as_champion(r, sample_aircraft):
        names = {s["surface"] for s in manufacturing.surfaces(sample_aircraft.geometry(None))}
    assert "winglet" not in names
