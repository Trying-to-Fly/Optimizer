"""Aero & trim — MODEL_DETAILS.md section 3.

M1 implementation (numeric, fixed design):
- Lifting surfaces: asb.LiftingLine — nonlinear lifting line, viscous from
  NeuralFoil 2D data, handles sweep/dihedral/multiple wings, and respects
  ControlSurface deflections (explicit ruddervator trim, section 3.3).
- Non-lifting bodies: flat-plate + form-factor buildup from
  aircraft.parasite_bodies(), plus an excrescence margin (section 3.1).
- Trim: 2-unknown root solve (alpha, symmetric ruddervator deflection) for
  L = W and Cm(CG) = 0.
- Stall: wing-level CL_max from the root airfoil's NeuralFoil cl_max at stall Re
  with a 3D knockdown; the critical-section method replaces this at M2/M3.
- Static margin: dCm/dCL about the CG by finite difference on alpha.

Dual smooth/tripped polar evaluation (section 3.2) is deferred to M2 — LiftingLine
takes airfoil data as-is; the tripped pass will re-run with modified airfoils.
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np
from scipy.optimize import root

EXCRESCENCE = 1.08  # saddle, hatch lips, wires, hinge gaps (section 3.1)


def body_cd0(bodies: list[dict], V: float, s_ref: float, rho=1.225, mu=1.81e-5) -> float:
    """Flat-plate turbulent Cf x form factor x wetted area, referenced to s_ref."""
    d = 0.0
    for b in bodies:
        re_l = rho * V * b["length_m"] / mu
        cf = 0.074 / re_l**0.2
        d += cf * b["form_factor"] * b["wetted_area_m2"]
    return EXCRESCENCE * d / s_ref


def _run_ll(airplane, V, alpha, deflection, x_cg):
    p = airplane.with_control_deflections({"ruddervator": float(deflection)})
    return asb.LiftingLine(
        airplane=p,
        op_point=asb.OperatingPoint(velocity=V, alpha=float(alpha)),
        xyz_ref=[x_cg, 0, 0],
    ).run()


def trim(airplane, V: float, weight_n: float, x_cg: float, bodies: list[dict], rho=1.225) -> dict:
    """Solve (alpha, ruddervator deflection) for L = W and Cm = 0 at speed V."""
    s_ref = airplane.s_ref
    q = 0.5 * rho * V**2
    cl_req = weight_n / (q * s_ref)

    def residuals(x):
        a, d = x
        r = _run_ll(airplane, V, a, d, x_cg)
        return [float(r["CL"]) - cl_req, float(r["Cm"])]

    sol = root(residuals, x0=[2.0, 0.0], method="hybr", tol=1e-8)
    if not sol.success:
        raise RuntimeError(f"trim failed at V={V}: {sol.message}")
    alpha, deflection = sol.x
    r = _run_ll(airplane, V, alpha, deflection, x_cg)

    cd_total = float(r["CD"]) + body_cd0(bodies, V, s_ref)
    drag = q * s_ref * cd_total
    return {
        "V_ms": V,
        "alpha_deg": float(alpha),
        "deflection_deg": float(deflection),
        "CL": float(r["CL"]),
        "CD_surfaces": float(r["CD"]),
        "CD_bodies": body_cd0(bodies, V, s_ref),
        "CD_total": cd_total,
        "L_over_D": float(r["CL"]) / cd_total,
        "drag_n": drag,
    }


def stall_speed(airplane, weight_n: float, rho=1.225, knockdown=0.90) -> dict:
    """Wing-level stall estimate: 3D CL_max = knockdown x root-airfoil 2D cl_max."""
    wing = airplane.wings[0]
    af = wing.xsecs[0].airfoil
    c_mean = wing.area() / wing.span()

    v = 8.0  # iterate Re(V_stall) once
    for _ in range(2):
        re = rho * v * c_mean / 1.81e-5
        aero = af.get_aero_from_neuralfoil(
            alpha=np.arange(0, 16.0, 0.25), Re=re, model_size="large"
        )
        cl_max_2d = float(np.max(aero["CL"]))
        cl_max_3d = knockdown * cl_max_2d
        v = float(np.sqrt(2 * weight_n / (rho * airplane.s_ref * cl_max_3d)))
    return {"v_stall_ms": v, "cl_max_2d": cl_max_2d, "cl_max_3d": cl_max_3d, "re": re}


def fuselage_cm_alpha(bodies: list[dict], s_ref, c_ref) -> float:
    """Munk slender-body destabilizing moment: dCm/dalpha (per rad, about any
    point — it is a pure moment) = 2*k*Volume / (S_ref*c_ref). Bodies without a
    volume_m3 entry contribute nothing. k ~0.85-0.95 for high fineness."""
    total = 0.0
    for b in bodies:
        vol = b.get("volume_m3")
        if vol:
            total += 2 * b.get("munk_factor", 0.9) * vol
    return total / (s_ref * c_ref)


def static_margin(
    airplane, V: float, x_cg: float, c_ref: float, alpha0=2.0, bodies: list[dict] | None = None
) -> dict:
    """SM = -dCm/dCL about the CG; x_np = x_cg + SM * c_ref.

    Least-squares slope over an alpha window centered on alpha0 rather than a
    +/-1 deg finite difference: LiftingLine's Cm(alpha) is nonlinear enough that
    the local derivative varies strongly with alpha (see FINDINGS.md — the SM
    model's dominant fidelity issue, along with the missing fuselage moment).
    The per-alpha local slopes are returned so the nonlinearity is visible."""
    alphas = np.array([alpha0 + d for d in (-2.0, -1.0, 0.0, 1.0, 2.0)])
    runs = [_run_ll(airplane, V, a, 0.0, x_cg) for a in alphas]
    cls = np.array([float(r["CL"]) for r in runs])
    cms = np.array([float(r["Cm"]) for r in runs])
    A = np.vstack([cls, np.ones_like(cls)]).T
    slope, _ = np.linalg.lstsq(A, cms, rcond=None)[0]
    sm = -float(slope)
    if bodies:
        # fuselage destabilization, converted to CL-space via the lift slope
        a_deg = np.linalg.lstsq(
            np.vstack([alphas, np.ones_like(alphas)]).T, cls, rcond=None
        )[0][0]
        cl_alpha_rad = float(a_deg) * 180 / np.pi
        sm -= fuselage_cm_alpha(bodies, float(airplane.s_ref), c_ref) / cl_alpha_rad
    local = [
        {"alpha": alphas[i], "sm_local": -float((cms[i + 1] - cms[i]) / (cls[i + 1] - cls[i]))}
        for i in range(len(alphas) - 1)
    ]
    return {"static_margin": sm, "x_np_m": x_cg + sm * c_ref, "sm_local_slopes": local}


def clmax_3d(airfoil, re: float, knockdown: float = 0.90) -> float:
    """Numeric wing-level CL_max used as a constant in the M2 NLP (weak Re
    dependence; the critical-section method replaces this at M3)."""
    aero = airfoil.get_aero_from_neuralfoil(
        alpha=np.arange(0, 16.0, 0.25), Re=re, model_size="large"
    )
    return knockdown * float(np.max(aero["CL"]))


def tripped_cd_delta(airplane, V: float, CL: float, rho=1.225, mu=1.81e-5) -> dict:
    """Profile-drag increment if all laminar runs are lost (layer lines): NeuralFoil
    with forced transition at 5% chord vs. natural transition, per surface at its
    approximate operating cl and mean-chord Re, referenced to s_ref.
    (MODEL_DETAILS section 3.2 — numeric dual evaluation, not in the NLP.)"""
    delta = 0.0
    detail = {}
    for i, wing in enumerate(airplane.wings):
        c_mean = wing.area() / wing.span()
        re = rho * V * c_mean / mu
        cl_local = CL if i == 0 else 0.0  # tail near zero lift at cruise
        af = wing.xsecs[0].airfoil
        # find alpha matching cl_local on the smooth polar, then compare cd
        alphas = np.arange(-2, 10, 0.25)
        smooth = af.get_aero_from_neuralfoil(alpha=alphas, Re=re, model_size="large")
        idx = int(np.argmin(np.abs(np.array(smooth["CL"]) - cl_local)))
        a = float(alphas[idx])
        s_pt = af.get_aero_from_neuralfoil(alpha=a, Re=re, model_size="large")
        t_pt = af.get_aero_from_neuralfoil(
            alpha=a, Re=re, model_size="large", xtr_upper=0.05, xtr_lower=0.05
        )
        d = (float(np.ravel(t_pt["CD"])[0]) - float(np.ravel(s_pt["CD"])[0])) * (
            wing.area() / airplane.s_ref
        )
        delta += d
        detail[wing.name] = {"re": re, "alpha_used": a, "dcd": d}
    return {"dcd_total": delta, "per_surface": detail}


def vlm_induced_check(planes: dict, V: float, alphas=(2.0, 4.0, 6.0), rho=1.225) -> dict:
    """Numeric second opinion on nonplanar induced drag (winglet study,
    MODEL_DETAILS 3.6): fit CD = CD0 + k*CL^2 to an inviscid VLM alpha sweep per
    configuration. LL is the in-loop model; comparing k across {winglet_on,
    winglet_off} checks the induced-drag delta with an independent method.
    (LL was the conservative of the two in the feasibility test.)"""
    out = {}
    for label, plane in planes.items():
        cls, cds = [], []
        for a in alphas:
            r = asb.VortexLatticeMethod(
                airplane=plane,
                op_point=asb.OperatingPoint(velocity=V, alpha=float(a)),
                xyz_ref=[0.0, 0.0, 0.0],
            ).run()
            cls.append(float(r["CL"]))
            cds.append(float(r["CD"]))
        k, cd0 = np.polyfit(np.array(cls) ** 2, np.array(cds), 1)
        ar = float(plane.b_ref**2 / plane.s_ref)
        out[label] = {
            "k_induced": float(k),
            "cd0_inviscid": float(cd0),
            # span efficiency wrt PROJECTED span — e > 1 is the nonplanar payoff
            "e_projected_span": float(1 / (np.pi * ar * k)),
        }
    return out


# ---------------------------------------------------------------- stall (M3.5)
# Critical-section method (MODEL_DETAILS 3.4): Schrenk spanwise loading + local
# 2D cl_max at local Re; the wing "stalls" when any station hits its section
# limit. Approximations, documented: Schrenk loading (not the LL distribution),
# 2D washout increment with a_2d ~ 5.7/rad, section-limit factor 0.95.

A2D_PER_RAD = 5.7
SECTION_FACTOR = 0.95


def clmax_log_fit(airfoil, re_lo=6e4, re_hi=3e5, n=5) -> tuple[float, float]:
    """Numeric precompute: cl_max(Re) ~ A + B*ln(Re) over the class's Re range."""
    res = np.geomspace(re_lo, re_hi, n)
    clm = []
    for re in res:
        aero = airfoil.get_aero_from_neuralfoil(
            alpha=np.arange(0, 16.0, 0.25), Re=re, model_size="large"
        )
        clm.append(float(np.max(aero["CL"])))
    B, A = np.polyfit(np.log(res), clm, 1)
    return float(A), float(B)


def wing_stations(wing) -> list[dict]:
    """Analysis stations from a Wing's xsec breakpoints + panel midpoints.

    Pure attribute arithmetic — works with floats or Opti symbolics, any
    architecture built from xsecs. Root station excluded (never critical)."""
    xs = wing.xsecs
    st = []
    for i in range(len(xs) - 1):
        y0, y1 = xs[i].xyz_le[1], xs[i + 1].xyz_le[1]
        c0, c1 = xs[i].chord, xs[i + 1].chord
        t0, t1 = xs[i].twist, xs[i + 1].twist
        st.append({"y": (y0 + y1) / 2, "c": (c0 + c1) / 2, "twist": (t0 + t1) / 2})
        st.append({"y": y1, "c": c1, "twist": t1})
    return st


def critical_section_ratios(stations, S, b, CL, V, clmax_ab, rho=1.225, mu=1.81e-5):
    """cl_local/cl_max_local per station at (CL, V). Symbolic-safe.

    Schrenk: c_S = (c + c_ell)/2; cl = CL*c_S/c + a_2d*(twist - twist_bar) with
    the loading-weighted mean twist. sqrt is regularized at the tip."""
    A, B = clmax_ab
    c_s, cl_base = [], []
    for st in stations:
        eta = 2 * st["y"] / b
        c_ell = (4 * S / (np.pi * b)) * (1 - eta**2 + 1e-4) ** 0.5
        c_s.append((st["c"] + c_ell) / 2)
    w_sum = sum(c_s)
    t_bar = sum(c_s[i] * stations[i]["twist"] for i in range(len(stations))) / w_sum
    out = []
    for i, st in enumerate(stations):
        cl = CL * c_s[i] / st["c"] + A2D_PER_RAD * (st["twist"] - t_bar) * np.pi / 180
        re = rho * V * st["c"] / mu
        clmax = SECTION_FACTOR * (A + B * np.log(re))
        out.append(cl / clmax)
    return out


def smooth_max(vals, sharpness=20.0):
    """Log-sum-exp upper bound on max(vals); symbolic-safe, differentiable."""
    return np.log(sum(np.exp(sharpness * v) for v in vals)) / sharpness


def critical_stall_speed(airplane, weight_n, clmax_ab, rho=1.225) -> dict:
    """Numeric: V where the most-loaded station reaches its section limit."""
    wing = airplane.wings[0]
    stations = wing_stations(wing)
    S, b = float(wing.area()), float(wing.span())

    def worst(V):
        CL = weight_n / (0.5 * rho * V**2 * S)
        r = critical_section_ratios(stations, S, b, CL, V, clmax_ab, rho)
        return max(float(x) for x in r)

    lo, hi = 5.0, 20.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if worst(mid) > 1:
            lo = mid
        else:
            hi = mid
    v_stall = (lo + hi) / 2
    CL = weight_n / (0.5 * rho * v_stall**2 * S)
    ratios = [float(x) for x in critical_section_ratios(stations, S, b, CL, v_stall, clmax_ab, rho)]
    return {
        "v_stall_ms": v_stall,
        "stations_y": [float(s["y"]) for s in stations],
        "ratios_at_stall": ratios,
        "critical_y": float(stations[int(np.argmax(ratios))]["y"]),
        "clmax_ab": clmax_ab,
    }
