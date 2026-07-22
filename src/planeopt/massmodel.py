"""Mass & CG model — MODEL_DETAILS.md section 1.

Contract: (design/geometry, aircraft config) -> list[PointMass] -> AUW, CG.

M1 implementation: printed-surface decomposition (section 1.2) computed from the
built geometry per-surface with that surface's ConstructionProfile; fixed equipment
and non-surface structure (spars/boom/pod/ballast at M1) from the aircraft config.
Surface CG at ~45% mean chord (AC + 20% c-bar) — station-level fidelity per
section 1.6. Constants are UNCALIBRATED until tools/fit_profile.py runs on slicer
data (section 1.4).
"""

from __future__ import annotations

from .types import ConstructionProfile, PointMass

WETTED_FACTOR = 2.05  # S_wet / S_plan for ~9% t/c sections


def printed_surface(wing, profile: ConstructionProfile) -> tuple[PointMass, dict]:
    """Mass of one printed lifting surface + its term breakdown."""
    S = wing.area()
    b = wing.span()
    c_mean = S / b

    skin = profile.k_skin_kg_m2 * WETTED_FACTOR * S
    ribs = profile.k_rib_kg_m2 * b * c_mean**2 / profile.rib_pitch_m
    joints = profile.k_joint_kg * b / profile.section_length_m  # continuous, not ceil'd
    mass = profile.finish_factor * (skin + ribs + joints + profile.overhead_kg)

    # ~45% mean chord behind the root LE (arithmetic, symbolic-safe — the AC
    # helper is numeric-only); fine at station-level fidelity for unswept LEs
    x_cg = wing.xsecs[0].xyz_le[0] + 0.45 * c_mean
    breakdown = {
        "skin_kg": skin,
        "ribs_kg": ribs,
        "joints_kg": joints,
        "overhead_kg": profile.overhead_kg,
        "finish_factor": profile.finish_factor,
        "profile": profile.name,
        "calibrated": profile.calibrated,
    }
    return PointMass(f"printed_{wing.name}", mass, x_cg), breakdown


def build(
    aircraft, airplane, dv=None, printed_scale: float = 1.0
) -> tuple[list[PointMass], dict]:
    """Full component list + printed-term breakdowns for the report.

    printed_scale multiplies printed-surface masses only — the knob for the
    +/-10% structure-mass re-solves (MODEL_DETAILS 1.5)."""
    components = list(aircraft.fixed_equipment(dv))
    components += aircraft.structure_extras(dv)

    breakdowns = {}
    profiles = aircraft.construction()
    for wing in airplane.wings:
        if wing.name in profiles:
            pm, bd = printed_surface(wing, profiles[wing.name])
            pm.mass_kg = pm.mass_kg * printed_scale
            components.append(pm)
            breakdowns[wing.name] = bd
    return components, breakdowns


def totals(components: list[PointMass]) -> dict:
    """AUW and CG from a component list. Symbolic-safe (sums and one division)."""
    total = sum(c.mass_kg for c in components)
    x_cg = sum(c.mass_kg * c.x_m for c in components) / total
    return {"auw_kg": total, "x_cg_m": x_cg}
