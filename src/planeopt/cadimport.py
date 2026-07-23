"""STEP import — CAD round-trip step (c) (MODEL_DETAILS 7.5).

The user designs the fuselage in CAD around the design brief; this module
brings the .STEP back in. Exact B-rep integrals (wetted area, volume) come
from the CAD kernel; a tessellation-based station scan feeds the rule-based
shape review (planeopt.shapereview).

Optional dependency: the CAD kernel (cadquery / OpenCascade) ships as the
`cad` extra — `uv sync --extra cad`. Everything here is general-purpose:
no aircraft- or mission-specific knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImportedShape:
    """Declared-data view of an imported fuselage solid (meters, m2, m3).

    sections: [(x_center, width, height)] nose -> tail, from the tessellation
    scan — coarse by construction (vertex extents per station slab), intended
    for the shape review, not for exact geometry."""

    path: str
    swet_m2: float
    volume_m3: float
    x_min: float
    x_max: float
    width_m: float
    height_m: float
    sections: list

    @property
    def length_m(self) -> float:
        return self.x_max - self.x_min

    def body_dict(self, name="fuselage", munk_factor=0.9, interference=1.08) -> dict:
        """Parasite-body entry (aero.body_cd0 / Munk contract) — same fineness
        form-factor model as the parametric loft (fuselage.body_dict)."""
        d_eq = (self.width_m * self.height_m) ** 0.5
        f = self.length_m / d_eq
        return {
            "name": name,
            "wetted_area_m2": self.swet_m2,
            "length_m": self.length_m,
            "form_factor": interference * (1 + 60 / f**3 + f / 400),
            "volume_m3": self.volume_m3,
            "munk_factor": munk_factor,
        }


def load_step(path, n_sections: int = 32, tess_tol: float = 5e-4) -> ImportedShape:
    """Read a .STEP file into an ImportedShape. Raises a clear error when the
    optional CAD kernel is missing."""
    try:
        import cadquery as cq  # noqa: F401 — optional `cad` extra
    except ImportError as e:
        raise RuntimeError(
            "STEP import needs the optional CAD kernel — install with "
            "`uv sync --extra cad` (adds cadquery/OpenCascade)."
        ) from e
    import numpy as np

    solids = cq.importers.importStep(str(path)).solids().vals()
    if not solids:
        raise ValueError(f"no solids found in {path}")
    swet = float(sum(s.Area() for s in solids))
    vol = float(sum(s.Volume() for s in solids))

    verts, tri_a, tri_b = [], [], []
    for s in solids:
        vv, tris = s.tessellate(tess_tol)
        v = np.array([(p.x, p.y, p.z) for p in vv])
        verts.append(v)
        t = np.asarray(tris, dtype=int)
        # triangle edges as endpoint pairs — a slab's y/z extents over a
        # triangulated surface are attained on triangle edges, so sampling
        # edge/boundary crossings makes the scan exact for the tessellation
        # (vertex binning alone fails on extrusions: no interior vertices)
        tri_a.append(v[np.concatenate([t[:, 0], t[:, 1], t[:, 2]])])
        tri_b.append(v[np.concatenate([t[:, 1], t[:, 2], t[:, 0]])])
    pts = np.vstack(verts)
    x0, x1 = float(pts[:, 0].min()), float(pts[:, 0].max())
    edges = np.linspace(x0, x1, n_sections + 1)

    a, b = np.vstack(tri_a), np.vstack(tri_b)
    ax, bx = a[:, 0], b[:, 0]
    crossings = [pts]
    for e in edges[1:-1]:
        m = (np.minimum(ax, bx) < e) & (np.maximum(ax, bx) > e)
        if not m.any():
            continue
        t_frac = (e - ax[m]) / (bx[m] - ax[m])
        crossings.append(a[m] + t_frac[:, None] * (b[m] - a[m]))
    pts = np.vstack(crossings)
    sections = []
    for i in range(n_sections):
        m = (pts[:, 0] >= edges[i]) & (pts[:, 0] <= edges[i + 1])
        if int(m.sum()) < 3:
            continue
        w = float(pts[m, 1].max() - pts[m, 1].min())
        h = float(pts[m, 2].max() - pts[m, 2].min())
        sections.append((float((edges[i] + edges[i + 1]) / 2), w, h))
    width = max(w for _, w, _ in sections)
    height = max(h for _, _, h in sections)
    return ImportedShape(str(path), swet, vol, x0, x1, width, height, sections)
