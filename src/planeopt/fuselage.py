"""Parametric fuselage loft — MODEL_DETAILS section 7.

The loft IS the geometry model: superellipse cross-sections placed along the
station line, built as an asb.Fuselage. Symbolic-safe (floats or Opti
variables) — the NLP optimizes the loft's driving parameters and reads the
loft's own integrals (area_wetted, volume). All station fractions and radius
multipliers are plain floats; only lengths/widths/heights may be symbolic.

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

import aerosandbox as asb
import aerosandbox.numpy as np

from . import geometry


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
