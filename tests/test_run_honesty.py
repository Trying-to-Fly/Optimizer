"""What a run is entitled to CLAIM, as distinct from what it computed.

Every property here comes from the 2026-08-05 battery, which converged cleanly
and whose artifact was nonetheless wrong about four things — not in its numbers,
in its claims:

  - it reported 142.09 min as the aeroplane's best, when the sweep's own optimum
    was 143.01 min and only the minimum-speed requirement stood between them;
  - it reported V = 8.0 m/s "infeasible" on the strength of a message about
    IPOPT's step size;
  - it reported a static margin of 0.0800 for an aircraft whose local dCm/dCL at
    its own trim alpha is negative;
  - it reported multistart and the flatness sweep at 0.0 minutes, which reads as
    "skipped" and meant "resumed".

None of those needs an aircraft to reproduce, which is the point: they are
properties of how the run describes itself.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from planeopt import solve

MAXIMIZE = 1


def _pt(v, obj):
    return {"V_ms": v, "objective_value": obj}


# --- the minimum-speed requirement, priced --------------------------------


def test_v_min_price_names_the_peak_the_requirement_excludes():
    """The 2026-08-05 shape: the sweep peaks below v_min, so the headline number
    is the requirement's, not the airframe's."""
    airworthy = [_pt(8.5, 139.45), _pt(9.0, 143.01), _pt(9.5, 142.09), _pt(10.0, 139.23)]
    best = _pt(9.5, 142.09)

    priced = solve.v_min_price(airworthy, best, v_min_ms=9.5, sign=MAXIMIZE)

    assert priced is not None
    assert priced["unconstrained_best_V_ms"] == 9.0
    assert priced["cost_of_v_min"] == pytest.approx(143.01 - 142.09)


def test_no_price_when_the_optimum_is_already_legal():
    """An interior optimum owes v_min nothing, and saying otherwise would put a
    scary note on every run that does not need one."""
    airworthy = [_pt(9.5, 140.0), _pt(10.0, 143.0), _pt(10.5, 141.0)]

    assert solve.v_min_price(airworthy, _pt(10.0, 143.0), 9.5, MAXIMIZE) is None


def test_the_price_follows_the_objective_direction():
    """A minimized objective (mass, energy per km) peaks the other way; the
    requirement is still what excludes the winner."""
    airworthy = [_pt(8.0, 10.0), _pt(9.0, 25.0)]

    priced = solve.v_min_price(airworthy, _pt(9.0, 25.0), v_min_ms=9.0, sign=-1)

    assert priced["unconstrained_best_V_ms"] == 8.0
    assert priced["cost_of_v_min"] == pytest.approx(15.0)


def test_an_empty_sweep_prices_nothing_rather_than_raising():
    """`run` already raises its own, far better, error when nothing trims — this
    must not pre-empt it with a max() on an empty sequence."""
    assert solve.v_min_price([], _pt(9.5, 1.0), 9.5, MAXIMIZE) is None


# --- the filters that run BEFORE v_min is ever consulted --------------------
#
# The first `vtail_rcv2` evaluation (2026-08-06) reported 53.76 min at 16.5 m/s
# — the FASTEST speed it swept, for an endurance aeroplane. The spec design is
# nose-heavy enough to need more than its 6.53 deg of trim throw at every
# slower speed, so twelve of thirteen trimmed points were dropped before
# `v_min_price` was called, and it correctly reported None. Nothing else said
# anything. The numbers below are that run's.


def _tp(v, obj, defl):
    return {"V_ms": v, "objective_value": obj, "deflection_deg": defl}


RCV2_THROW_CAP = 6.5294335627444235
RCV2_RULES = {
    "trim_throw": lambda s: abs(s["deflection_deg"]) <= RCV2_THROW_CAP + 1e-3
}
#: V, endurance and ruddervator deflection from that run's sweep, thinned.
RCV2_SWEEP = [
    _tp(10.5, 61.83, -24.61), _tp(12.0, 71.16, -16.38), _tp(14.0, 66.13, -10.52),
    _tp(16.0, 56.27, -6.95), _tp(16.5, 53.76, -6.29),
]


def test_a_filter_that_chose_the_answer_is_named_and_priced():
    """The rcv2 shape: every better speed was excluded by ONE rule, and the
    reported number is whatever that rule happened to leave behind."""
    priced = solve.airworthiness_price(
        RCV2_SWEEP, _tp(16.5, 53.76, -6.29), RCV2_RULES, v_min_ms=9.5, sign=MAXIMIZE
    )

    assert priced is not None
    assert priced["unfiltered_best_V_ms"] == 12.0
    assert priced["peak_excluded_by"] == ["trim_throw"]
    assert priced["cost_of_airworthiness"] == pytest.approx(71.16 - 53.76)
    # the count is the finding: one awkward point dropping out is not the same
    # claim as a filter having chosen the answer
    assert priced["excluded_by_rule"]["trim_throw"] == [10.5, 12.0, 14.0, 16.0]


def test_a_design_inside_its_own_limits_is_priced_nothing():
    """Otherwise every healthy run carries a note saying it was crippled."""
    healthy = [_tp(10.0, 60.0, -2.0), _tp(11.0, 71.0, -1.5), _tp(12.0, 65.0, -1.0)]

    assert solve.airworthiness_price(
        healthy, _tp(11.0, 71.0, -1.5), RCV2_RULES, 9.5, MAXIMIZE
    ) is None


def test_points_below_v_min_are_not_double_reported():
    """`v_min_price` owns those, and pricing them here as well would make one
    excluded peak read as two separate findings."""
    sweep = [_tp(9.0, 99.0, -1.0), _tp(10.0, 60.0, -1.0)]

    assert solve.airworthiness_price(
        sweep, _tp(10.0, 60.0, -1.0), RCV2_RULES, 9.5, MAXIMIZE
    ) is None


def test_the_price_follows_a_minimized_objective_too():
    """A worse peak is the filters costing nothing, not a negative price — which
    is why the comparison is signed and not an absolute difference."""
    sweep = [_tp(10.0, 25.0, -20.0), _tp(11.0, 10.0, -1.0)]

    priced = solve.airworthiness_price(
        sweep, _tp(11.0, 10.0, -1.0), RCV2_RULES, 9.5, sign=-1
    )
    assert priced is None  # the excluded point is WORSE for a minimized objective

    priced = solve.airworthiness_price(
        [_tp(10.0, 4.0, -20.0), _tp(11.0, 10.0, -1.0)],
        _tp(11.0, 10.0, -1.0), RCV2_RULES, 9.5, sign=-1,
    )
    assert priced["unfiltered_best_V_ms"] == 10.0
    assert priced["cost_of_airworthiness"] == pytest.approx(6.0)


def test_nothing_at_or_above_v_min_prices_nothing():
    assert solve.airworthiness_price(
        [_tp(8.0, 99.0, -1.0)], _tp(8.0, 99.0, -1.0), RCV2_RULES, 9.5, MAXIMIZE
    ) is None


# --- a static margin that changes sign inside its own window ---------------


def test_sign_flip_is_caught_under_a_positive_reported_margin():
    """The champion's actual numbers. The regression says 0.0800 and passes; the
    local slope at the trim alpha says the aeroplane is unstable there."""
    sm = {
        "static_margin": 0.08000015740224872,
        "sm_local_slopes": [
            {"alpha": 3.68, "sm_local": 0.1867953836284154},
            {"alpha": 4.68, "sm_local": 0.13828341836237237},
            {"alpha": 5.68, "sm_local": -0.022067618955063283},
            {"alpha": 6.68, "sm_local": -0.019115899958615457},
        ],
    }

    worst = solve.sm_sign_flip(sm)

    assert worst is not None
    assert worst["alpha"] == 5.68  # the MOST negative, not merely the first
    assert worst["sm_local"] < 0


def test_a_margin_positive_throughout_raises_nothing():
    sm = {
        "static_margin": 0.12,
        "sm_local_slopes": [{"alpha": 4.0, "sm_local": 0.13}, {"alpha": 6.0, "sm_local": 0.11}],
    }

    assert solve.sm_sign_flip(sm) is None


def test_an_already_negative_margin_is_not_double_reported():
    """The guard exists to catch a margin that LOOKS fine. A design whose
    reported margin is itself negative already fails `sm_in_range` loudly."""
    sm = {"static_margin": -0.03, "sm_local_slopes": [{"alpha": 4.0, "sm_local": -0.05}]}

    assert solve.sm_sign_flip(sm) is None


def test_missing_slopes_are_not_an_accusation():
    """A caller that did not ask for the diagnostic must not be told its
    aircraft is unstable."""
    assert solve.sm_sign_flip({"static_margin": 0.09}) is None
    assert solve.sm_sign_flip({"static_margin": 0.09, "sm_local_slopes": []}) is None


# --- non-convergence is not infeasibility ----------------------------------


def test_a_trim_failure_is_classified_as_the_solver_giving_up():
    """`aero.trim`'s wording, verbatim from the 2026-08-05 artifact."""
    e = RuntimeError(
        "trim failed at V=8.0: The iteration is not making good progress, as "
        "measured by the \n improvement from the last ten iterations. / "
        "least-squares residual too large"
    )

    assert solve._is_trim_failure(e) is True


def test_a_propulsion_failure_is_not_a_trim_failure():
    """A chain that cannot close IS a statement about the aeroplane, and must
    keep saying so rather than being softened into 'unknown'."""
    assert solve._is_trim_failure(ValueError("advance ratio beyond the fitted table")) is False
    assert solve._is_trim_failure(RuntimeError("no motor operating point")) is False


# --- a resumed phase must not read as a skipped one ------------------------


def test_the_cache_counts_what_it_served_per_phase(tmp_path):
    """0.0 minutes plus 'from checkpoint' is a resume; 0.0 minutes alone reads
    as a phase that never ran."""
    cache = solve._SolveCache(tmp_path, "abc123abc123")
    cache.put("multistart", "nominal", {"objective_value": 1.0})
    cache.put("multistart", "perturbed_0", {"objective_value": 2.0})
    cache.put("flatness sweep", "2.0", {"objective_value": 3.0})

    assert cache.resumed == {}  # writing is not resuming

    assert cache.get("multistart", "nominal") is not None
    assert cache.get("multistart", "perturbed_0") is not None
    assert cache.get("flatness sweep", "2.0") is not None

    assert cache.resumed == {"multistart": 2, "flatness sweep": 1}


def test_a_miss_counts_as_nothing(tmp_path):
    cache = solve._SolveCache(tmp_path, "abc123abc123")

    assert cache.get("multistart", "never_solved") is None
    assert cache.resumed == {}


def test_a_corrupt_entry_is_a_miss_not_a_resume(tmp_path):
    """It will be re-solved, so counting it as resumed would overstate what came
    off disk."""
    cache = solve._SolveCache(tmp_path, "abc123abc123")
    cache._path("multistart", "nominal").write_text("{not json", encoding="utf-8")

    assert cache.get("multistart", "nominal") is None
    assert cache.resumed == {}


def test_numpy_valued_sweep_points_price_correctly():
    """Sweep points carry numpy scalars; the arithmetic must not care."""
    airworthy = [_pt(np.float64(9.0), np.float64(143.01)), _pt(np.float64(9.5), np.float64(142.09))]

    priced = solve.v_min_price(airworthy, airworthy[1], 9.5, MAXIMIZE)

    assert float(priced["cost_of_v_min"]) == pytest.approx(143.01 - 142.09)


# ------------------------------------- a run must record what produced it
# `run.json` recorded span, area and mean chord and no design vector, so a run
# could not be reproduced from its own artifact: none of those invert back to
# taper, fullness, washout or the tail variables. Rebuilding the 2026-08-05
# champion meant re-running the optimizer. Everything else in the artifact is an
# OUTPUT; this is the input that produced them.


class _AC:
    # ClassVar because it mirrors the aircraft convention: DV_DEFAULTS is a
    # class-level declaration, never per-instance state.
    DV_DEFAULTS: ClassVar[dict] = {"span": 1.8, "taper": 0.6, "washout_tip": -1.5}


def test_an_override_is_recorded_MERGED_over_the_defaults():
    """The complete vector, not a diff — a reader must not have to go and find
    the defaults, in a file that has since changed, to know what was built."""
    got = solve.effective_design_vector(_AC(), {"span": 1.9})
    assert got == {"span": 1.9, "taper": 0.6, "washout_tip": -1.5}


def test_the_spec_design_records_an_EMPTY_vector_rather_than_the_defaults():
    """The trap this field is easiest to get wrong on, and it was.

    `aircraft.geometry(dv=None)` is documented as "the fixed v1.2 spec design;
    else the parametric architecture" — the two are materially DIFFERENT
    aeroplanes, not two spellings of one (see the test below). Filling this in
    with DV_DEFAULTS would put an authoritative-looking vector in the artifact
    that rebuilds something the run never evaluated, which is strictly worse
    than recording nothing. `{}` is correct because `geometry({} or None)` is
    `geometry(None)`.
    """
    assert solve.effective_design_vector(_AC(), None) == {}


def test_the_two_geometries_really_are_different_aeroplanes(sample_aircraft):
    """Pinned because the whole design of the field above rests on it, and
    because it is surprising enough to be 'simplified' away later.

    Measured 2026-08-06 on the sample aircraft: 7% in wing area, 3.5% in
    projected span, 7% in mean chord.
    """
    from planeopt import geometry

    spec = geometry.summarize(sample_aircraft.geometry(None))
    parametric = geometry.summarize(
        sample_aircraft.geometry(dict(sample_aircraft.DV_DEFAULTS))
    )
    assert spec["area_m2"] != pytest.approx(parametric["area_m2"], rel=1e-3)
    assert spec["mean_chord_m"] != pytest.approx(parametric["mean_chord_m"], rel=1e-3)


def test_numpy_scalars_are_coerced_because_json_refuses_them():
    """An aircraft may declare defaults with numpy scalars, and a field that
    cannot serialize is a field that is not in the artifact.

    `np.int64` is the one that matters: `np.float64` subclasses `float` so a
    naive isinstance check catches it, while `np.int64` subclasses neither and
    would reach `json.dump` uncoerced — failing after the solving was done.
    """
    import json

    class _NP:
        DV_DEFAULTS: ClassVar[dict] = {}

    got = solve.effective_design_vector(
        _NP(), {"span": np.float64(1.8), "n_panels": np.int64(4)}
    )
    assert json.loads(json.dumps(got)) == {"span": 1.8, "n_panels": 4.0}


def test_a_discrete_flag_is_not_turned_into_a_number():
    """`bool` IS a `numbers.Real`, so an unguarded coercion would record
    winglet=1.0 and rebuild the aircraft with a float where it declared a
    switch."""
    got = solve.effective_design_vector(_AC(), {"winglet": True})
    assert got["winglet"] is True


def test_an_aircraft_without_declared_defaults_does_not_raise():
    """`DV_DEFAULTS` is an aircraft-level convention, accessed defensively
    elsewhere in the framework (recolour.py) — the artifact must degrade to the
    override alone rather than crash a finished run at write time."""
    assert solve.effective_design_vector(object(), {"span": 2.0}) == {"span": 2.0}
    assert solve.effective_design_vector(object(), None) == {}


@pytest.mark.slow  # ~50 s — a real M1 evaluation, no NLP
def test_the_recorded_vector_rebuilds_the_geometry_the_run_reported(
    sample_aircraft, sample_mission, tmp_path
):
    """The property the field exists for, end to end: a run directory alone is
    enough to rebuild the aeroplane it describes.

    Compared summary-to-summary rather than against `b_ref` — the artifact
    distinguishes `span_m` from `span_projected_m` and a reference span is
    neither, so asserting on one would pass or fail for the wrong reason.
    """
    import json

    from planeopt import geometry
    from planeopt.report import assemble

    dv = dict(sample_aircraft.DV_DEFAULTS)
    # A NARROW sweep on purpose. The default is 18 speed points and each is a
    # full trim + propulsion solve, which put this test past ten minutes on
    # its own — and what is under test is the design vector, not the power
    # curve. 10.0-11.0 brackets the champion trim point (10.5 m/s).
    result, _ = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path,
                          dv=dv, v_sweep=(10.0, 11.0, 0.5))
    run_dir = assemble.write_run_dir(result, tmp_path / "out", [])
    on_disk = json.loads((run_dir / "run.json").read_text())

    assert on_disk["design_vector"] == result.design_vector
    assert on_disk["diagnostics"]["design_source"] == "parametric"
    rebuilt = geometry.summarize(
        sample_aircraft.geometry(on_disk["design_vector"] or None)
    )
    for key, was in result.geometry.items():
        if isinstance(was, float):
            assert rebuilt[key] == pytest.approx(was, rel=1e-9), key


@pytest.mark.slow  # ~25 s
def test_a_spec_design_run_says_it_was_the_spec_design(
    sample_aircraft, sample_mission, tmp_path
):
    """The empty vector must be readable as a statement, not as an omission."""
    result, _ = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path,
                          v_sweep=(10.0, 11.0, 0.5))
    assert result.design_vector == {}
    assert result.diagnostics["design_source"] == "spec"


# ------------------------------------- a truncated run must say it is truncated
# `--max-iter` exists so the whole pipeline can be exercised in seconds instead
# of hours (graph construction, every study, the artifacts). What it produces is
# a COMPLETE artifact — champion, studies, sensitivities, a build document —
# describing an aeroplane no solver ever finished converging. This project's
# recurring defect is the claim a run is not entitled to make (FINDINGS §20),
# and this would be the easiest one yet to make by accident.


def test_the_iteration_cap_actually_reaches_the_solver(monkeypatch):
    """The dangerous failure is not a wrong cap, it is a cap that does nothing.

    A `--max-iter 3` run that silently solved to convergence would burn the
    hours it was invoked to avoid; one that silently ignored the flag while
    LOOKING truncated would be worse. So this pins the value arriving at
    `_solve_nlp` rather than merely being accepted by the CLI.
    """
    seen = []
    monkeypatch.setattr(
        solve, "_solve_nlp",
        lambda aircraft, mission, **kw: seen.append(kw) or {"objective_value": 1.0},
    )
    solve._solve_many(object(), object(), [("a", {}), ("b", {})], parallel=1,
                      max_iter=3)

    assert [kw["max_iter"] for kw in seen] == [3, 3], "every member, not just one"


def test_a_job_may_still_override_the_cap_per_member(monkeypatch):
    """`_solve_many` injects defaults; an explicit per-job kwarg wins, the same
    way `timeout_min` already behaves."""
    seen = []
    monkeypatch.setattr(
        solve, "_solve_nlp",
        lambda aircraft, mission, **kw: seen.append(kw) or {"objective_value": 1.0},
    )
    solve._solve_many(object(), object(), [("a", {"max_iter": 7})], parallel=1,
                      max_iter=3)

    assert seen[0]["max_iter"] == 7


def test_the_default_cap_is_the_declared_constant():
    """Left alone, nothing changes — the flag is opt-in and a normal run is
    still a normal run."""
    import inspect

    for fn in (solve._solve_nlp, solve._solve_many, solve.optimize):
        assert (
            inspect.signature(fn).parameters["max_iter"].default
            == solve.SOLVE_MAX_ITER
        ), fn.__name__


# --- and a battery where EVERY member fails ---------------------------------
#
# The first `--max-iter 3` run ever attempted (2026-08-06) crashed after 2.5
# minutes on `ValueError: max() iterable argument is empty`, with no artifact
# and no diagnosis. Two separate defects met: a truncated member was recorded as
# FAILED, which at `--max-iter 3` is every member by construction, and then
# `optimize` selected a champion from the empty list with a bare `max()`.
# `run` has raised a proper diagnosis for the same shape since M1.


def _failed(status, **extra):
    return {"failed": f"{status} after 3 iterations", "return_status": status, **extra}


def test_a_battery_with_no_survivors_says_why_instead_of_max_of_empty():
    """The bare `max()` told the reader nothing after paying for every solve."""
    err = solve.no_survivors_error(
        ["nominal", "perturbed_1"],
        [_failed("Infeasible_Problem_Detected"), _failed("Infeasible_Problem_Detected")],
    )

    message = str(err)
    assert "no champion" in message
    assert "Infeasible_Problem_Detected [nominal, perturbed_1]" in message
    assert "every one of the 2" in message


def test_a_mixture_of_causes_is_not_flattened_to_one():
    """Every member infeasible, every member timing out, and a mixture are three
    different fixes; a message naming one cause picks the wrong one twice."""
    err = solve.no_survivors_error(
        ["a", "b"], [_failed("Maximum_WallTime_Exceeded"), _failed("Restoration_Failed")]
    )

    assert "Maximum_WallTime_Exceeded [a]" in str(err)
    assert "Restoration_Failed [b]" in str(err)


def test_the_closest_miss_rides_along_when_a_member_recorded_one():
    """`_worst_violations` already knows which constraint could not be met, and
    that is the first thing anyone would go looking for next."""
    err = solve.no_survivors_error(
        ["a"], [_failed("Restoration_Failed", violations=[{"what": "L == weight_n"}])]
    )

    assert "Closest miss on any member: L == weight_n" in str(err)


# --- when NOTHING in the sweep is legal ------------------------------------
#
# `candidates = legal if legal else feasible` silently changes what "best"
# means. The first `vtail_rcv2` battery (2026-08-06) hit it: nine of eighteen
# speeds failed to trim and all nine that trimmed exceeded the control throw, so
# the run reported a champion trimming at -27.55 deg against a 6.53 deg cap,
# with a static margin of 0.439 against a required [0.08, 0.15]. The only trace
# was `sm_in_range: false` in a table beside a cap the artifact never printed.
#
# `airworthiness_price` cannot catch this and is not meant to: it asks which
# rule excluded a BETTER point, and here every point was excluded.

RCV2_LIMITS = {
    "trim_throw": ("trim deflection", lambda s: abs(s["deflection_deg"]), 6.5294, " deg"),
}


def test_a_violated_rule_is_quoted_with_both_numbers():
    """"violates trim_throw" sends the reader to the aircraft file; "27.55 deg
    against a 6.53 deg limit" does not — and the cap appears nowhere else."""
    got = solve.rule_violations(
        _tp(12.5, 44.71, -27.553), RCV2_RULES, RCV2_LIMITS
    )

    assert [v["rule"] for v in got] == ["trim_throw"]
    assert got[0]["value"] == pytest.approx(27.553)
    assert got[0]["limit"] == pytest.approx(6.5294)
    assert "27.55 deg against a 6.529 deg limit" in got[0]["text"]


def test_a_legal_point_reports_no_violations():
    assert solve.rule_violations(_tp(12.5, 44.71, -3.0), RCV2_RULES, RCV2_LIMITS) == []


def test_a_rule_with_no_way_to_quote_it_degrades_to_silence():
    """A predicate added without a matching limit entry must not raise KeyError
    inside a finished run — the diagnostic is the last thing that should be able
    to destroy hours of solving."""
    rules = {**RCV2_RULES, "mystery": lambda s: False}

    got = solve.rule_violations(_tp(12.5, 44.71, -27.553), rules, RCV2_LIMITS)

    assert [v["rule"] for v in got] == ["trim_throw"]


def test_an_undeclared_limit_is_skipped_rather_than_formatted_as_none():
    """`trim_deflection_limit_deg` is optional — an aircraft that declares no
    cap has no violation to report, not a 'None deg limit'."""
    limits = {"trim_throw": ("trim deflection", lambda s: 1.0, None, " deg")}

    assert solve.rule_violations(_tp(12.5, 44.71, -27.553), RCV2_RULES, limits) == []


def test_the_reeval_tolerance_is_one_number_the_run_and_the_test_share():
    """`test_m3_optimize_smoke` asserted this and the artifact never mentioned
    it, so a 64.16 min gap on a 120 min champion shipped unremarked. Two copies
    of a threshold is how that happens twice."""
    import inspect

    from planeopt import solve as s

    assert 0 < s.NLP_REEVAL_GAP_FRAC < 1
    # comments stripped: the prose in `optimize` quotes the old literal while
    # explaining why it is no longer spelled out, and a check that cannot tell
    # code from commentary would forbid saying so
    code = "\n".join(
        line for line in inspect.getsource(s.optimize).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "NLP_REEVAL_GAP_FRAC" in code, "the run must read the declared number"
    assert "0.1 *" not in code, "and must not re-spell it"


def test_a_member_with_no_status_is_reported_as_unknown_not_dropped():
    """A worker that died before the solver produced stats still has to appear —
    a cause list that silently omits members is how a crash reads as a quiet
    infeasibility."""
    err = solve.no_survivors_error(["a"], [{"failed": "worker died"}])

    assert "unknown [a]" in str(err)


# --- the case above, end to end (needs a real aero evaluation) --------------

#: The champion `vtail_rcv2` returned on 2026-08-06 at `--max-iter 3`. Pinned
#: as data because the run directory it came from was a scratch artifact, and
#: this is the only aeroplane this project has produced for which NO speed in
#: the sweep is airworthy. Not optimized — that is the point; what it
#: reproduces is the FALLBACK, not a design.
RCV2_ILLEGAL_CHAMPION = {
    "ballast_kg": 0.06282218278514194,
    "c_root": 0.26391043211434456,
    "cs_frac": 0.23604430383472771,
    "d_exp": 0.5114776683683473,
    "dihedral_tip": 3.108708241417302,
    "eta_break": 0.2686540986342541,
    "fin_c_root": 0.13380840053218196,
    "fin_height": 0.1997596912423295,
    "fin_sweep": 15.134897835573843,
    "fin_taper": 0.7271782089117856,
    "fullness": 1.1101424174951524,
    "le_shear": 0.07021809936227577,
    "pod_bay": 0.4334615525559903,
    "pod_bay_end": 0.48632163252680094,
    "pod_nose": 0.04233996303142498,
    "pod_tail": 0.16427102824636516,
    "pod_wh": 0.8128986737399786,
    "pod_xs": 1.0425625827484761,
    "span": 1.801961561620828,
    "spar_od_center": 0.010906108322096432,
    "spar_od_outer": 0.009908234330043572,
    "spar_wall_center": 0.0010453029498954996,
    "spar_wall_outer": 0.0010193286396070493,
    "t_c_root": 0.16718743496643365,
    "t_span": 0.4180725537812581,
    "t_sweep": 8.098563637955715,
    "t_taper": 0.8245619841014549,
    "tail_arm": 0.5713654105202417,
    "taper": 0.715614837572725,
    "washout_tip": -2.5419382322340445,
    "wl_cant": 71.32494439750583,
    "wl_cr": 0.7532922990370441,
    "wl_len": 0.1210473893962054,
    "wl_taper": 0.6989365674506756,
    "wl_toe": -1.0528114238144235,
    "x_airspeed_board": 0.44997844918983,
    "x_battery": 0.14156494779147188,
    "x_bec_pi": 0.30710343508019605,
    "x_buzzer": 0.43481143664900157,
    "x_companion_pi": 0.26110657725597636,
    "x_esc": 0.28010602118739913,
    "x_flight_controller": 0.3591506708060532,
    "x_gps_compass": 0.3836812689985093,
    "x_receiver_elrs": 0.41055273958080374,
    "x_telemetry_sik": 0.2740740857139824,
}


@pytest.mark.solve  # a full 18-point sweep on the heavier aeroplane, ~20 min
def test_a_sweep_with_no_legal_point_says_so_at_note_zero(
    rcv2_aircraft, sample_mission, tmp_path
):
    """Nine of eighteen speeds fail to trim and all nine that trim exceed the
    6.53 deg throw cap, so `candidates` falls back to `feasible` and the run
    reports the least-bad ILLEGAL point. Before this it did so in silence."""
    result, _ = solve.run(
        rcv2_aircraft, sample_mission, runs_root=tmp_path,
        dv=RCV2_ILLEGAL_CHAMPION,
    )

    assert result.diagnostics["candidates_source"] == "feasible_fallback"
    broken = {v["rule"] for v in result.diagnostics["reported_point_violations"]}
    assert "trim_throw" in broken
    # the loudest thing the artifact says, ahead of every standing caveat
    assert "NO AIRWORTHY OPERATING POINT EXISTS" in result.notes[0]
    # and the numbers are IN the sentence, not left to the aircraft file
    assert "against a" in result.notes[0]
