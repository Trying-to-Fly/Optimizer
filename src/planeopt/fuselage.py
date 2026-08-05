"""Parametric fuselage loft — MODEL_DETAILS section 7.

The loft IS the geometry model: superellipse cross-sections placed along the
station line, built as an asb.Fuselage. Symbolic-safe (floats or Opti
variables) — the NLP optimizes the loft's driving parameters and reads the
loft's own integrals (area_wetted, volume). Station fractions are plain floats;
lengths, widths, heights AND the end-cap fraction `r_cap` may be symbolic (the
cap is a boom socket of fixed diameter, so as a FRACTION it moves with d_eq).

Profile family (streamlined by construction — the optimizer sizes it, the
family guarantees it looks like a fuselage):
- nose: elliptical-arc radius growth, tangent where it meets the bay, section
  shape blending from circular at the tip to the bay's rounded rectangle;
- bay: constant superellipse (shape 4 ~ rounded rect);
- tail: cubic-Hermite boat-tail (tangent at the bay shoulder AND at the end
  cap — no straight cone), shape blending back to circular at the cap.

Aero enters through the existing flat-plate buildup (bodies dict) + Munk term,
NOT through LiftingLine: asb's LL adds its own fuselage model when one is
attached, which would double-count drag against the validated M1 buildup. The
aero Airplane therefore stays wings-only; the fuselage attaches to a viz twin
for the 3D artifacts (solve.run).
"""

from __future__ import annotations

import math

import aerosandbox as asb
import aerosandbox.numpy as np

from . import geometry

# --- afterbody physics (MODEL_DETAILS section 7.3) -------------------------
# Family constants, not aircraft choices, so they live here rather than on any
# one aircraft. All three are DECLARED, UNCALIBRATED data in the same idiom as
# MOUNT_EFFECTS and the 1.08 excrescence factor: adjustable data, not code.

#: Separation onset for an axisymmetric afterbody, half-angle in degrees. The
#: conservative end of the 12-15 deg band the literature puts it in (user
#: decision, 2026-08-05) — conservative meaning it charges SOONER, which is the
#: safe direction for a term whose whole purpose is to stop the optimizer
#: shortening a boat-tail for free.
THETA_SEP_DEG = 12.0

#: Base-pressure drag coefficient on the separated (effective) base. Matched to
#: AeroSandbox 4.2.10's `fuselage_base_drag_coefficient` at M -> 0, which is
#: MIL-HDBK-762 Fig 5-140 blunt-base data, so that the planned AeroBuildup
#: cross-check compares like with like rather than against a private number.
#:
#: Applying a BLUNT-base coefficient to a separated-boattail effective base is
#: standard Hoerner-style bookkeeping, not a calibration — nothing in this
#: project has ever measured it, and the label matters more than the digits.
CD_BASE = 0.159

#: Width of the onset ramp, expressed as degrees of angle EXCESS over
#: THETA_SEP_DEG (the ramp itself is in tangent, below). Separation near onset
#: is weak and intermittent, so a term that switched on at full strength would
#: be claiming a confidence the physics does not have — and would hand IPOPT a
#: step discontinuity in a constraint-adjacent quantity, which is worse.
RAMP_EXCESS_DEG = 3.0

#: The ramp scale in TANGENT (what the model actually compares), so the "3
#: degrees of excess" meaning survives an edit to THETA_SEP_DEG instead of
#: silently becoming "3 degrees at 12 deg, 2.4 at 15". ~0.0554 as declared.
SEPARATION_RAMP = math.tan(math.radians(THETA_SEP_DEG + RAMP_EXCESS_DEG)) - math.tan(
    math.radians(THETA_SEP_DEG)
)


def loft(
    nose_len,
    bay_len,
    tail_len,
    width,
    height,
    x_nose=0.0,
    z_c=0.0,
    shape=4.0,
    n_nose=7,
    n_tail=7,
    r_cap=0.12,
    name="pod",
) -> asb.Fuselage:
    """Streamlined pod loft. r_cap is the end-cap radius fraction (boom socket
    diameter in pod-boom topology, tail-block joint in integrated)."""
    xsecs = []
    for i in range(n_nose + 1):
        t = i / n_nose
        r = 1e-3 + (1 - (1 - t) ** 2) ** 0.5  # elliptical arc: 0 at tip, tangent at bay
        s = 2.0 + (shape - 2.0) * t  # circular tip -> rounded-rect bay
        xsecs.append(
            asb.FuselageXSec(
                xyz_c=[x_nose + nose_len * t, 0, z_c],
                width=width * r,
                height=height * r,
                shape=s,
            )
        )
    x_bay_end = x_nose + nose_len + bay_len
    xsecs.append(
        asb.FuselageXSec(xyz_c=[x_bay_end, 0, z_c], width=width, height=height, shape=shape)
    )
    for i in range(1, n_tail + 1):
        u = i / n_tail
        r = 1 - (1 - r_cap) * (3 * u**2 - 2 * u**3)  # Hermite: tangent both ends
        s = shape + (2.0 - shape) * u  # rounded-rect bay -> circular cap
        xsecs.append(
            asb.FuselageXSec(
                xyz_c=[x_bay_end + tail_len * u, 0, z_c],
                width=width * r,
                height=height * r,
                shape=s,
            )
        )
    return asb.Fuselage(name=name, xsecs=xsecs)


def boom_loft(x_start, length, od=0.012, z_c=0.0, name="boom") -> asb.Fuselage:
    """The exposed CF boom as a drawable body: a plain constant-section tube.

    Viz only. The boom's DRAG comes from `boom_body`, and its mass from the
    aircraft's own structure model — this exists because a three-view and an
    interactive model that show a pod and a tail floating apart, with nothing
    between them, misrepresent the aircraft to the person reading them.

    Two end caps plus one mid station: a tube needs no more, and every station
    is an asb.FuselageXSec that something downstream has to walk.
    """
    return asb.Fuselage(
        name=name,
        xsecs=[
            asb.FuselageXSec(
                xyz_c=[x_start + length * t, 0, z_c],
                width=od, height=od, shape=2.0,  # circular
            )
            for t in (0.0, 0.5, 1.0)
        ],
    )


def body_dict(fuse: asb.Fuselage, length, width, height, munk_factor=0.9, interference=1.08) -> dict:
    """Parasite-body entry (aero.body_cd0 / Munk contract) from a loft.

    Form factor from fineness (Hoerner): FF = 1 + 60/f^3 + f/400, f = L/d_eq,
    times an interference/canopy factor chosen so the spec pod reproduces its
    frozen M1 value (1.16 x 1.08 ~ 1.25) — slenderness becomes a real trade
    while the validated baseline is preserved."""
    d_eq = (width * height) ** 0.5
    f = length / d_eq
    return {
        "name": fuse.name,
        "wetted_area_m2": fuse.area_wetted(),
        "length_m": length,
        "form_factor": interference * (1 + 60 / f**3 + f / 400),
        "volume_m3": fuse.volume(),
        "munk_factor": munk_factor,
        # reported, never consumed by the buildup: the FF above is a function of
        # fineness ALONE, so a run that ends up slender should say so in its own
        # artifact rather than leave it to be recomputed from the design vector
        "fineness": f,
    }


def afterbody_terms(
    d_eq,
    tail_len,
    r_cap,
    cd_base: float = CD_BASE,
    theta_sep_deg: float = THETA_SEP_DEG,
    ramp: float = SEPARATION_RAMP,
) -> dict:
    """Boat-tail separation as an EFFECTIVE BASE, in the parasite-body contract.

    Until 2026-08-05 the drag buildup could not see afterbody shape at all: the
    complete channel from fuselage geometry to the objective was wetted area,
    length, fineness and volume, so a well-faired body and a badly separated one
    that agreed on those four scored identically. The 2026-08-05 champion ran a
    20.1 deg closure half-angle through the middle of its boat-tail — roughly
    half again the separation threshold — and was charged nothing for it, which
    is why `pod_tail` sat exactly on the geometric floor that stood in for this
    physics (HANDOFF, FUSELAGE DRAG FIDELITY).

    ONE MECHANISM, not two. Rather than a boat-tail penalty plus a separate base
    term, the station where the local closure angle first exceeds the separation
    threshold defines an enlarged EFFECTIVE BASE, and unrecovered base pressure
    is charged on that area. Attached afterbodies charge nothing; a steep one
    charges most of its own cross-section, which is what a separated afterbody
    physically is.

    Closed form for the Hermite family, so this needs no geometry query, no new
    design variable and no quadrature. With `r(u) = 1 - (1-r_cap)(3u^2 - 2u^3)`,
    `R(u) = (d_eq/2) r(u)` and `x = tail_len * u`:

        tan theta(u) = (d_eq/2)(1 - r_cap) * 6u(1-u) / tail_len
        tan theta_max = 1.5 (d_eq/2)(1 - r_cap) / tail_len          (at u = 1/2)
        4 u (1-u) = rho == tan theta_sep / tan theta_max
        u* = (1 - sqrt(1 - rho)) / 2            first crossing, rising side
        A_charged = (pi/4) d_eq^2 (r(u*)^2 - r_cap^2)

    The end cap is subtracted because it is occluded in both topologies by
    construction — in pod-boom it IS the boom socket, in integrated it is the
    tail-block joint — so base drag can only ever arrive through separation.

    THE ONSET RAMP is the non-obvious part. At the moment of onset u* -> 1/2,
    where r ~ (1 + r_cap)/2 ~ 0.6, NOT r_cap: the raw charged area would jump
    from zero to most of the cross-section the instant theta_max crossed
    theta_sep. Physically separation near onset is weak and intermittent;
    numerically a step in a quantity the objective reads is exactly what an
    interior-point method cannot walk across. So the charge is ramped in the
    tangent excess, `lambda = h^2/(h^2 + ramp^2)`: zero below onset, ~0.83 at a
    2026-08-05-champion-like 18.5 deg, and -> 1 for a bluff afterbody.

    All quantities use the d_eq-EQUIVALENT AXISYMMETRIC convention. The real
    section is 68x88, so the vertical-plane closure is ~14% steeper in tangent
    than this reports; the correlations being borrowed are axisymmetric, so d_eq
    is the consistent choice and the understatement is stated rather than
    corrected. Revisit if the width:height ratio is ever unlocked.

    SYMBOLIC SAFETY. Every guard here exists because an interior-point method
    evaluates the model at iterates outside the feasible box (the lesson of the
    boom NaN, HANDOFF issue 3): `tail_len` is a difference of design variables
    and enters a denominator, and `1 - rho` goes negative for every afterbody
    shallower than the threshold. Both go through `geometry.smooth_floor`, never
    a bare `max`. The u* that results below onset is meaningless — the guard
    exists so the sqrt is FINITE, not so u* is right — and it is harmless
    because lambda is zero there and multiplies it away.

    Returns the additive drag AREA (D/q, m^2 — constant with V at our Re and
    Mach) that `aero.body_cd0` adds, plus an `afterbody` block for the artifact.
    Declared, uncalibrated: see CD_BASE.
    """
    tail = geometry.smooth_floor(tail_len)
    # How much radius the boat-tail actually closes. Floored because it divides
    # into `rho` below: at r_cap = 1 exactly — a cap as wide as the body, i.e.
    # no boat-tail at all — the closure is zero, `rho` is infinite, and
    # `smooth_floor(1 - inf)` is `0.5*(-inf + inf)` = NaN. Unreachable through
    # today's bounds (r_cap is 0.14-0.24 across the pod_xs box) and one edit
    # away from reachable: HANDOFF lists freeing `r_cap` as a design variable
    # among the cheap widenings once the physics can see shape.
    closure = geometry.smooth_floor(1 - r_cap)
    tan_sep = math.tan(math.radians(theta_sep_deg))
    tan_max = 1.5 * (d_eq / 2) * closure / tail

    rho = tan_sep / tan_max
    # Floored to a small POSITIVE number, not to zero. `1 - rho` is negative for
    # every afterbody shallower than the threshold, and floored to exactly zero
    # the sqrt above it has an infinite slope — which is how a guard against
    # NaN values becomes a source of NaN gradients. (Worse: for `1 - rho` below
    # about -7e4 the hinge cancels to a hard zero in double precision, so this
    # is not merely a measure-zero coincidence.) The resulting u* is meaningless
    # there, which costs nothing: lambda is zero below onset and multiplies it
    # away.
    u_star = (1 - np.sqrt(geometry.smooth_floor(1 - rho, floor=1e-9))) / 2
    r_sep = 1 - closure * (3 * u_star**2 - 2 * u_star**3)
    area_charged = (math.pi / 4) * d_eq**2 * (r_sep**2 - r_cap**2)

    excess = geometry.smooth_floor(tan_max - tan_sep)
    lam = excess**2 / (excess**2 + ramp**2)
    base_drag_area = cd_base * lam * area_charged
    return {
        "base_drag_area_m2": base_drag_area,
        "afterbody": {
            "theta_max_deg": np.arctan(tan_max) * 180 / math.pi,
            "theta_sep_deg": theta_sep_deg,
            "u_star": u_star,
            "r_sep": r_sep,
            "r_cap": r_cap,
            "lambda": lam,
            "area_charged_m2": area_charged,
            "base_drag_area_m2": base_drag_area,
        },
    }


def boom_body(exposed_len, od=0.012) -> dict:
    """Parasite-body entry for the exposed CF boom, symbolic-safe in its
    length (the boom now spans pod tail -> tail block, so its length is an
    optimization outcome, not a constant).

    That length is a DIFFERENCE of design variables, held positive only by the
    aircraft's boom-clearance constraint, so intermediate iterates can and do
    drive it negative. The whole body dict is therefore built on a smoothly
    floored length: length, wetted area and volume stay non-negative together,
    the drag build-up stays finite, and the point is rejected by the constraint
    that owns it instead of by a NaN (geometry.smooth_floor)."""
    length = geometry.smooth_floor(exposed_len)
    return {
        "name": "boom",
        "wetted_area_m2": np.pi * od * length,
        "length_m": length,
        "form_factor": 1.10,
        "volume_m3": np.pi * (od / 2) ** 2 * length,
        "munk_factor": 0.95,
    }
