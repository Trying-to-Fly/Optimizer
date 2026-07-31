"""The root-chord cap is a PRINT BED limit, and it is always active.

`c_root` sits exactly on its bound in every solve that has ever converged, so
the number is doing real work on the design and has to be declared, overridable
and enforced — not a literal buried in `design_variables` (2026-07-31).

The cap was raised 245 -> 275 mm the same day (user decision). It is worth five
seconds at the champion; what it is actually worth is that three studies which
had failed every run since M4.8 converge at 275 mm, all of them on the
static-margin floor — SM is normalised by MAC, so a wing denied chord reports
its shortfall as a STABILITY failure (FINDINGS section 15).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from planeopt.cli import load_aircraft

BED_MM = 256.0          # Bambu A1, square
TC = 0.092              # SD7037 max thickness / chord, DESIGN_SPEC section 9


@pytest.fixture(scope="module")
def sample():
    return load_aircraft(Path("aircraft/vtail_sample"))[0]


def test_the_cap_is_declared(sample):
    """A bound the optimizer is always pinned against must be easy to find."""
    assert sample.c_root_max_m == pytest.approx(0.275)


def test_the_cap_actually_reaches_the_SOLVER(sample):
    """Declaring the attribute is worthless if `design_variables` still reads a
    literal. Checked by overriding it on a second instance — nothing but the
    attribute changes, so exactly one bound row may move, and it must move by
    the ratio.

    AeroSandbox scales every bound (`var/scale <= bound/scale`), so the raw
    metres never appear in `ubg`; the ratio survives the scaling because both
    aircraft share every scale.
    """
    import aerosandbox as asb
    import casadi as cas
    import numpy as np

    variant = type(sample)()
    variant.c_root_max_m = 0.245

    def upper_bounds(ac):
        opti = asb.Opti()
        ac.design_variables(opti)
        return np.array(cas.Function("f", [], [opti.ubg])()["o0"]).ravel()

    a, b = upper_bounds(sample), upper_bounds(variant)
    assert a.shape == b.shape, "the override changed the SHAPE of the problem"
    differ = np.flatnonzero(~np.isclose(a, b, equal_nan=True))
    assert len(differ) == 1, f"expected exactly one bound to move, got {len(differ)}"
    assert b[differ[0]] / a[differ[0]] == pytest.approx(0.245 / 0.275)


@pytest.mark.parametrize("chord_mm, fits", [(245, True), (275, True), (340, False)])
def test_the_cap_is_consistent_with_the_45_degree_bed_diagonal(chord_mm, fits):
    """The panel prints standing up, so the bed footprint is chord x thickness
    and a 45-degree layout needs (c + t)/sqrt(2) per axis. This is the arithmetic
    that makes 275 mm buildable on a 256 mm bed at all — axis-aligned it is not."""
    box = (chord_mm * (1 + TC)) / math.sqrt(2)
    assert (box <= BED_MM) is fits
    # and axis-aligned, 275 would NOT fit — the rotation is load-bearing
    if chord_mm == 275:
        assert chord_mm > BED_MM


def test_the_declared_cap_is_inside_the_geometric_ceiling(sample):
    """~332 mm is where the 45-degree layout runs out of bed. A cap above it
    would be a number no printer in this project can honour."""
    ceiling_m = (BED_MM * math.sqrt(2) / (1 + TC)) / 1000
    assert sample.c_root_max_m < ceiling_m
    assert ceiling_m == pytest.approx(0.3315, abs=5e-4)
