"""The bivariate prop model (MODEL_DETAILS.md section 2.1).

CT/CP are fitted against advance ratio AND blade Reynolds. These guard the two
properties the optimizer depends on — that the fit reproduces APC's own numbers
at the operating point, and that it evaluates identically through the numeric
and the CasADi-symbolic path — plus the Reynolds reconstruction that makes the
second variable free rather than an extra unknown.
"""

from __future__ import annotations

import casadi as ca
import numpy as np
import pytest

from planeopt import propulsion

# Cruise-ish operating points for an 11 in prop on a ~1.8 kg airframe.
POINTS = [(0.30, 80.0), (0.4730, 62.4), (0.6081, 55.92), (0.72, 45.0)]


def test_reynolds_follows_the_operating_point():
    """Re = re_coeff * n * sqrt((0.75pi)^2 + J^2) — the reason no RPM window is needed."""
    t = propulsion.PropTable("apc_11x7e")
    re_a = float(t.reynolds(0.5, 50.0))
    # Reynolds scales with rev/s at fixed advance ratio...
    assert float(t.reynolds(0.5, 100.0)) == pytest.approx(2 * re_a, rel=1e-9)
    # ...and rises with forward speed at fixed rev/s
    assert float(t.reynolds(0.9, 50.0)) > re_a
    assert re_a == pytest.approx(
        t.re_coeff * 50.0 * np.sqrt((0.75 * np.pi) ** 2 + 0.25), rel=1e-9
    )


def test_coefficients_actually_depend_on_reynolds():
    """A fit that ignored Reynolds would make this a no-op — and did, until 2026-07-28."""
    t = propulsion.PropTable("apc_11x7e")
    lo, hi = float(t.ct(0.55, 30.0)), float(t.ct(0.55, 90.0))
    assert lo != pytest.approx(hi, rel=1e-6), "CT is Reynolds-blind"
    assert abs(hi / lo - 1) < 0.5, "Reynolds sensitivity is implausibly strong"


def test_numeric_and_symbolic_paths_agree():
    """solve() root-finds numerically, chain() builds CasADi graphs. Same physics."""
    t = propulsion.PropTable("apc_11x7e")
    J, n = ca.MX.sym("J"), ca.MX.sym("n")
    f = ca.Function("f", [J, n], [t.ct(J, n), t.cp(J, n)])
    for j, nn in POINTS:
        ct_sym, cp_sym = f(j, nn)
        assert float(ct_sym) == pytest.approx(float(t.ct(j, nn)), rel=1e-12)
        assert float(cp_sym) == pytest.approx(float(t.cp(j, nn)), rel=1e-12)


def test_gradients_are_finite_across_the_table():
    """A NaN in the Jacobian is an IPOPT restoration failure hours into a battery."""
    t = propulsion.PropTable("apc_11x7e")
    J, n = ca.MX.sym("J"), ca.MX.sym("n")
    jac = ca.Function("g", [J, n], [ca.jacobian(t.ct(J, n), ca.vertcat(J, n))])
    for j in np.linspace(0.05, t.j_max, 25):
        for nn in (20.0, 60.0, 160.0):
            assert np.all(np.isfinite(np.array(jac(j, nn)))), f"non-finite at J={j}, n={nn}"


@pytest.mark.parametrize("key", ["apc_11x55e", "apc_11x6", "apc_11x7e"])
def test_fit_is_monotonic_and_physical(key):
    """CT must fall with advance ratio and reach ~0 by the table's J ceiling."""
    t = propulsion.PropTable(key)
    n = t.n_at_mid_reynolds()
    ct = np.array([float(t.ct(j, n)) for j in np.linspace(0.05, t.j_max, 40)])
    assert np.all(np.diff(ct) < 0), "CT(J) is not monotonically decreasing"
    assert ct[0] > 0.05 and ct[-1] < 0.03


@pytest.mark.parametrize("key", ["apc_11x55e", "apc_11x6", "apc_11x7e"])
def test_peak_efficiency_is_sane(key):
    t = propulsion.PropTable(key)
    j_peak = t.j_peak_eta()
    assert 0.2 < j_peak < t.j_max
    eta = float(t.eta(j_peak, t.n_at_mid_reynolds()))
    assert 0.4 < eta < 0.9, f"{key} peak eta {eta:.3f} is not a real propeller"


def test_peak_efficiency_tracks_reynolds():
    """j_peak_eta takes an operating point because the peak moves with Reynolds."""
    t = propulsion.PropTable("apc_11x7e")
    assert t.j_peak_eta(30.0) != pytest.approx(t.j_peak_eta(120.0), rel=1e-6)


def test_shipped_fits_meet_a_quality_bar():
    """Median fit error across the catalogue, measured at ingest time."""
    errs = [
        propulsion.PropTable(k).meta.get("eta_rel_pct", 0.0)
        for k in propulsion.available_props()
    ]
    assert np.median(errs) < 2.0, f"median eta fit error {np.median(errs):.2f}%"
    assert np.percentile(errs, 95) < 8.0
