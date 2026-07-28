"""Buildable geometry export (report/geometry_export.py).

These files are what someone cuts parts from, so the properties worth pinning
are the ones that would produce a WRONG PART rather than a failed import:
the loft definition must match the analysed airplane, and the 3D curves must
be consistent with the stations they claim to belong to.
"""

import csv

from planeopt.report import geometry_export


def test_stations_cover_every_surface_and_section(sample_aircraft):
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    rows = geometry_export.stations(plane)
    assert len(rows) == sum(len(w.xsecs) for w in plane.wings)
    assert {r["surface"] for r in rows} == {w.name for w in plane.wings}
    for r in rows:
        assert r["airfoil"] != "unknown"  # a rib with no section is unbuildable
        assert r["chord_m"] > 0


def test_stations_match_the_analysed_geometry(sample_aircraft):
    """The export must describe the airplane that was evaluated, not a
    re-derivation of it — a separate transform is free to drift."""
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    wing = plane.wings[0]
    rows = [r for r in geometry_export.stations(plane) if r["surface"] == "wing"]
    assert abs(rows[0]["chord_m"] - float(wing.xsecs[0].chord)) < 1e-9
    assert abs(rows[-1]["chord_m"] - float(wing.xsecs[-1].chord)) < 1e-9
    # tip station's y is the semi-span the projected-span cap is written against
    assert abs(2 * rows[-1]["y_le_m"] - float(plane.b_ref)) < 1e-6


def test_chord_line_length_matches_declared_chord(sample_aircraft):
    """LE->TE distance must equal the chord, or every rib is cut wrong."""
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    for r in geometry_export.stations(plane):
        d = sum((r[f"{a}_te_m"] - r[f"{a}_le_m"]) ** 2 for a in "xyz") ** 0.5
        assert abs(d - r["chord_m"]) < 1e-6, r["surface"]


def test_section_points_are_closed_placed_outlines(sample_aircraft):
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    pts = geometry_export.section_points(plane)
    keys = {(p["surface"], p["station"]) for p in pts}
    assert len(keys) == sum(len(w.xsecs) for w in plane.wings)
    root = [p for p in pts if p["surface"] == "wing" and p["station"] == 0]
    assert len(root) > geometry_export.MIN_CHORDWISE_POINTS
    # outline closes back on itself (same point order as the airfoil file)
    assert abs(root[0]["x_m"] - root[-1]["x_m"]) < 1e-6
    assert abs(root[0]["z_m"] - root[-1]["z_m"]) < 1e-6


def test_section_points_span_their_station_chord(sample_aircraft):
    """Chordwise extent of the placed outline matches that station's chord,
    within airfoil thickness — catches a missing scale or a lost twist."""
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    stations = {(r["surface"], r["station"]): r for r in geometry_export.stations(plane)}
    pts = geometry_export.section_points(plane)
    for (surface, station), st in stations.items():
        xs = [p["x_m"] for p in pts if p["surface"] == surface and p["station"] == station]
        assert max(xs) - min(xs) <= st["chord_m"] + 1e-6
        assert max(xs) - min(xs) > 0.9 * st["chord_m"]


def test_write_produces_importable_csvs(sample_aircraft, tmp_path):
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    out = geometry_export.write(plane, tmp_path)
    assert (out / "README.txt").is_file()
    for name in ("stations.csv", "sections_3d.csv"):
        with (out / name).open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows and all(len(r) == len(rows[0]) for r in rows)


def test_symmetric_flag_is_reported(sample_aircraft):
    """Only the starboard half is stored; without this flag a builder mirrors
    a surface that should not be mirrored, or fails to mirror one that should."""
    plane = sample_aircraft.geometry(sample_aircraft.DV_DEFAULTS)
    rows = geometry_export.stations(plane)
    by_surface = {w.name: bool(w.symmetric) for w in plane.wings}
    for r in rows:
        assert r["symmetric"] == by_surface[r["surface"]]
