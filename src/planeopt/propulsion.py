"""Propulsion chain — MODEL_DETAILS.md section 2.

Contract: (V, required thrust T, PowertrainConfig) -> P_elec + diagnostics
(RPM, advance ratio J, per-stage efficiencies). Objective-agnostic; mission
evaluators compose it.

M1 implementation (numeric, fixed-design evaluation): prop from the fitted APC
proxy table (planeopt/data/props/*.json, built by tools/ingest_props.py) with the
folding derate applied to shaft power; motor equivalent circuit via AeroSandbox's
motor_electric_performance; ESC as constant efficiency. The M2 optimizer replaces
the root-solve with an Opti variable + thrust-match equality (same physics).

The prop model is a surface in TWO variables, CT(J, Re) — see PropTable and
MODEL_DETAILS §2.1.1 for why advance ratio alone was not enough. Both the numeric
path (`solve`, brentq) and the symbolic path (`chain`, CasADi) evaluate the same
fit through the same nested-Horner code, so they cannot drift apart.

Proxy tables are package data, so they resolve identically from a source tree, an
installed wheel, and a frozen (PyInstaller) build. The whole published APC
catalogue ships (443 tables — `planeopt props` lists them), and
`PLANEOPT_PROPS_DIR` prepends a user directory to the search path, which is how
an end user adds a prop of their own without touching the install.
"""

from __future__ import annotations

import difflib
import functools
import json
import os
from importlib.resources import files
from pathlib import Path

import aerosandbox.numpy as anp
import numpy as np
from aerosandbox.library import propulsion_electric as pe
from scipy.optimize import brentq

from .types import PowertrainConfig

BUILTIN_PROPS_DIR = Path(str(files("planeopt") / "data" / "props"))
PROPS_DIR_ENV = "PLANEOPT_PROPS_DIR"


def props_search_path() -> list[Path]:
    """User override directory (if set) first, then the tables shipped with the app."""
    override = os.environ.get(PROPS_DIR_ENV)
    return ([Path(override)] if override else []) + [BUILTIN_PROPS_DIR]


def available_props() -> list[str]:
    """Proxy-table keys resolvable right now, nearest override first."""
    keys: list[str] = []
    for d in props_search_path():
        if d.is_dir():
            # sort on the KEY, not the filename: sorting paths puts apc_11x7e-3
            # ahead of apc_11x7e, because '-' sorts before the '.' of '.json'
            keys += sorted({p.stem for p in d.glob("*.json")} - set(keys))
    return keys


def find_prop_table(key: str) -> Path:
    for d in props_search_path():
        candidate = d / f"{key}.json"
        if candidate.is_file():
            return candidate
    have = available_props()
    # Naming every table was helpful at three of them and useless at 443, so the
    # suggestion is a did-you-mean plus a count of the rest.
    near = difflib.get_close_matches(key, have, n=5, cutoff=0.6) or have[:5]
    raise FileNotFoundError(
        f"No proxy table {key!r}. Searched {[str(d) for d in props_search_path()]}; "
        f"{len(have)} available"
        + (f", closest: {', '.join(near)}" if have else " (none)")
        + f". List them with `planeopt props`, build more with tools/ingest_props.py, "
        f"or point {PROPS_DIR_ENV} at a directory holding your own."
    )


OMEGA_75 = 0.75 * np.pi  # 75%-span radius ratio, as an angular-to-linear factor


@functools.lru_cache(maxsize=64)
def _read_table(path: Path, mtime: float) -> dict:
    """Parse one table. Keyed on mtime so an edited table is still picked up.

    The dict is SHARED between every PropTable built from that file — read-only.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _load_table(path: Path) -> dict:
    """chain() rebuilds a PropTable on every call while the NLP graph is built,
    and the tables live on package data that may sit on a slow filesystem, so the
    parse is cached. Resolution still happens per call, which is what keeps
    PLANEOPT_PROPS_DIR switchable at runtime."""
    return _read_table(path, path.stat().st_mtime)


def _horner(coeffs, x):
    """polyval that stays symbolic-safe (works on floats and CasADi MX)."""
    y = 0.0
    for c in coeffs:
        y = y * x + float(c)
    return y


def _horner2(grid, x, y):
    """Bivariate polyval: grid is descending in x (rows) and y (within a row)."""
    total = 0.0
    for row in grid:
        total = total * x + _horner(row, y)
    return total


class PropTable:
    """Smooth CT(J,Re)/CP(J,Re) fits of an APC proxy table.

    Reynolds is the second variable because CT/CP at a fixed advance ratio drift
    systematically with it, and a single-variable fit can only hide that by
    picking an RPM window -- a choice that depends on both the aircraft and the
    prop diameter, so no one window is right for a whole catalogue. Reynolds is
    not an extra unknown: it follows from the operating point via the blade speed
    at 75% span, with one stored per-prop constant (tools/ingest_props.py).
    """

    def __init__(self, key: str):
        meta = _load_table(find_prop_table(key))
        self.key = key
        self.meta = meta
        self.ct_coeffs = meta["ct_coeffs"]
        self.cp_coeffs = meta["cp_coeffs"]
        self.j_max = meta["j_range"][1]
        self.re_coeff = meta["re_coeff"]
        self.re_range = tuple(meta["re_range"])
        self._re_ref = meta["log_re_ref"]
        self._re_scale = meta["log_re_scale"]

    def reynolds(self, J, n):
        """Blade Reynolds at 75% span for advance ratio J and n rev/s."""
        return self.re_coeff * n * anp.sqrt(OMEGA_75**2 + J**2)

    def _u(self, J, n):
        return (anp.log(self.reynolds(J, n)) - self._re_ref) / self._re_scale

    def ct(self, J, n):
        return _horner2(self.ct_coeffs, J, self._u(J, n))

    def cp(self, J, n):
        return _horner2(self.cp_coeffs, J, self._u(J, n))

    def eta(self, J, n):
        return J * self.ct(J, n) / self.cp(J, n)

    def n_at_mid_reynolds(self) -> float:
        """A representative rev/s: the geometric-mean fitted Re at mid advance ratio."""
        re_mid = float(np.sqrt(self.re_range[0] * self.re_range[1]))
        return re_mid / (self.re_coeff * float(np.sqrt(OMEGA_75**2 + (0.5 * self.j_max) ** 2)))

    def j_peak_eta(self, n: float | None = None) -> float:
        """Advance ratio of peak efficiency along the operating locus at n rev/s.

        Peak-eta J is mildly Reynolds-dependent, so callers with a real operating
        point should pass its n; the default reports at mid-table Reynolds.
        """
        n = self.n_at_mid_reynolds() if n is None else n
        jj = np.linspace(0.05, self.j_max, 200)
        return float(jj[np.argmax(self.eta(jj, n))])


def solve(V: float, thrust_req: float, pt: PowertrainConfig, rho: float = 1.225) -> dict:
    """Find the operating point delivering `thrust_req` at airspeed `V`.

    Returns P_elec (bus watts, incl. ESC) + full diagnostics. Raises ValueError if
    the prop cannot make that thrust inside its table's J range at sane RPM.
    """
    prop = PropTable(pt.prop.proxy_table)
    D = pt.prop.diameter_m

    def thrust_residual(n):  # n: rev/s
        J = V / (n * D)
        return prop.ct(J, n) * rho * n**2 * D**4 - thrust_req

    # bracket: n_min set by J <= j_max (prop still thrusting), n_max generous
    n_min = V / (prop.j_max * D) + 1e-6
    n_max = 250.0
    if thrust_residual(n_max) < 0:
        raise ValueError(f"thrust {thrust_req:.1f} N unreachable at V={V:.1f}")
    if thrust_residual(n_min) > 0:
        # The prop already makes more thrust than the airframe needs at the
        # slowest rpm the fitted table covers, so level flight would sit at
        # J > j_max — off the end of the data. This is a prop/airframe mismatch
        # (too fine a prop for a clean, fast design), not a solver failure, and
        # it deserves to say so rather than surface as a bracketing error.
        raise ValueError(
            f"prop {prop.key} is too fine for this design at V={V:.1f}: it makes "
            f"more than the required {thrust_req:.2f} N at the lowest in-table "
            f"speed ({n_min*60:.0f} rpm, J={prop.j_max:.3f}). Level flight lies "
            f"beyond the fitted advance-ratio range — fit a coarser-pitch or "
            f"smaller-diameter prop (tools/ingest_props.py)"
        )
    n = brentq(thrust_residual, n_min, n_max, xtol=1e-6)

    J = V / (n * D)
    p_shaft_ideal = prop.cp(J, n) * rho * n**3 * D**5
    p_shaft = p_shaft_ideal / pt.prop.folding_derate  # derate = efficiency knockdown
    torque = p_shaft / (2 * np.pi * n)

    motor = pe.motor_electric_performance(
        rpm=n * 60.0,
        torque=torque,
        kv=pt.motor.kv_rpm_per_volt,
        resistance=pt.motor.resistance_ohm,
        no_load_current=pt.motor.no_load_current_a,
    )
    p_motor_in = float(motor["voltage"] * motor["current"])
    p_bus = p_motor_in / pt.esc_efficiency

    eta_prop = thrust_req * V / p_shaft if p_shaft > 0 else 0.0
    re_75 = float(prop.reynolds(J, n))
    return {
        "P_elec_w": p_bus,
        "rpm": n * 60.0,
        "J": float(J),
        "J_peak_eta": prop.j_peak_eta(n),
        # the advance-ratio/Reynolds sanity check of MODEL_DETAILS 2.3: both say
        # whether the proxy table is being read inside the region it was fitted on
        "re_75": re_75,
        "re_in_range": bool(prop.re_range[0] <= re_75 <= prop.re_range[1]),
        "thrust_n": thrust_req,
        "torque_nm": float(torque),
        "motor_voltage": float(motor["voltage"]),
        "motor_current_a": float(motor["current"]),
        "throttle_frac": float(motor["voltage"]) / pt.battery.v_nominal,
        "eta_prop": float(eta_prop),
        "eta_motor": float(p_shaft / p_motor_in) if p_motor_in > 0 else 0.0,
        "eta_chain": float(thrust_req * V / p_bus) if p_bus > 0 else 0.0,
    }


def chain(V, n, pt: PowertrainConfig, rho: float = 1.225) -> dict:
    """Symbolic-safe propulsion chain for the optimizer (MODEL_DETAILS section 6.1).

    V: airspeed, n: prop speed in rev/s — both may be Opti variables. The caller
    adds the thrust-match equality (thrust == drag). Same physics as solve().
    """
    prop = PropTable(pt.prop.proxy_table)
    D = pt.prop.diameter_m
    J = V / (n * D)
    ct = prop.ct(J, n)
    cp = prop.cp(J, n)
    thrust = ct * rho * n**2 * D**4
    p_shaft = cp * rho * n**3 * D**5 / pt.prop.folding_derate
    torque = p_shaft / (2 * np.pi * n)

    motor = pe.motor_electric_performance(
        rpm=n * 60.0,
        torque=torque,
        kv=pt.motor.kv_rpm_per_volt,
        resistance=pt.motor.resistance_ohm,
        no_load_current=pt.motor.no_load_current_a,
    )
    p_bus = motor["voltage"] * motor["current"] / pt.esc_efficiency
    return {"J": J, "j_max": prop.j_max, "thrust_n": thrust, "p_shaft_w": p_shaft,
            "p_bus_w": p_bus, "current_a": motor["current"], "voltage": motor["voltage"]}
