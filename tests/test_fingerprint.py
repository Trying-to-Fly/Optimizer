"""The guard that stops a battery resuming checkpoints from a different model.

The defect these exist for: `_SolveCache` keys entries by (phase label, member
key) and nothing else, so a resume after the model moved produced ONE artifact
containing members solved under TWO models — and every member converged, so
nothing looked wrong. A whole battery was discarded for that on 2026-08-01
(FINDINGS section 18.7), caught only by a human remembering the dates.

Note what is NOT asserted anywhere here: a specific fingerprint value. Pinning
the digest would mean editing this file on every legitimate model change, which
trains the reader to update the expected value without asking why it moved —
exactly the reflex the guard exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from planeopt import fingerprint, solve
from planeopt.types import MissionSpec


PKG = Path(fingerprint.__file__).resolve().parent


class _Aircraft:
    name = "fake"


def in_a_fresh_process(aircraft, mission) -> str:
    """`model_fingerprint` as the NEXT run would compute it.

    The package half is memoized per process on purpose (see `_package_digest`),
    so a test that edits the tree and asks again is really asking "what would the
    next run see?" — and clearing the cache is how that question is spelled.
    """
    fingerprint._package_digest.cache_clear()
    return fingerprint.model_fingerprint(aircraft, mission)


@pytest.fixture(autouse=True)
def _fresh_package_digest():
    """The package half is memoized per PROCESS — correct in production (one run
    per process, model code fixed at import) and wrong inside a test session that
    repoints `_PKG` at a temporary tree."""
    fingerprint._package_digest.cache_clear()
    yield
    fingerprint._package_digest.cache_clear()


@pytest.fixture()
def mission():
    return MissionSpec(name="m", objective="endurance")


# --------------------------------------------------------------- the partition

def test_every_module_is_either_model_or_declared_presentation():
    """A new module must not join the package and silently escape the hash.

    This is the maintainability half of the design: `NON_MODEL` is an explicit
    exclusion list, so anything unlisted is fingerprinted by default. The failure
    mode this prevents is someone adding `planeopt/aero_v2.py`, it changing every
    objective, and checkpoints from before it happily resuming afterwards.
    """
    # Every entry, not just the `.py` ones: `py.typed` and `data/` are model
    # inputs too, and the point of the assertion is that NOTHING is unaccounted
    # for. `__pycache__` is derived and skipped by `_iter_files` itself.
    top_level = {p.name for p in PKG.iterdir() if p.name != "__pycache__"}
    excluded = set(fingerprint.NON_MODEL)
    assert excluded <= top_level, f"NON_MODEL names something absent: {excluded - top_level}"

    hashed = {
        p.relative_to(PKG).parts[0]
        for p in fingerprint._iter_files(PKG, exclude=fingerprint.NON_MODEL)
    }
    assert hashed == top_level - excluded


def test_the_shipped_prop_tables_are_part_of_the_model(mission):
    """A refitted table moves every objective that reads it, and it is the change
    least likely to be remembered — 661 of them ship."""
    tables = list((PKG / "data" / "props").glob("*.json"))
    assert tables, "the fixture assumes shipped prop tables"
    assert tables[0] in set(fingerprint._iter_files(PKG, exclude=fingerprint.NON_MODEL))


def test_derived_bytecode_is_not_hashed():
    """`.pyc` would make the fingerprint depend on what had been imported yet."""
    files = list(fingerprint._iter_files(PKG, exclude=fingerprint.NON_MODEL))
    assert not [p for p in files if p.suffix in (".pyc", ".pyo")]
    assert not [p for p in files if "__pycache__" in p.parts]


# --------------------------------------------------------------- what it covers

def test_the_same_inputs_give_the_same_fingerprint(mission):
    assert fingerprint.model_fingerprint(_Aircraft(), mission) == \
        fingerprint.model_fingerprint(_Aircraft(), mission)


def test_a_changed_mission_value_changes_the_fingerprint():
    """The GUI rewrites `missions/<name>.py` from its form on every queue, so the
    same filename can carry a different wind speed — and the checkpoint directory
    is named from that filename."""
    base = MissionSpec(name="m", objective="endurance")
    windier = MissionSpec(name="m", objective="endurance", v_wind_ms=4.0)
    assert fingerprint.model_fingerprint(_Aircraft(), base) != \
        fingerprint.model_fingerprint(_Aircraft(), windier)


def test_a_changed_model_source_changes_the_fingerprint(tmp_path, monkeypatch, mission):
    monkeypatch.setattr(fingerprint, "_PKG", tmp_path)
    (tmp_path / "aero.py").write_text("LL_VORTEX_CORE_RADIUS = 1e-8", encoding="utf-8")
    before = in_a_fresh_process(_Aircraft(), mission)

    (tmp_path / "aero.py").write_text("LL_VORTEX_CORE_RADIUS = 1e-4", encoding="utf-8")
    assert in_a_fresh_process(_Aircraft(), mission) != before, (
        "this is the exact 2026-08-01 change that invalidated a battery"
    )


def test_renaming_a_module_changes_the_fingerprint(tmp_path, monkeypatch, mission):
    """Content-only hashing would miss it, and a rename changes what imports
    resolve to."""
    monkeypatch.setattr(fingerprint, "_PKG", tmp_path)
    (tmp_path / "aero.py").write_text("x = 1", encoding="utf-8")
    before = in_a_fresh_process(_Aircraft(), mission)

    (tmp_path / "aero.py").rename(tmp_path / "aero2.py")
    assert in_a_fresh_process(_Aircraft(), mission) != before


def test_a_presentation_change_does_NOT_change_the_fingerprint(tmp_path, monkeypatch, mission):
    """The other half of being useful: editing the GUI must not discard hours of
    checkpoints, or the guard gets switched off."""
    monkeypatch.setattr(fingerprint, "_PKG", tmp_path)
    (tmp_path / "aero.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "gui").mkdir()
    (tmp_path / "gui" / "window.py").write_text("BUTTON = 'New run…'", encoding="utf-8")
    before = in_a_fresh_process(_Aircraft(), mission)

    (tmp_path / "gui" / "window.py").write_text("BUTTON = 'New run'", encoding="utf-8")
    assert in_a_fresh_process(_Aircraft(), mission) == before


def test_a_base_class_in_another_package_is_covered(mission):
    """An experiment package is a SUBCLASS of the sample living in its own
    directory (`aircraft/vtail_span300/` over `aircraft/vtail_sample/`).
    Fingerprinting only the subclass would miss most of the aeroplane."""
    repo = Path(__file__).resolve().parent.parent
    base_dir, sub_dir = repo / "aircraft" / "vtail_sample", repo / "aircraft" / "vtail_span300"
    if not sub_dir.is_dir():  # the experiment package may be retired away
        pytest.skip("no subclassing aircraft package on disk")

    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("_fp_span300", sub_dir / "aircraft.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_fp_span300"] = module
    spec.loader.exec_module(module)
    covered = fingerprint.aircraft_source_dirs(module.AIRCRAFT)
    assert sub_dir in covered and base_dir in covered


# ------------------------------------------------------------------- the cache

def test_a_different_model_does_not_resume_the_old_checkpoints(tmp_path):
    old = solve._SolveCache(tmp_path, "aaaaaaaaaaaa")
    old.put("phase", "m0", {"objective_value": 222.12})

    new = solve._SolveCache(tmp_path, "bbbbbbbbbbbb")
    assert new.get("phase", "m0") is None, (
        "a member solved under a different model must be re-solved, not reused"
    )


def test_the_old_checkpoints_are_kept_not_deleted(tmp_path):
    """Discarding hours of compute to protect against a mistake the user may not
    have made is the wrong trade; the old set just stops being found."""
    old = solve._SolveCache(tmp_path, "aaaaaaaaaaaa")
    old.put("phase", "m0", {"objective_value": 222.12})
    solve._SolveCache(tmp_path, "bbbbbbbbbbbb")

    assert solve._SolveCache(tmp_path, "aaaaaaaaaaaa").get("phase", "m0") == {
        "objective_value": 222.12
    }


def test_resuming_the_same_model_still_works(tmp_path):
    """The guard must not break the feature it is guarding."""
    first = solve._SolveCache(tmp_path, "aaaaaaaaaaaa")
    first.put("phase", "m0", {"objective_value": 150.53})
    assert solve._SolveCache(tmp_path, "aaaaaaaaaaaa").get("phase", "m0") == {
        "objective_value": 150.53
    }


def test_pre_guard_checkpoints_sitting_loose_are_not_read(tmp_path):
    """Entries written before 2026-08-04 live directly in the parent directory.
    They carry no fingerprint, so they cannot be shown to match — and the
    directory they are in is `runs/_checkpoints/<mission>`, which the GUI reuses
    by default for every run of that mission."""
    (tmp_path / "phase__m0.json").write_text('{"objective_value": 119.9}', encoding="utf-8")
    cache = solve._SolveCache(tmp_path, "aaaaaaaaaaaa")
    assert cache.get("phase", "m0") is None


def test_the_supersession_is_logged(tmp_path, caplog):
    """Otherwise the only symptom of a model change is that a resume re-solves
    everything, which reads as a bug in the resume."""
    solve._SolveCache(tmp_path, "aaaaaaaaaaaa").put("phase", "m0", {"objective_value": 1.0})
    with caplog.at_level("INFO"):
        solve._SolveCache(tmp_path, "bbbbbbbbbbbb")
    assert "aaaaaaaaaaaa" in caplog.text and "will not be resumed" in caplog.text
