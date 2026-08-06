"""Two-stage discrete studies (M5.3, EXECUTION_PLAN §6 / HANDOFF issue 3).

A discrete study costs one full NLP re-solve per candidate, which is why the
prop study priced 3 of 443 shipped tables and adopted one that screened 119th of
441 (FINDINGS §12). `solve.screen_discrete` ranks candidates at the champion's
operating point with no NLP at all, so the candidate set can be the catalogue
and the run still pays for four solves.

The screen is a SHORTLISTER and never a verdict — everything it returns is
re-solved in full. What these tests pin is that it shortlists honestly: it
prices mass as well as power, it survives a candidate the airframe cannot use,
and it puts the eventual champion in the shortlist on the one battery where the
answer is already known.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planeopt import solve

REPO = Path(__file__).parent.parent

#: The 2026-07-31 champion's own multistart solve — the incumbent operating
#: point a screen would have run against in that battery.
#:
#: It lives under `runs/`, which is gitignored, so a fresh clone does not have
#: it and cannot regenerate it in less than a multi-hour battery. Skipping is
#: therefore the honest outcome — but it has to be a SKIP. Read at import time
#: with no guard, the missing file raised during collection, which pytest treats
#: as a collection error and which aborts the entire suite: 411 unrelated tests
#: went unrun on a clean checkout, on every platform, and the summary blamed a
#: propeller test. A checkout that cannot run its own tests reads as a broken
#: checkout.
_INCUMBENT_PATH = REPO / "runs/_checkpoints_chord275/multistart__nominal.json"
try:
    INCUMBENT = json.loads(_INCUMBENT_PATH.read_text())
except (OSError, ValueError) as _e:
    INCUMBENT = None
    pytestmark = pytest.mark.skip(
        reason=f"needs the 2026-07-31 battery's checkpoint at {_INCUMBENT_PATH}, "
               f"which is not in version control ({_e.__class__.__name__})"
    )
#: That run's measured shadow price, minutes per gram of structure.
SHADOW_PER_G = -0.0776


@pytest.fixture()
def screen(sample_aircraft, sample_mission):
    def run(candidates=None, top_n=4, shadow_per_g=SHADOW_PER_G):
        cands = candidates if candidates is not None else [
            c for c in sample_aircraft.discrete_options["prop_choice"]
            if c != sample_aircraft.prop_choice
        ]
        return solve.screen_discrete(
            sample_aircraft, sample_mission, "prop_choice", cands,
            INCUMBENT, top_n, shadow_per_g,
        )
    return run


def test_the_screen_finds_the_champion_the_full_study_found(screen):
    """The acceptance criterion: on the 2026-07-31 battery, eight full re-solves
    adopted `cam_12x10` at 141.43 min. The screen must reach for the same prop
    without solving anything — and it prices it to within a fraction of a
    minute, which is the evidence that a shortlist built this way is safe."""
    r = screen()
    assert r["shortlist"][0] == "ancf_12x10"
    top = r["ranking"][0]
    assert top["screened_objective"] == pytest.approx(141.4, abs=1.0)
    assert len(r["shortlist"]) == 4


def test_mass_is_charged_at_the_run_s_own_shadow_price(screen):
    """Without this the screen is systematically biased toward big propellers —
    a 14 in disc that arrives weightless is free thrust on the longest lever the
    airframe has, which is the defect that kept the diameter cap at 11 in."""
    r = screen()
    by_key = {e["candidate"]: e for e in r["ranking"]}
    big = by_key["ancf_14x9"]
    assert big["mass_delta_g"] > 30, "a 14 in prop must weigh more than an 11 in"
    # charged, and in the direction that makes it look worse
    assert big["screened_objective"] < big["powertrain_only"]
    assert big["screened_objective"] == pytest.approx(
        big["powertrain_only"] + SHADOW_PER_G * big["mass_delta_g"], abs=1e-6
    )


def test_without_a_shadow_price_the_screen_is_powertrain_only(screen):
    """A run whose mass-bump member failed has no shadow price. The screen still
    has to work — it just cannot see mass, and must not pretend otherwise."""
    r = screen(shadow_per_g=None)
    assert all(
        e["screened_objective"] == pytest.approx(e["powertrain_only"])
        for e in r["ranking"]
    )
    assert r["shadow_price_obj_per_gram"] is None


def test_a_candidate_the_airframe_cannot_use_is_recorded_not_raised(screen):
    """A prop too fine or too coarse for this design at this speed is a screen
    RESULT — it is how the screen says "not this one". Raising would sink a
    battery hours in, over a candidate nobody chose."""
    r = screen()
    assert r["unreachable"], "expected at least one unusable table in 65"
    assert not (set(r["unreachable"]) & set(r["shortlist"]))
    # and every candidate is accounted for exactly once
    assert len(r["ranking"]) + len(r["unreachable"]) == 65


def test_the_screen_restores_the_attribute(sample_aircraft, screen):
    """It sets `prop_choice` 65 times. Leaving it set would silently re-solve
    the champion as some other propeller."""
    before = sample_aircraft.prop_choice
    screen()
    assert sample_aircraft.prop_choice == before


def test_a_broken_candidate_does_not_take_the_screen_down(sample_aircraft, screen):
    r = screen(candidates=["ancf_12x10", "no_such_prop_key", "ancf_11x10"])
    assert r["shortlist"][0] == "ancf_12x10"
    assert "no_such_prop_key" in r["unreachable"]
    assert sample_aircraft.prop_choice != "no_such_prop_key"


def test_the_aircraft_declares_the_screen_rather_than_the_framework_guessing(
    sample_aircraft,
):
    """Opt-in per attribute, because the screen is only valid where the
    attribute changes nothing the airframe solve fixed. True of a propeller,
    false of a tail type — and the framework cannot tell them apart without
    knowing what an attribute MEANS."""
    declared = getattr(sample_aircraft, "discrete_screen", {})
    assert declared == {"prop_choice": 4}
    for attr in ("tail_type", "fuselage_topology", "wing_dihedral_form"):
        assert attr not in declared, f"{attr} changes the airframe — cannot be screened"


def test_the_shortlist_is_smaller_than_the_catalogue_it_searched(sample_aircraft):
    """The whole point: search wide, solve narrow."""
    n_candidates = len(sample_aircraft.discrete_options["prop_choice"])
    assert n_candidates > 20
    assert sample_aircraft.discrete_screen["prop_choice"] < n_candidates / 4
