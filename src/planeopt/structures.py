"""Spar beam model — MODEL_DETAILS.md section 1.3.

Round CF tube properties + the two sizing constraints (root bending stress, tip
deflection), all symbolic-safe. Load model (documented approximations, conservative
side): elliptical spanwise lift -> semispan lift centroid at 0.424 x (b/2); no
inertia relief from structure mass; tip deflection from the cantilever formula
with the root moment applied over the segment length.
"""

from __future__ import annotations

import aerosandbox.numpy as np

RHO_CF = 1600.0  # kg/m^3, woven tube
E_CF = 110e9  # Pa, woven (not UD) modulus
SIGMA_ALLOW = 400e6  # Pa, woven tube bending allowable
SAFETY_FACTOR = 2.0


def tube(od, wall):
    """Section properties of a round tube; od/wall may be Opti variables."""
    id_ = od - 2 * wall
    area = np.pi / 4 * (od**2 - id_**2)
    I = np.pi / 64 * (od**4 - id_**4)
    return {"area": area, "I": I, "id": id_}


def tube_mass(od, wall, length):
    return RHO_CF * tube(od, wall)["area"] * length


def spar_constraints(opti, od, wall, length, moment_nm, defl_frac: float = 0.05):
    """Apply stress + stiffness constraints for one spar segment.

    moment_nm: bending moment at the segment root at limit load.
    defl_frac: tip deflection cap as a fraction of segment length.
    """
    sec = tube(od, wall)
    stress = moment_nm * (od / 2) / sec["I"]
    # Written as a RATIO, not `stress <= allowable`. Both forms describe exactly
    # the same feasible set — this one is divided through by a positive constant
    # — but the residual the SOLVER sees changes from pascals (~1e8) to order 1,
    # which is the whole point. This row used to dominate the constraint vector:
    # IPOPT opened the short-span solve at inf_pr = 5.2e7 and spent hundreds of
    # iterations recovering from it (FINDINGS §14.5).
    opti.subject_to(stress / (SIGMA_ALLOW / SAFETY_FACTOR) <= 1.0)
    tip_defl = moment_nm * length**2 / (3 * E_CF * sec["I"])
    # already order 1e-2 on both sides (metres) — left alone deliberately
    opti.subject_to(tip_defl <= defl_frac * length)
    opti.subject_to(wall <= od / 2 * 0.45)  # stay a tube, not a rod


def semispan_root_moment(weight_n, n_limit, semispan):
    """Root bending moment of one wing half at limit load, elliptical lift."""
    return n_limit * (weight_n / 2) * 0.424 * semispan


def spar_report(od, wall, length, moment_nm, defl_frac: float = 0.05) -> dict:
    """As-built numbers for one spar segment: the stock to buy, and how close it
    ended up to each limit.

    Deliberately mirrors `spar_constraints` term for term — a build document that
    re-derived the stress from its own formula would be free to disagree with the
    constraint the optimizer actually enforced. Numeric only (report path).
    """
    sec = tube(float(od), float(wall))
    stress = float(moment_nm) * (float(od) / 2) / sec["I"]
    allow = SIGMA_ALLOW / SAFETY_FACTOR
    defl = float(moment_nm) * float(length) ** 2 / (3 * E_CF * sec["I"])
    defl_allow = defl_frac * float(length)
    return {
        "od_mm": round(float(od) * 1000, 2),
        "wall_mm": round(float(wall) * 1000, 3),
        "bore_mm": round(float(sec["id"]) * 1000, 2),
        "length_mm": round(float(length) * 1000, 1),
        "mass_g": round(float(tube_mass(od, wall, length)) * 1000, 1),
        "root_moment_Nm": round(float(moment_nm), 2),
        "stress_MPa": round(stress / 1e6, 1),
        "stress_allow_MPa": round(allow / 1e6, 1),
        "stress_margin_pct": round((allow / stress - 1) * 100, 1) if stress > 0 else "",
        "tip_defl_mm": round(defl * 1000, 1),
        "defl_allow_mm": round(defl_allow * 1000, 1),
        "defl_margin_pct": round((defl_allow / defl - 1) * 100, 1) if defl > 0 else "",
    }
