"""`planeopt brief` — the CAD round-trip's handoff document.

Renders from a finished run, so what matters here is what it does with an
artifact that is not exactly the one this build would have written.
"""

from __future__ import annotations

import json

import pytest

from planeopt.report import assemble, brief

CHAMPION = {
    "objective_value": 110.0, "V_ms": 9.5, "auw_kg": 1.8,
    "static_margin": 0.1, "dv": {"span": 2.0},
}


def _run(tmp_path, champion):
    run_dir = tmp_path / "20260725T120000-endurance_sample-fixture"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps({
        "aircraft": "fixture", "mission": "endurance_sample",
        "objective": "endurance", "status": "M3",
        "created": "2026-07-25T12:00:00",
        "performance": {
            "objective_units": "min",
            "optimization": {"champion": champion, "shadow_price_obj_per_gram": -0.08},
        },
    }), encoding="utf-8")
    return assemble.load(run_dir)


class _NoHook:
    name = "fixture"


def _champion_line(text):
    return next(l for l in text.splitlines() if l.startswith("**Champion"))


def test_a_healthy_champion_renders_its_margin(tmp_path):
    line = _champion_line(brief.render(_run(tmp_path, CHAMPION), _NoHook()))
    assert "static margin 0.100" in line


@pytest.mark.parametrize(
    ("label", "champion"),
    [
        ("null", {**CHAMPION, "static_margin": None}),
        ("absent", {k: v for k, v in CHAMPION.items() if k != "static_margin"}),
    ],
)
def test_a_champion_without_a_margin_renders_a_dash(tmp_path, label, champion):
    """`.get(key, default)` covers a key that is ABSENT and not one that is
    present and NULL — a distinction JSON makes and this line did not, so a
    champion carrying `"static_margin": null` formatted None and took the whole
    command down with a TypeError."""
    line = _champion_line(brief.render(_run(tmp_path, champion), _NoHook()))
    assert "static margin —" in line
    assert "110.0 min" in line, "the rest of the headline still renders"


def test_a_hook_row_with_no_value_reads_as_a_dash(tmp_path):
    """"None" printed in a design brief reads as a bug in the brief."""
    class Hooked:
        name = "fixture"

        def design_brief(self, dv, shadow_per_g=None):
            return {"Packaging": {"nose bay": None, "boom": 0.605}}

    text = brief.render(_run(tmp_path, CHAMPION), Hooked())
    assert "- **nose bay:** —" in text
    assert "None" not in text
