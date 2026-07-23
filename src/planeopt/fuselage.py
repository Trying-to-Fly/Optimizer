"""Parametric fuselage loft — MODEL_DETAILS section 7.

The loft IS the geometry model: superellipse cross-sections placed along the
station line, built as an asb.Fuselage. Symbolic-safe (floats or Opti
variables) — the NLP optimizes the loft's driving parameters and reads the
loft's own integrals (area_wetted, volume).

Aero enters through the existing flat-plate buildup (bodies dict) + Munk term,
NOT through LiftingLine: asb's LL adds its own fuselage model when one is
attached, which would double-count drag against the validated M1 buildup. The
aero Airplane therefore stays wings-only; the fuselage attaches to a viz twin
for the 3D artifacts (solve.run).
"""

from __future__ import annotations

import aerosandbox as asb
import aerosandbox.numpy as np


def loft(
    nose_len,
    bay_len,
    tail_len,
    width,
    height,
    x_nose=0.0,
    z_c=0.0,
    shape=4.0,
    n_nose=3,
    name="pod",
) -> asb.Fuselage:
    """Pod loft: circular-arc nose growth (n_nose intermediate sections),
    constant superellipse bay (shape 4 ~ rounded rect), conical tail fairing."""
    xsecs = []
    for i in range(n_nose + 1):
        t = i / n_nose
        r = 1e-3 + (1 - (1 - t) ** 2) ** 0.5  # 0 at the tip, 1 at the bay
        xsecs.append(
            asb.FuselageXSec(
                xyz_c=[x_nose + nose_len * t, 0, z_c],
                width=width * r,
                height=height * r,
                shape=shape,
            )
        )
    x_bay_end = x_nose + nose_len + bay_len
    xsecs.append(
        asb.FuselageXSec(xyz_c=[x_bay_end, 0, z_c], width=width, height=height, shape=shape)
    )
    xsecs.append(
        asb.FuselageXSec(
            xyz_c=[x_bay_end + tail_len, 0, z_c],
            width=width * 0.12,
            height=height * 0.12,
            shape=2.0,
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
