"""Geometry helpers shared by aircraft architecture mappings.

The mapping itself (design vector -> asb.Airplane) lives in each aircraft's config
module — the framework never assumes an architecture (OPTIMIZATION_CONCEPT.md scope).
This module holds reusable, symbolic-safe helpers only.
"""

from __future__ import annotations

import aerosandbox as asb


def summarize(airplane: asb.Airplane) -> dict:
    """Geometry summary block for reports (floats only — call on numeric geometry)."""
    wing = airplane.wings[0]
    out = {
        "name": airplane.name,
        "span_m": float(wing.span()),
        "span_projected_m": float(airplane.b_ref),  # front-view y-span (the capped one)
        "area_m2": float(wing.area()),
        "aspect_ratio": float(wing.aspect_ratio()),
        "mean_chord_m": float(wing.area() / wing.span()),
        "n_wings": len(airplane.wings),
    }
    wl = next((w for w in airplane.wings if w.name == "winglet"), None)
    if wl is not None:
        r0, r1 = wl.xsecs[0], wl.xsecs[-1]
        dy = float(r1.xyz_le[1] - r0.xyz_le[1])
        dz = float(r1.xyz_le[2] - r0.xyz_le[2])
        out["winglet"] = {
            "length_m": float((dy**2 + dz**2) ** 0.5),
            "cant_deg": float(__import__("math").degrees(__import__("math").atan2(dz, dy))),
            "root_chord_m": float(r0.chord),
            "tip_chord_m": float(r1.chord),
            "toe_deg": float(r0.twist),
        }
        out["span_projected_m"] += 2 * dy  # cap applies winglet-inclusive
    return out
