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
    opti.subject_to(stress <= SIGMA_ALLOW / SAFETY_FACTOR)
    tip_defl = moment_nm * length**2 / (3 * E_CF * sec["I"])
    opti.subject_to(tip_defl <= defl_frac * length)
    opti.subject_to(wall <= od / 2 * 0.45)  # stay a tube, not a rod


def semispan_root_moment(weight_n, n_limit, semispan):
    """Root bending moment of one wing half at limit load, elliptical lift."""
    return n_limit * (weight_n / 2) * 0.424 * semispan
