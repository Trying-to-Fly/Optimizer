"""What `tools/price_caps.py` can express, and what its report admits.

Two defects found 2026-08-07 by using it on the `20260807T061330` battery:

  - it could express only THREE of that battery's six lost members, so half the
    evidence could not be re-run at all. The list had been scoped from the
    2026-08-06 battery, which lost a different set.
  - its report printed cells from SIX different commits as one table and said
    nothing. The matrix invites exactly one operation — subtract two cells and
    call the difference the price of a cap — and that is only valid inside one
    tree, because a model change moves every objective with it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from planeopt import solve

TOOL = Path(__file__).resolve().parent.parent / "tools" / "price_caps.py"


@pytest.fixture(scope="module")
def pc():
    spec = importlib.util.spec_from_file_location("price_caps", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- what it can express ---------------------------------------------------


@pytest.mark.parametrize(
    "member",
    ["winglet_off", "winglet_continuous_cant", "mass_bump", "dihedral_polyhedral2"],
)
def test_every_member_the_battery_lost_can_be_re_run(pc, member):
    assert member in pc.MEMBERS


def test_the_winglet_member_matches_what_solve_actually_does(pc):
    """`_wl_prep` clears the winglet AND raises the cant ceiling to 88. Setting
    only one of the two would re-run a different aeroplane under the same name —
    the "same label, different aeroplane" trap section 4 of the study is about."""
    assert pc.MEMBERS["winglet_continuous_cant"]["set"] == {
        "winglet": False,
        "tip_dihedral_max_deg": 88.0,
    }


def test_the_mass_bump_is_the_same_twenty_grams_solve_uses(pc):
    assert pc.MEMBERS["mass_bump"]["kw"] == {"extra_mass_kg": 0.020}


class _Winged:
    winglet = True


def test_a_perturbed_start_is_asked_of_solve_not_reimplemented(pc):
    """The draws are seeded, so copying them into the tool would work today and
    desynchronize silently the first time that block is edited. Pinned by
    comparing against `solve` rather than against a frozen literal, which is the
    whole point — a frozen literal here would BE the second source of truth."""
    spec = pc.member_spec("multistart_perturbed_1", _Winged())

    assert spec["kw"]["inits"] == solve.multistart_inits(_Winged(), 2)[1]


def test_the_perturbed_sequence_depends_on_the_aircraft(pc):
    """The draw COUNT per start depends on `winglet`, so start N of a winged
    aircraft is not start N of an unwinged one. A tool that ignored that would
    re-run a start the battery never took."""

    class _Bare:
        winglet = False

    assert solve.multistart_inits(_Winged(), 2)[1] != solve.multistart_inits(_Bare(), 2)[1]


def test_an_unknown_member_is_refused_rather_than_guessed(pc):
    with pytest.raises(SystemExit):
        pc.member_spec("no_such_member", _Winged())


# --- the pod-length levers -------------------------------------------------


def test_the_row_that_actually_blocks_the_battery_is_priceable(pc):
    """Five of six failures missed on the motor row and none of the four caps
    the study started with touches it. These two buy pod LENGTH, which is what
    that row is short of."""
    assert pc.RELAXATIONS["fineness_9.0"]["set"] == {"fineness_max": 9.0}
    assert pc.RELAXATIONS["boat_tail_1.5"]["set"] == {"boat_tail_min_d_eq": 1.5}


# --- provenance ------------------------------------------------------------


def _cells(*commits):
    return {
        f"m{i}|none": {"member": f"m{i}", "relax": "none", "status": "converged",
                       "objective_value": 100.0 + i, "solve_minutes": 1.0,
                       "commit": c}
        for i, c in enumerate(commits)
    }


def test_one_tree_is_stated_rather_than_left_implied(pc, capsys):
    pc._print_provenance(_cells("abc1234", "abc1234"))

    out = capsys.readouterr().out
    assert "all cells measured at abc1234" in out
    assert "TREES IN THIS TABLE" not in out


def test_a_table_spanning_two_trees_says_so(pc, capsys):
    pc._print_provenance(_cells("abc1234", "def5678"))

    out = capsys.readouterr().out
    assert "2 TREES IN THIS TABLE" in out
    assert "abc1234" in out and "def5678" in out


def test_the_warning_does_not_forbid_the_comparison_outright(pc, capsys):
    """It is a flag to check, not a verdict: stage 5's exact Hessian spans two of
    these trees and IS solution-preserving (`nominal|none` reproduces across it
    to eleven significant figures). Wording that called every cross-tree
    difference invalid would have thrown away a real measurement."""
    pc._print_provenance(_cells("abc1234", "def5678"))

    out = capsys.readouterr().out
    assert "until the trees are shown to be solution-preserving" in out
    assert "nominal|none" in out


def test_a_cell_with_no_commit_is_named_not_hidden(pc, capsys):
    """The row that says whether the design is AIRWORTHY was the one row whose
    tree could not be identified, because `reevaluate` never recorded one."""
    cells = _cells("abc1234")
    cells["nominal|none:reeval"] = {"member": "nominal", "relax": "none:reeval",
                                    "status": "reevaluated"}

    pc._print_provenance(cells)

    assert "UNRECORDED" in capsys.readouterr().out


def test_the_reeval_cell_now_records_its_tree(pc):
    """Fixed at the source as well as reported: `_head_commit` is what every
    other cell uses, so there is one answer to 'which tree' rather than two."""
    import inspect

    assert '"commit": _head_commit()' in inspect.getsource(pc.reevaluate)
    assert pc._head_commit()  # non-empty inside a git checkout


def test_the_committed_study_data_still_parses(pc):
    """It is appended to by hand across sessions and machines; a malformed line
    would take the whole report down."""
    path = TOOL.parent.parent / "docs" / "studies" / "rcv2_cap_pricing" / "cells.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows
    assert all("member" in r and "relax" in r for r in rows)
