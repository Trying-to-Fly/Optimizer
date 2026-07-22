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
    return {
        "name": airplane.name,
        "span_m": float(wing.span()),
        "area_m2": float(wing.area()),
        "aspect_ratio": float(wing.aspect_ratio()),
        "mean_chord_m": float(wing.area() / wing.span()),
        "n_wings": len(airplane.wings),
    }
