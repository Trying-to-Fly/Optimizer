"""End-to-end M0 gate: `run` produces a complete artifact directory."""

import json


def test_run_writes_artifacts(sample_aircraft, sample_mission, tmp_path):
    from planeopt import solve

    result, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)

    assert (run_dir / "run.json").exists()
    assert (run_dir / "report.html").exists()
    assert (run_dir / "figures").is_dir()

    data = json.loads((run_dir / "run.json").read_text())
    assert data["objective"] == "endurance"
    assert abs(data["performance"]["usable_energy_wh"] - 47.36) < 0.01
    assert "M0" in data["status"]

    html = (run_dir / "report.html").read_text()
    assert "vtail_sample" in html and "endurance" in html


def test_report_rerender_roundtrip(sample_aircraft, sample_mission, tmp_path):
    from planeopt import solve
    from planeopt.report import assemble, html as html_mod

    _, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)
    reloaded = assemble.load(run_dir)
    rendered = html_mod.render(reloaded)
    assert "vtail_sample" in rendered
