"""Buildable geometry out of a run: the loft definition and the 3D curves.

The report answers "is this design any good"; these files answer "how do I cut
it". Two levels, because CAD wants one and a cutter wants the other:

- `stations.csv` — the LOFT DEFINITION, one row per section: leading-edge point
  in xyz, chord, twist, and the airfoil name. This is what you type into a CAD
  loft, and it is the smallest complete description of the wing.
- `sections_3d.csv` — the CURVES themselves: every section's airfoil outline
  already scaled, twisted and placed in aircraft coordinates, ready to import
  as polylines and loft or rib-cut directly.

Both come from `asb.Wing`'s own placement functions rather than from a
re-derivation here, so what you build is exactly what was analysed — a
separate transform would be free to drift from the one the solver saw.

Architecture-agnostic: this reads whatever surfaces the aircraft built, so it
works for any wing, tail type or added surface without knowing their names.

Coordinates are metres in the aircraft frame: +x aft from the nose datum,
+y starboard, +z up. Surfaces marked `symmetric` store only the starboard half
— mirror about y = 0 for the port side.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

#: Chordwise resolution of the exported outlines. The airfoil's own coordinate
#: set is used as-is when it is at least this dense, which it normally is
#: (~160-200 points) — resampling a coordinate file usually loses the leading
#: edge rather than improving it.
MIN_CHORDWISE_POINTS = 60


def _airfoil_name(xsec) -> str:
    return getattr(getattr(xsec, "airfoil", None), "name", None) or "unknown"


def stations(airplane) -> list[dict]:
    """Loft definition: one row per section, root to tip, for every surface."""
    rows = []
    for wing in airplane.wings:
        for i, xsec in enumerate(wing.xsecs):
            le = np.array(wing._compute_xyz_le_of_WingXSec(i), dtype=float).flatten()
            te = np.array(wing._compute_xyz_te_of_WingXSec(i), dtype=float).flatten()
            rows.append({
                "surface": wing.name,
                "station": i,
                "airfoil": _airfoil_name(xsec),
                "chord_m": round(float(xsec.chord), 6),
                "twist_deg": round(float(xsec.twist), 4),
                "x_le_m": round(float(le[0]), 6),
                "y_le_m": round(float(le[1]), 6),
                "z_le_m": round(float(le[2]), 6),
                "x_te_m": round(float(te[0]), 6),
                "y_te_m": round(float(te[1]), 6),
                "z_te_m": round(float(te[2]), 6),
                "symmetric": bool(getattr(wing, "symmetric", False)),
            })
    return rows


def section_points(airplane) -> list[dict]:
    """Every section outline as placed 3D points (surface, station, index, xyz).

    Points run in the airfoil file's own order — trailing edge, over the top,
    around the leading edge, back along the bottom — so consecutive rows form a
    closed polyline per (surface, station).
    """
    rows = []
    for wing in airplane.wings:
        for i, xsec in enumerate(wing.xsecs):
            coords = np.array(xsec.airfoil.coordinates, dtype=float)
            for j, (x_nondim, z_nondim) in enumerate(coords):
                xyz = np.array(
                    wing._compute_xyz_of_WingXSec(i, float(x_nondim), float(z_nondim)),
                    dtype=float,
                ).flatten()
                rows.append({
                    "surface": wing.name,
                    "station": i,
                    "airfoil": _airfoil_name(xsec),
                    "point": j,
                    "x_m": round(float(xyz[0]), 6),
                    "y_m": round(float(xyz[1]), 6),
                    "z_m": round(float(xyz[2]), 6),
                })
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


README = """\
Buildable geometry for this run.

Units are metres, aircraft frame: +x aft from the nose datum, +y starboard,
+z up. Surfaces with symmetric = True store only the STARBOARD half; mirror
about y = 0 for the port side.

stations.csv
    The loft definition — one row per section. Leading- and trailing-edge
    points, chord, twist and the airfoil each section uses. Enough on its own
    to rebuild the surface in CAD: place the LE points, set each chord and
    twist, apply the named airfoil, loft between stations in order.

sections_3d.csv
    The curves themselves. Each section's airfoil outline already scaled,
    twisted and positioned, as an ordered point list. Import per
    (surface, station) as a closed polyline and loft, or cut ribs directly.
    Point order follows the airfoil file: trailing edge, over the top, around
    the leading edge, back along the bottom.

Both are generated from the same geometry the solver analysed, so what you
build is what was evaluated.
"""


def write(airplane, run_dir: Path) -> Path:
    """Write the geometry export into `run_dir/geometry/`; return that folder."""
    out = Path(run_dir) / "geometry"
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "stations.csv", stations(airplane))
    _write_csv(out / "sections_3d.csv", section_points(airplane))
    (out / "README.txt").write_text(README, encoding="utf-8")
    return out
