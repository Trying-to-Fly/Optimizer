"""Rendering must never be what loses the analysis it is rendering.

`optimize` re-evaluates its champion by calling `solve.run`, inside an
`except Exception` that writes a RunResult holding only the design vector. So
anything that raises in `run`'s artifact tail costs the whole re-evaluation
after the solving is already done.

That happened. The `20260808T145905` battery solved for 342 minutes and wrote
`performance.best: null`, an empty sweep and `constraints: {}` because a Jinja
template had been edited while it ran: the process holds the `report.html`
module it imported hours earlier, while `FileSystemLoader` reads the template
from disk at render time, so the two disagreed and
`TemplateAssertionError: No filter named 'num'` propagated all the way out.

A template edit is the cheapest way to reproduce it and not the only one — a
full disk, a matplotlib font-cache rebuild, or an allocation failure right after
a run that peaked near 14.5 GB all raise in the same place.
"""

from __future__ import annotations

import json

import pytest

from planeopt.report import assemble


@pytest.mark.slow
def test_a_failing_report_does_not_cost_the_evaluation(
    sample_aircraft, sample_mission, tmp_path, monkeypatch
):
    """The regression, end to end through the real pipeline."""
    from planeopt import solve

    def boom(*a, **k):
        raise RuntimeError("no filter named 'num'")

    monkeypatch.setattr(solve.report_html, "render", boom)
    result, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)

    # the analysis survived — this is the whole point
    assert result.performance["best"] is not None
    assert result.performance["best"]["objective_value"] > 0
    assert result.constraints, "constraints were lost with the report"
    assert not (run_dir / "report.html").exists()

    # and the artifact SAYS what is missing, rather than looking complete
    data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    failed = data["diagnostics"]["artifacts_failed"]
    assert "report.html" in failed
    assert "RuntimeError" in failed["report.html"]
    # everything that did not fail is still there
    assert (run_dir / "figures" / "power_curves.png").exists()


@pytest.mark.slow
def test_one_bad_figure_does_not_stop_the_others(
    sample_aircraft, sample_mission, tmp_path, monkeypatch
):
    """Each presentation step is guarded on its own, not as one block.

    Guarding them together would mean a failed three-view also costs the build
    document and the report, which are unrelated to it.
    """
    from planeopt import solve

    monkeypatch.setattr(solve.figures, "three_view",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no space left")))
    result, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)

    data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert list(data["diagnostics"]["artifacts_failed"]) == ["figures/three_view"]
    assert (run_dir / "report.html").exists()
    assert (run_dir / "manufacturing" / "BUILD.md").exists()
    assert result.performance["best"] is not None


def test_write_run_json_can_be_called_again_on_an_existing_run_dir(tmp_path):
    """`solve.run` re-writes run.json once it knows what failed.

    Cheap enough to run without the `slow` mark, and it pins the split that made
    recording the failures possible: `write_run_dir` creates the directory with
    `exist_ok=False`, so the second write had to be a separate function.
    """
    from planeopt.types import RunResult

    result = RunResult(aircraft="a", mission="m", objective="endurance",
                       status="M1", created="2026-08-10T00:00:00")
    run_dir = assemble.write_run_dir(result, tmp_path, [])
    first = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert first["diagnostics"] == {}

    result.diagnostics["artifacts_failed"] = {"report.html": "RuntimeError: boom"}
    assemble.write_run_json(result, run_dir)

    again = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert again["diagnostics"]["artifacts_failed"] == {"report.html": "RuntimeError: boom"}
    # and nothing else moved
    assert again["aircraft"] == "a" and again["created"] == first["created"]
