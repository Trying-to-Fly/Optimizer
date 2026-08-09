"""What `tools/bughunt/audit_run.py` reads, and the three things it misread.

The audit tool is the instrument HANDOFF points at for checking a finished
battery, so a field it reads from the wrong key is worse than one it does not
read at all: it prints a confident line about a field the artifact does carry.
All three properties here were reproduced against the
`20260807T061330-rcv2_endurance` artifact before being fixed.

  - `performance.objective` has never existed, so the headline line read
    "objective <ABSENT> min" on every artifact ever written.
  - the station check looked for `x_m`, which lives in the geometry export and
    the manufacturing sheet; `masses.components` carries `station_mm`
    (`solve.py`), so the fc58751 defect was reported as live on artifacts that
    had fixed it.
  - `candidates_source` was not read at all — the one field FINDINGS 28 calls
    "the first thing to read in its artifact", because a `feasible_fallback`
    headline is invisible in every other field.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

AUDIT = Path(__file__).resolve().parent.parent / "tools" / "bughunt" / "audit_run.py"


def load_audit():
    spec = importlib.util.spec_from_file_location("audit_run", AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_run(tmp_path: Path, **over) -> Path:
    """A minimal artifact shaped like the real one, legal unless told otherwise."""
    run = {
        "status": "M3: full-vehicle optimization",
        "objective": "endurance",
        "design_vector": {"span": 2.0},
        "notes": ["a standing caveat that is not the headline"],
        "performance": {
            "objective_units": "min",
            "best": {"objective_value": 122.6193158052834, "V_ms": 9.5},
        },
        "masses": {"components": {"motor": {"mass_kg": 0.17, "station_mm": 243.3}}},
        "diagnostics": {"design_source": "parametric", "candidates_source": "legal"},
    }
    run.update(over)
    d = tmp_path / "20260807T061330-run"
    d.mkdir()
    (d / "run.json").write_text(json.dumps(run))
    return d


def audit_text(tmp_path, capsys, **over) -> str:
    load_audit().main(str(write_run(tmp_path, **over)))
    return capsys.readouterr().out


def test_the_headline_objective_is_read_from_where_it_is_written(tmp_path, capsys):
    """It is `objective` plus `performance.best`, not `performance.objective`."""
    out = audit_text(tmp_path, capsys)
    assert "endurance = 122.6193158052834 min at V = 9.5 m/s" in out
    assert "objective         <ABSENT>" not in out


def test_a_component_carrying_its_station_is_not_reported_as_missing_one(
    tmp_path, capsys
):
    """The key is `station_mm`. Looking for `x_m` fails on every real artifact."""
    out = audit_text(tmp_path, capsys)
    assert "components carry mass without station" not in out


def test_a_component_really_missing_its_station_still_says_so(tmp_path, capsys):
    """The check has to keep failing for the defect it was written for."""
    out = audit_text(
        tmp_path, capsys, masses={"components": {"motor": {"mass_kg": 0.17}}}
    )
    assert "components carry mass without station" in out


def test_candidates_source_is_reported_at_all(tmp_path, capsys):
    out = audit_text(tmp_path, capsys)
    assert "candidates_source legal" in out


def test_a_fallback_headline_is_reported_as_not_an_answer(tmp_path, capsys):
    """FINDINGS 28: `feasible_fallback` means no operating point was airworthy.

    `airworthiness_price` is null in exactly this case — there is no better
    legal point to name — so a reader who checks only that field concludes the
    filters cost nothing. This line is the one that must not be silent.
    """
    out = audit_text(
        tmp_path,
        capsys,
        diagnostics={
            "design_source": "parametric",
            "candidates_source": "feasible_fallback",
            "reported_point_violations": [
                "trim deflection 17.4 deg against a 6.572 deg limit"
            ],
        },
    )
    assert "NO LEGAL OPERATING POINT" in out
    assert "trim deflection 17.4 deg against a 6.572 deg limit" in out


@pytest.mark.parametrize("source", ["legal", "feasible_fallback"])
def test_the_audit_never_raises_on_either_source(tmp_path, capsys, source):
    """A reading aid that crashes on an artifact tells the reader nothing."""
    audit_text(
        tmp_path,
        capsys,
        diagnostics={"design_source": "parametric", "candidates_source": source},
    )


# --- the diagnostics added 2026-08-07, which the aid was blind to ----------
#
# Both were added to `run.json` the same day and the reading aid was not
# updated with them — the identical defect fixed above, one session later.


def test_a_shadow_price_from_the_wrong_aeroplane_is_called_out(tmp_path, capsys):
    """The +20 g bump is re-solved on the shipped design so the quoted rate is
    ITS rate. When that solve fails the value falls back to the multistart
    screen's, measured before the studies chose the design — and the artifact
    reports the number either way."""
    out = audit_text(
        tmp_path,
        capsys,
        performance={
            "objective_units": "min",
            "best": {"objective_value": 122.12, "V_ms": 9.5},
            "optimization": {
                "shadow_price_obj_per_gram": -0.07094,
                "shadow_price_source": {
                    "source": "multistart_screen",
                    "measured_on_objective": 105.818,
                    "reported_beside_champion": 122.123,
                    "final_bump_failed": "Maximum_WallTime_Exceeded",
                },
            },
        },
    )
    assert "NOT THIS DESIGN'S RATE" in out
    assert "105.818" in out and "122.123" in out


def test_a_shadow_price_measured_on_the_shipped_design_is_not_accused(tmp_path, capsys):
    out = audit_text(
        tmp_path,
        capsys,
        performance={
            "objective_units": "min",
            "best": {"objective_value": 122.12, "V_ms": 9.5},
            "optimization": {
                "shadow_price_obj_per_gram": -0.0711,
                "shadow_price_source": {"source": "final_design"},
            },
        },
    )
    assert "from final_design" in out
    assert "NOT THIS DESIGN'S RATE" not in out


def test_a_binding_pod_limit_is_reported(tmp_path, capsys):
    """Neither limit can appear in `active_bounds` — that reports design-variable
    BOX bounds and both of these are constraint rows — so if the aid does not
    print them, nothing does."""
    out = audit_text(
        tmp_path,
        capsys,
        diagnostics={
            "design_source": "parametric",
            "candidates_source": "legal",
            "afterbody": {
                "fineness": 8.00000008, "fineness_max": 8.0,
                "fineness_ceiling_active": True,
                "boat_tail_d_eq": 1.7999998, "boat_tail_min_d_eq": 1.8,
                "boat_tail_floor_active": True, "theta_max_deg": 18.91,
            },
        },
    )
    assert "FINENESS CEILING BINDING" in out
    assert "BOAT-TAIL FLOOR STILL ACTIVE" in out
    assert "do NOT delete the floor" in out


def test_pod_limits_clear_of_their_bounds_are_reported_quietly(tmp_path, capsys):
    out = audit_text(
        tmp_path,
        capsys,
        diagnostics={
            "design_source": "parametric",
            "candidates_source": "legal",
            "afterbody": {
                "fineness": 6.20, "fineness_max": 8.0,
                "fineness_ceiling_active": False,
                "boat_tail_d_eq": 2.4, "boat_tail_min_d_eq": 1.8,
                "boat_tail_floor_active": False, "theta_max_deg": 13.0,
            },
        },
    )
    assert "f=6.2" in out
    assert "BINDING" not in out and "STILL ACTIVE" not in out


def test_an_older_artifact_says_it_is_older_rather_than_reading_as_clean(
    tmp_path, capsys
):
    """The 20260807T061330 battery predates both fields. Silence there would be
    indistinguishable from "measured, and fine" — which is the exact confusion
    this whole file exists to prevent."""
    out = audit_text(
        tmp_path,
        capsys,
        performance={
            "objective_units": "min",
            "best": {"objective_value": 122.6, "V_ms": 9.5},
            "optimization": {"shadow_price_obj_per_gram": -0.0709},
        },
        diagnostics={
            "design_source": "parametric",
            "candidates_source": "legal",
            "afterbody": {"fineness": 8.00000008, "theta_max_deg": 18.91},
        },
    )
    assert "no provenance recorded" in out
    assert "artifact predates them" in out
