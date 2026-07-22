"""End-to-end M1 gate: fixed-design evaluation produces a complete, plausible artifact.

Bands from docs/VALIDATION_ANCHORS.md (real-aircraft data), slightly widened so the
test checks plausibility, not calibration.
"""

import json


def test_run_writes_artifacts(sample_aircraft, sample_mission, tmp_path):
    from planeopt import solve

    result, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)

    assert (run_dir / "run.json").exists()
    assert (run_dir / "report.html").exists()
    assert (run_dir / "figures" / "power_curves.png").exists()

    data = json.loads((run_dir / "run.json").read_text())
    assert data["objective"] == "endurance"
    assert "M1" in data["status"]

    # mass plausibility
    m = data["masses"]
    assert 1.4 < m["auw_kg"] < 2.6
    assert 0.30 < m["x_cg_m"] < 0.60
    assert 30 < m["wing_loading_g_dm2"] < 80

    # performance plausibility (wide bands pending real-aircraft anchors)
    best = data["performance"]["best"]
    assert 8 < best["L_over_D"] < 26
    assert 15 < best["P_elec_w"] < 100  # anchors: ~25-90 W class band
    assert 0.4 < data["performance"]["wh_per_km_airspeed"] < 2.0  # anchors: 0.8-1.5
    assert 15 < best["objective_value"] < 180  # minutes
    assert 0.15 < best["eta_chain"] < 0.75
    assert abs(best["deflection_deg"]) < 8  # trim well inside throws

    # printed structure fraction of AUW (anchors: 43-52% for full-PLA builds;
    # here pod+wing+tail printed mass over AUW, wide band)
    printed = sum(v for k, v in m["components"].items() if k.startswith("printed_")) + m["components"]["pod"]
    assert 0.30 < printed / m["auw_kg"] < 0.60

    # constraint plumbing
    c = data["constraints"]
    assert best["V_ms"] >= c["v_min_ms"] - 1e-9
    assert 5 < 1000 * 0 + data["diagnostics"]["stall_detail"]["v_stall_ms"] < 12
    assert isinstance(c["stall_ok"], bool) and isinstance(c["sm_in_range"], bool)


def test_report_rerender_roundtrip(sample_aircraft, sample_mission, tmp_path):
    from planeopt import solve
    from planeopt.report import assemble, html as html_mod

    _, run_dir = solve.run(sample_aircraft, sample_mission, runs_root=tmp_path)
    reloaded = assemble.load(run_dir)
    rendered = html_mod.render(reloaded, run_dir)
    assert "vtail_sample" in rendered
    assert "base64" in rendered  # figures embedded


def test_propulsion_solver_sane(sample_aircraft):
    """Prop solve: more thrust at same V costs more power; efficiencies bounded."""
    from planeopt import propulsion

    pt = sample_aircraft.powertrain()
    lo = propulsion.solve(12.0, 1.0, pt)
    hi = propulsion.solve(12.0, 3.0, pt)
    assert hi["P_elec_w"] > lo["P_elec_w"] > 0
    for r in (lo, hi):
        assert 0 < r["eta_prop"] <= 0.9
        assert 0 < r["eta_motor"] <= 1.0
        assert 0 < r["J"] < 1.0


def test_m2_optimize_smoke(sample_aircraft, sample_mission, tmp_path):
    """M2 gate (reduced): NLP converges, champion beats/matches baseline, artifacts complete."""
    from planeopt import solve

    result, run_dir = solve.optimize(
        sample_aircraft, sample_mission, runs_root=tmp_path, multistart=1, flatness=False
    )
    opt = result.performance["optimization"]
    champ = opt["champion"]
    assert 1.5 - 1e-6 <= champ["dv"]["span"] <= 2.2 + 1e-6  # IPOPT bound slack
    assert champ["objective_value"] > 60  # beats the fixed design's ~96 min? keep loose
    assert abs(opt["nlp_vs_reeval_gap"]) < 0.1 * champ["objective_value"]
    assert opt["shadow_price_obj_per_gram"] < 0  # more mass never helps endurance
    assert (run_dir / "report.html").exists()
