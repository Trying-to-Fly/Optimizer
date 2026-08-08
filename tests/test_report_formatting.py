"""Two things the champion report said badly, on every run it has ever written.

Neither is a wrong number — they are the report describing a correct number in a
way that reads as something else, which is the same shape as the defects the
fifteenth session found in its claims rather than its arithmetic.
"""

from __future__ import annotations

import pytest

from planeopt.report.html import _fmt, _pairs


class TestNegativeZero:
    """A solution on a zero floor comes back as -3e-17, and `%.4f` shows a minus.

    The 20260807 champion printed `ballast_kg  -0.0000` in the design-variable
    table, `-0` in the re-solve battery's ballast column and `nose_ballast  -0`
    in the mass budget — three places claiming a negative quantity of lead, on
    rows whose own declared box starts at zero.
    """

    @pytest.mark.parametrize("value", [-0.0, -1e-17, -3e-9, -0.00001])
    @pytest.mark.parametrize("spec", ["%.0f", "%.3f", "%.4f", "%+.0f"])
    def test_a_value_that_rounds_to_zero_loses_its_minus(self, value, spec):
        assert not _fmt(value, spec).startswith("-")

    @pytest.mark.parametrize("value,spec,expected", [
        (-0.0001, "%.4f", "-0.0001"),
        (-0.5, "%.1f", "-0.5"),
        (-1.0, "%.0f", "-1"),
        (-0.0228, "%.3f", "-0.023"),
        (-0.07094, "%.4f", "-0.0709"),
    ])
    def test_a_real_negative_keeps_its_sign(self, value, spec, expected):
        """The zeros are stripped, never the magnitude.

        `static_margin_gap` is genuinely -0.023 and `shadow price` genuinely
        -0.0709 /g; a filter that swallowed those would be a far worse bug than
        the one it fixes.
        """
        assert _fmt(value, spec) == expected

    @pytest.mark.parametrize("value,spec,expected", [
        (0.0, "%.3f", "0.000"),
        (2.0, "%.4f", "2.0000"),
        (122.6193, "%.1f", "122.6"),
    ])
    def test_positive_and_zero_are_untouched(self, value, spec, expected):
        assert _fmt(value, spec) == expected

    def test_a_bool_is_not_formatted_as_a_number(self):
        """`True` is an int in Python and `%.3f` would render it as 1.000."""
        assert _fmt(True) == "True"
        assert _fmt(False) == "False"

    def test_a_string_passes_through(self):
        assert _fmt("legal") == "legal"


class TestMappingConstraints:
    """`sm_read_at` is a dict, and the constraints table's fallback was `{{ v }}`.

    So the row printed a Python repr — braces, quotes and
    `9.741593732349461` — for the field HANDOFF names as the first thing to
    read when the NLP and the re-evaluation disagree about the static margin.
    """

    def test_a_mapping_becomes_readable_pairs(self):
        rows = _pairs({
            "nlp_V_ms": 9.741593732349461,
            "reeval_V_ms": 9.5,
            "candidates_source": "legal",
        })
        assert rows == [
            ("nlp_V_ms", "9.742"),
            ("reeval_V_ms", "9.5"),
            ("candidates_source", "legal"),
        ]

    def test_floats_are_shortened_but_integers_and_text_are_not(self):
        rows = dict(_pairs({"n": 16, "why": "two different operating points"}))
        assert rows["n"] == "16"
        assert rows["why"] == "two different operating points"

    def test_a_tiny_value_in_a_mapping_keeps_its_magnitude(self):
        """`%.4g` shows -1e-18 as -1e-18, and that is the RIGHT answer here.

        The negative-zero rule only fires when every digit rendered is a zero.
        A mapping value that is genuinely 1e-18 away from zero has not been
        rounded away by its own format, so there is nothing misleading to fix —
        and silently zeroing it would be the report claiming a measurement it
        did not make.
        """
        assert dict(_pairs({"gap": -1e-18}))["gap"] == "-1e-18"

    def test_an_empty_mapping_is_no_rows_rather_than_an_error(self):
        assert _pairs({}) == []


def test_the_rendered_report_has_no_negative_zero_and_no_python_repr(tmp_path):
    """End to end through Jinja, because the filters are only half the fix.

    Each call site had to be routed through them, and a site that was missed
    would still print `-0` while every unit test above passed — which is what
    happened to `nose_ballast` on the first attempt.
    """
    from planeopt.report import html
    from planeopt.types import RunResult

    result = RunResult(
        aircraft="fixture_v1", mission="m", objective="endurance", status="M3",
        created="2026-08-08T00:00:00",
        design_vector={"ballast_kg": -2e-17},
        geometry={"span_m": 2.0},
        masses={
            "auw_kg": 2.1, "x_cg_m": 0.5032, "wing_loading_g_dm2": 45.4,
            "components": {"nose_ballast": {"mass_kg": -3e-18, "station_mm": 210.0},
                           "motor": {"mass_kg": 0.17, "station_mm": 243.3}},
        },
        # No "best" block: the operating-point table needs a dozen keys that
        # have nothing to do with this, and it is guarded on its own presence.
        performance={
            "objective_units": "min",
            "optimization": {
                "champion": {"dv": {"ballast_kg": -2e-17, "span": 2.0},
                             "static_margin": 0.08},
                "multistart_objective_spread": 7e-10,
                "shadow_price_obj_per_gram": -0.07094,
                # the re-solve battery's ballast column, the third site
                "resolve_battery": {"printed_mass_x1.10": {
                    "objective_value": 115.0, "delta": -7.1, "span": 2.0,
                    "static_margin": 0.08, "ballast_kg": -1e-19}},
            },
        },
        constraints={
            "static_margin_gap": -0.0228,
            "sm_read_at": {"nlp_V_ms": 9.741593732349461, "reeval_V_ms": 9.5,
                           "why": "two different operating points"},
        },
    )
    page = html.render(result)
    assert ">-0<" not in page and ">-0.0000<" not in page and ">-0.000<" not in page
    assert "nlp_V_ms&#39;:" not in page and "{&#39;" not in page
    # the real negative survives, and the mapping is still SHOWN rather than
    # dropped the way the Geometry table drops mappings
    assert "-0.023" in page
    assert "nlp_V_ms" in page and "9.742" in page
