"""The span flatness sweep: when it is allowed to stop early, and what it is
allowed to spend finding out.

The 2026-07-30 run spent roughly two of its hours re-deriving that its bottom
end contains no aircraft (FINDINGS §14.5.8). Skipping that is worth real time,
but only under an inference the sweep is actually entitled to make — which is
what these pin.

These drive `solve.flatness_sweep` ITSELF. The previous version of this file
re-implemented the loop inside the test, and so passed happily while the shipped
sweep skipped nothing at all for 130.6 minutes: the copy was fed a verdict the
real solver has never once produced. A test that re-implements the code under
test can only ever check the copy.
"""

from __future__ import annotations

import pytest

from planeopt import solve


class _Batch:
    """Stands in for `optimize`'s `batch`: records the jobs asked for, and
    answers each with whatever verdict the test wants."""

    def __init__(self, verdicts=None):
        self.jobs: list[tuple] = []
        self.verdicts = verdicts or {}

    def __call__(self, label, jobs, **kw):
        out = {}
        for key, kw_job in jobs:
            span = round(kw_job["fixed"]["span"], 4)
            self.jobs.append((span, kw_job.get("timeout_min")))
            status = self.verdicts.get(span)
            if status is not None:
                out[key] = {
                    "failed": f"{status} after 131 iterations",
                    "return_status": status,
                    "solve_minutes": 12.0,
                }
            else:
                out[key] = {
                    "objective_value": 100.0 + span,
                    "dv": {"span": span},
                    "solve_minutes": 4.7,
                }
        return out

    @property
    def asked(self) -> list[float]:
        return [s for s, _ in self.jobs]


# IPOPT's own spellings, written out rather than read back from `solve`. A test
# that takes the expected status FROM the code under test cannot tell that code
# is watching for the wrong one — which is the entire bug being fixed here, and
# it would survive a mutation of `PROVEN_INFEASIBLE_STATUS` if these were
# aliases for it.
INFEASIBLE = "Infeasible_Problem_Detected"
TIMEOUT = "Maximum_WallTime_Exceeded"
SKIPPED = "Skipped_Below_Infeasible_Span"


def test_the_statuses_are_IPOPT_s_own_spellings():
    """The gate is a string comparison against a solver's vocabulary, so the
    string is load-bearing: a typo here is a sweep that silently never skips."""
    assert solve.PROVEN_INFEASIBLE_STATUS == INFEASIBLE
    assert solve.SKIPPED_STATUS == SKIPPED


def test_the_sweep_runs_downward_from_the_cap():
    """Direction is the whole basis for stopping early: shrinking span makes the
    constraints harder, so an infeasible member licenses an inference about
    SMALLER spans only. Sweeping upward would license nothing."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    assert b.asked == sorted(b.asked, reverse=True)
    assert b.asked[0] == pytest.approx(2.0)


def test_a_member_is_capped_well_below_the_champion_s_budget():
    """The bug this file exists for was NOT that the sweep lacked a proof — it
    was that it paid 30 minutes per span for an answer no amount of clock
    improves. Every solve that has ever converged on this model took 3.6-5.3
    min; every solve that has ever failed ran to its ceiling. The cap has to sit
    between those, comfortably clear of the slowest success."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    assert {t for _, t in b.jobs} == {solve.FLATNESS_TIMEOUT_MIN}
    # 6.0 min is the slowest FLATNESS member that has ever converged (n = 6,
    # both runs, both chord caps). Not "the slowest solve on the model" — that
    # is tail_type=conventional at 21.5 min, and an earlier version of this
    # assertion was built on a survey that missed it (FINDINGS 15.4). The cap
    # was raised to 20 min on that count (user decision, 2026-07-31): the
    # margin is now against the slowest solve KNOWN to converge on this model,
    # not merely against the slowest flatness member.
    SLOWEST_CONVERGED_FLATNESS_MIN = 6.0
    SLOWEST_CONVERGED_SOLVE_MIN = 21.5
    assert 3 * SLOWEST_CONVERGED_FLATNESS_MIN <= solve.FLATNESS_TIMEOUT_MIN
    assert solve.FLATNESS_TIMEOUT_MIN >= 0.9 * SLOWEST_CONVERGED_SOLVE_MIN
    assert solve.FLATNESS_TIMEOUT_MIN < solve.SOLVE_TIMEOUT_MIN


def test_the_member_cap_is_overridable():
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, span_min=1.5, member_timeout_min=3.0)
    assert {t for _, t in b.jobs} == {3.0}


def test_a_PROVED_infeasible_member_short_circuits_smaller_spans():
    b = _Batch({1.8: INFEASIBLE})
    flat = solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    by_span = {round(e["span"], 4): e for e in flat}

    # 2.0, 1.9 and 1.8 are solved; 1.7, 1.6 and 1.5 are never attempted
    assert b.asked == pytest.approx([2.0, 1.9, 1.8])
    assert by_span[1.8]["return_status"] == INFEASIBLE
    for span in (1.7, 1.6, 1.5):
        assert by_span[span]["return_status"] == SKIPPED
        assert "skipped" in by_span[span]["failed"]
        assert by_span[span]["objective_value"] is None


def test_a_TIMEOUT_never_short_circuits():
    """A timeout certifies nothing. Cascading one would silently discard spans
    that are merely slow — which is exactly the mistake this sweep is trying to
    stop making, in the other direction. This is the case that actually happens
    on the real model, every single run."""
    b = _Batch({1.8: TIMEOUT, 1.7: TIMEOUT, 1.6: TIMEOUT, 1.5: TIMEOUT})
    flat = solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    assert b.asked == pytest.approx([2.0, 1.9, 1.8, 1.7, 1.6, 1.5])
    assert all(SKIPPED not in str(e.get("return_status")) for e in flat)


def test_the_real_2026_07_31_sweep_costs_less_than_it_did():
    """The regression, in the units that matter: four spans timed out at 32.7
    min each for 130.6 minutes and zero skips. Nothing about the ANSWER changes
    at a lower cap — all four still fail, and still say what they missed.

    The bound is deliberately loose. The member cap was 12 min when this test
    was written (4 x 12 = 48 against 130.6) and is 20 by user decision, which
    buys margin against a slow-but-converging member at a cost that is bounded
    and visible. Pinning the exact saving would make this test a tripwire on a
    number that is the user's call, not the sweep's contract.
    """
    b = _Batch({1.8: TIMEOUT, 1.7: TIMEOUT, 1.6: TIMEOUT, 1.5: TIMEOUT})
    solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    spent = sum(t for s, t in b.jobs if s <= 1.8)
    MEASURED_2026_07_31_MIN = 130.6
    assert spent < 4 * solve.SOLVE_TIMEOUT_MIN  # cheaper than the run ceiling
    assert spent < MEASURED_2026_07_31_MIN  # and cheaper than what it did cost


def test_an_all_feasible_sweep_is_unaffected():
    b = _Batch()
    flat = solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)
    by_span = {round(e["span"], 4): e for e in flat}
    assert len(b.asked) == 6
    assert all("failed" not in e for e in flat)
    # every span still reported, ascending, and the objective tied to its own span
    assert [e["span"] for e in flat] == sorted(e["span"] for e in flat)
    assert by_span[2.0]["objective_value"] == pytest.approx(102.0)
    assert by_span[1.5]["objective_value"] == pytest.approx(101.5)


def test_the_sweep_samples_the_span_range_inclusively():
    b = _Batch()
    solve.flatness_sweep(b, span_cap=1.8, n=4, span_min=1.5)
    assert sorted(b.asked) == pytest.approx([1.5, 1.6, 1.7, 1.8])


def _render_flatness(flat: list[dict]) -> str:
    """Just the flatness section of report.html, for a given sweep result."""
    import re
    from types import SimpleNamespace

    from planeopt.report import html

    result = SimpleNamespace(
        aircraft="x", mission="m", objective="endurance", status="s", created="c",
        geometry={}, masses={}, constraints={}, notes=[], diagnostics={},
        performance={"optimization": {
            "champion": {"dv": {"span": 2.0}}, "flatness_span": flat,
        }},
    )
    section = re.search(r"<h2>Flatness sweep.*?</table>", html.render(result), re.S)
    assert section, "the report dropped the flatness sweep entirely"
    return section.group(0)


def test_the_report_shows_every_span_not_only_the_ones_that_converged():
    """The flatness FIGURE plots only spans that returned a number, so a sweep
    whose bottom half is empty renders as a two-point line. Before this table the
    other four spans, and the reason for each, were reachable only from
    run.json — the more interesting half of the answer, invisible in the report
    a person actually reads."""
    b = _Batch({1.8: INFEASIBLE})
    body = _render_flatness(solve.flatness_sweep(b, span_cap=2.0, span_min=1.5))

    for span in ("1.50", "1.60", "1.70", "1.80", "1.90", "2.00"):
        assert span in body
    assert INFEASIBLE in body                    # 1.8, and what it was
    assert body.count("skipped") == 3            # 1.7, 1.6, 1.5
    assert "converged" in body                   # 1.9 and 2.0


def test_the_report_shows_a_real_timeout_sweep_as_six_attempted_spans():
    """What the last run actually produced. The reader has to be able to see
    that four spans were tried, and what each of them missed."""
    b = _Batch({1.8: TIMEOUT, 1.7: TIMEOUT, 1.6: TIMEOUT, 1.5: TIMEOUT})
    body = _render_flatness(solve.flatness_sweep(b, span_cap=2.0, span_min=1.5))
    assert body.count(TIMEOUT) == 4
    assert "skipped" not in body


def test_a_skipped_span_reports_no_minutes_rather_than_zero():
    """It was never attempted, and "0.0" reads as a measured zero."""
    b = _Batch({1.8: INFEASIBLE})
    rows = _render_flatness(solve.flatness_sweep(b, span_cap=2.0, span_min=1.5)).split("<tr>")
    skipped = [r for r in rows if "skipped" in r]
    assert len(skipped) == 3
    assert all("0.0" not in r for r in skipped)


def test_the_run_wide_ceiling_clamps_the_flatness_cap_but_cannot_raise_it():
    """`--solve-timeout-min` is documented as the ceiling for ONE member solve,
    so a user who lowers it must not find the sweep quietly ignoring them.
    Raising it is the asymmetric case: a run-wide ceiling of 60 does not undo a
    12-minute budget that was set from evidence about this phase specifically."""
    lowered = _Batch()
    solve.flatness_sweep(lowered, span_cap=2.0, span_min=1.5, run_timeout_min=2.0)
    assert {t for _, t in lowered.jobs} == {2.0}

    raised = _Batch()
    solve.flatness_sweep(raised, span_cap=2.0, span_min=1.5, run_timeout_min=60.0)
    assert {t for _, t in raised.jobs} == {solve.FLATNESS_TIMEOUT_MIN}


# ---------------------------------------------------- what spans it samples
# HANDOFF issue 0f: the range was `linspace(1.5, cap, 6)`, a constant inherited
# from a 2.2 m cap with an interior optimum. Once the optimum sat ON the cap,
# four of six spans were 10-25% below it in a region that holds no aircraft — so
# the sweep spent most of a run re-deriving that the bottom of its own range was
# empty, while the question it exists to answer is about the NEIGHBOURHOOD of
# the optimum, which 1.5 m is not in for a 2.0 m design.


def test_the_range_follows_the_incumbent_rather_than_a_constant():
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, incumbent_span=2.0)
    assert min(b.asked) == pytest.approx(solve.FLATNESS_SPAN_FRACTION * 2.0)
    assert max(b.asked) == pytest.approx(2.0)

    # and it moves with the champion: an interior optimum gets a range around
    # ITSELF, not around a cap it never reached
    b2 = _Batch()
    solve.flatness_sweep(b2, span_cap=3.0, incumbent_span=2.2)
    assert min(b2.asked) == pytest.approx(solve.FLATNESS_SPAN_FRACTION * 2.2)
    assert max(b2.asked) == pytest.approx(3.0)


def test_the_sweep_never_samples_past_the_declared_cap():
    """The cap is a declared manufacturing limit; a member past it is not an
    aircraft anyone agreed to build, however good it would be."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, incumbent_span=5.0)
    assert max(b.asked) == pytest.approx(2.0)
    assert min(b.asked) == pytest.approx(solve.FLATNESS_SPAN_FRACTION * 2.0)


def test_a_cap_with_no_incumbent_falls_back_to_the_cap():
    """`optimize` always has a champion by this phase, but the function is
    public and must not depend on being given one."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0)
    assert min(b.asked) == pytest.approx(solve.FLATNESS_SPAN_FRACTION * 2.0)


def test_an_explicit_span_min_still_wins():
    """The override is what a deliberate wide sweep uses — and what every
    cascade test above uses, so those keep testing the cascade and not this."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, span_min=1.2, incumbent_span=2.0)
    assert min(b.asked) == pytest.approx(1.2)


def test_the_sampled_range_brackets_the_incumbent_closely_enough_to_be_a_slope():
    """The point of the change: neighbouring samples must be close enough that
    the difference between them is a local slope rather than a different
    aeroplane. At the 2026-07-31 champion the old range's steps were 100 mm on a
    2.0 m wing and crossed a region where the chord cap was binding."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, incumbent_span=2.0)
    steps = [round(a - c, 6) for a, c in zip(b.asked, b.asked[1:])]
    assert all(s == pytest.approx(steps[0]) for s in steps)
    assert steps[0] < 0.07  # 60 mm on a 2 m wing, against the old 100 mm


def test_the_derived_range_never_goes_under_the_declared_floor():
    """A `fixed` value outside a variable's own box is an INVALID problem, not
    an infeasible one: IPOPT returns `Invalid_Problem_Definition` and the member
    comes back as a solver error rather than as a span. A champion at 1.7 m with
    a declared floor of 1.5 would otherwise ask for 1.445."""
    b = _Batch()
    solve.flatness_sweep(b, span_cap=2.0, incumbent_span=1.7, span_floor=1.5)
    assert min(b.asked) == pytest.approx(1.5)
    assert max(b.asked) == pytest.approx(2.0)

    # and where the floor does not bind, it changes nothing
    b2 = _Batch()
    solve.flatness_sweep(b2, span_cap=3.0, incumbent_span=3.0, span_floor=1.5)
    assert min(b2.asked) == pytest.approx(0.85 * 3.0)
