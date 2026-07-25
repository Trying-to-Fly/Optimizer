"""Propulsion chain — MODEL_DETAILS.md section 2.

Contract: (V, required thrust T, PowertrainConfig) -> P_elec + diagnostics
(RPM, advance ratio J, per-stage efficiencies). Objective-agnostic; mission
evaluators compose it.

M1 implementation (numeric, fixed-design evaluation): prop from the fitted APC
proxy table (planeopt/data/props/*.json, built by tools/ingest_props.py) with the
folding derate applied to shaft power; motor equivalent circuit via AeroSandbox's
motor_electric_performance; ESC as constant efficiency. The M2 optimizer replaces
the root-solve with an Opti variable + thrust-match equality (same physics).

Proxy tables are package data, so they resolve identically from a source tree, an
installed wheel, and a frozen (PyInstaller) build. `PLANEOPT_PROPS_DIR` prepends a
user directory to the search path — that is how an end user adds their own prop
without touching the install.
"""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path

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
            keys += [p.stem for p in sorted(d.glob("*.json")) if p.stem not in keys]
    return keys


def find_prop_table(key: str) -> Path:
    for d in props_search_path():
        candidate = d / f"{key}.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No proxy table {key!r}. Searched {[str(d) for d in props_search_path()]}; "
        f"available: {available_props() or '(none)'}. Build one with "
        f"tools/ingest_props.py, or point {PROPS_DIR_ENV} at a directory holding it."
    )


class PropTable:
    """Smooth CT(J)/CP(J) fits of an APC proxy table."""

    def __init__(self, key: str):
        meta = json.loads(find_prop_table(key).read_text(encoding="utf-8"))
        self.key = key
        self.ct_coeffs = np.array(meta["ct_coeffs"])
        self.cp_coeffs = np.array(meta["cp_coeffs"])
        self.j_max = meta["j_range"][1]

    def ct(self, J):
        return np.polyval(self.ct_coeffs, J)

    def cp(self, J):
        return np.polyval(self.cp_coeffs, J)

    def eta(self, J):
        return J * self.ct(J) / self.cp(J)

    def j_peak_eta(self) -> float:
        jj = np.linspace(0.05, self.j_max, 200)
        return float(jj[np.argmax(self.eta(jj))])


def solve(V: float, thrust_req: float, pt: PowertrainConfig, rho: float = 1.225) -> dict:
    """Find the operating point delivering `thrust_req` at airspeed `V`.

    Returns P_elec (bus watts, incl. ESC) + full diagnostics. Raises ValueError if
    the prop cannot make that thrust inside its table's J range at sane RPM.
    """
    prop = PropTable(pt.prop.proxy_table)
    D = pt.prop.diameter_m

    def thrust_residual(n):  # n: rev/s
        J = V / (n * D)
        return prop.ct(J) * rho * n**2 * D**4 - thrust_req

    # bracket: n_min set by J <= j_max (prop still thrusting), n_max generous
    n_min = V / (prop.j_max * D) + 1e-6
    n_max = 250.0
    if thrust_residual(n_max) < 0:
        raise ValueError(f"thrust {thrust_req:.1f} N unreachable at V={V:.1f}")
    n = brentq(thrust_residual, n_min, n_max, xtol=1e-6)

    J = V / (n * D)
    p_shaft_ideal = prop.cp(J) * rho * n**3 * D**5
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
    return {
        "P_elec_w": p_bus,
        "rpm": n * 60.0,
        "J": float(J),
        "J_peak_eta": prop.j_peak_eta(),
        "thrust_n": thrust_req,
        "torque_nm": float(torque),
        "motor_voltage": float(motor["voltage"]),
        "motor_current_a": float(motor["current"]),
        "throttle_frac": float(motor["voltage"]) / pt.battery.v_nominal,
        "eta_prop": float(eta_prop),
        "eta_motor": float(p_shaft / p_motor_in) if p_motor_in > 0 else 0.0,
        "eta_chain": float(thrust_req * V / p_bus) if p_bus > 0 else 0.0,
    }


def _horner(coeffs, x):
    """polyval that stays symbolic-safe (works on floats and CasADi MX)."""
    y = 0.0
    for c in coeffs:
        y = y * x + float(c)
    return y


def chain(V, n, pt: PowertrainConfig, rho: float = 1.225) -> dict:
    """Symbolic-safe propulsion chain for the optimizer (MODEL_DETAILS section 6.1).

    V: airspeed, n: prop speed in rev/s — both may be Opti variables. The caller
    adds the thrust-match equality (thrust == drag). Same physics as solve().
    """
    prop = PropTable(pt.prop.proxy_table)
    D = pt.prop.diameter_m
    J = V / (n * D)
    ct = _horner(prop.ct_coeffs, J)
    cp = _horner(prop.cp_coeffs, J)
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
