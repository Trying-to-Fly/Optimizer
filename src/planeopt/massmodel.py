"""Mass & CG model — MODEL_DETAILS.md section 1.

Contract: (design vector, aircraft config) -> list[PointMass] -> AUW, CG.
M0 status: fixed-equipment passthrough only. Printed-surface terms (section 1.2),
spar mass (section 1.3), and per-surface CG (section 1.6) arrive at M1/M2;
constants come from tools/fit_profile.py against slicer data (section 1.4).
"""

from __future__ import annotations

from .types import PointMass


def totals(components: list[PointMass]) -> dict:
    """AUW and CG from a component list. Symbolic-safe (sums and one division)."""
    total = sum(c.mass_kg for c in components)
    x_cg = sum(c.mass_kg * c.x_m for c in components) / total
    return {"auw_kg": total, "x_cg_m": x_cg}
