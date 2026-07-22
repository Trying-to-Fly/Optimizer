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


def static_margin(airplane, V: float, x_cg: float, c_ref: float, alpha0=2.0) -> dict:
    """SM = -dCm/dCL about the CG; x_np = x_cg + SM * c_ref."""
    da = 1.0
    r1 = _run_ll(airplane, V, alpha0 - da, 0.0, x_cg)
    r2 = _run_ll(airplane, V, alpha0 + da, 0.0, x_cg)
    dcm_dcl = (float(r2["Cm"]) - float(r1["Cm"])) / (float(r2["CL"]) - float(r1["CL"]))
    sm = -dcm_dcl
    return {"static_margin": sm, "x_np_m": x_cg + sm * c_ref}
