"""Aero & trim — MODEL_DETAILS.md section 3.

M1 implementation (numeric, fixed design):
- Lifting surfaces: asb.LiftingLine — nonlinear lifting line, viscous from
  NeuralFoil 2D data, handles sweep/dihedral/multiple wings, and respects
  ControlSurface deflections (explicit pitch-control trim, section 3.3; the
  trim surface's name is declared by the aircraft, `pitch_control_name`).
- Non-lifting bodies: flat-plate + form-factor buildup from
  aircraft.parasite_bodies(), plus an excrescence margin (section 3.1).
- Trim: 2-unknown root solve (alpha, symmetric pitch-control deflection) for
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
from scipy.optimize import least_squares, root

from . import geometry

EXCRESCENCE = 1.08  # saddle, hatch lips, wires, hinge gaps (section 3.1)


def body_cd0(bodies: list[dict], V: float, s_ref: float, rho=1.225, mu=1.81e-5) -> float:
    """Flat-plate turbulent Cf x form factor x wetted area, referenced to s_ref.

    The body lengths are whatever the aircraft's `parasite_bodies` produced, so
    in the NLP they are expressions in the design variables and an infeasible
    iterate may hand this a non-positive one. `(-Re)**0.2` is NaN, and a NaN
    reaching a constraint row fails the SOLVE rather than the point — so the
    length is floored (geometry.smooth_floor) before it becomes a Reynolds
    number. Feasible designs are unaffected to within a micrometre; the
    constraint that owns the dimension still does the rejecting."""
    d = 0.0
    for b in bodies:
        re_l = rho * V * geometry.smooth_floor(b["length_m"]) / mu
        cf = 0.074 / re_l**0.2
        d += cf * b["form_factor"] * b["wetted_area_m2"]
    return EXCRESCENCE * d / s_ref


def _run_ll(airplane, V, alpha, deflection, x_cg, control_name="ruddervator"):
    p = airplane.with_control_deflections({control_name: float(deflection)})
    return asb.LiftingLine(
        airplane=p,
        op_point=asb.OperatingPoint(velocity=V, alpha=float(alpha)),
        xyz_ref=[x_cg, 0, 0],
    ).run()


def trim(
    airplane, V: float, weight_n: float, x_cg: float, bodies: list[dict], rho=1.225,
    control_name: str = "ruddervator",
    guess: tuple[float, float] | None = None,
) -> dict:
    """Solve (alpha, pitch-control deflection) for L = W and Cm = 0 at speed V.

    The pitch-trim surface is declared by the aircraft (`pitch_control_name`,
    e.g. "ruddervator" or "elevator") — the framework assumes no tail type.

    `guess` seeds the root-find with (alpha_deg, deflection_deg). It matters more
    than it looks: the default (2 deg, 0 deg) is near the answer for a loiter
    design and nowhere near it for an airframe that trims at 20+ deg of
    elevator, where the solver simply stops making progress. Callers sweeping a
    speed range should pass the previous point's solution (continuation).
    """
    s_ref = airplane.s_ref
    q = 0.5 * rho * V**2
    cl_req = weight_n / (q * s_ref)

    def residuals(x):
        a, d = x
        r = _run_ll(airplane, V, a, d, x_cg, control_name)
        return [float(r["CL"]) - cl_req, float(r["Cm"])]

    # Trim is a stiff 2-D root-find and `hybr` from a single start is brittle:
    # it converges instantly for a loiter design and stalls out ("not making good
    # progress") for an airframe trimming at large deflection. So: try the seeded
    # start, then a bounded least-squares from the same point (far more tolerant
    # of a poor start), then a small spread of starts covering nose-up and
    # nose-down trim. First success wins; the physics is identical in each case.
    starts = [tuple(guess)] if guess is not None else []
    starts += [(2.0, 0.0), (4.0, -10.0), (4.0, 10.0), (1.0, -20.0), (6.0, 20.0)]

    alpha = deflection = None
    last_message = "no attempt made"
    for x0 in starts:
        sol = root(residuals, x0=list(x0), method="hybr", tol=1e-8)
        if sol.success:
            alpha, deflection = sol.x
            break
        last_message = sol.message
        ls = least_squares(residuals, x0=list(x0), xtol=1e-10, ftol=1e-10)
        if ls.success and max(abs(r) for r in residuals(ls.x)) < 1e-6:
            alpha, deflection = ls.x
            break
        last_message = f"{sol.message} / least-squares residual too large"
    if alpha is None:
        raise RuntimeError(f"trim failed at V={V}: {last_message}")
    r = _run_ll(airplane, V, alpha, deflection, x_cg, control_name)

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
        if vol is not None:  # structural check — volume may be an Opti symbolic
            total += 2 * b.get("munk_factor", 0.9) * vol
    return total / (s_ref * c_ref)


#: THE static-margin estimator's alpha window (deg, relative to the trim point).
#: SM here is a REGRESSION SLOPE, not a derivative — LiftingLine's Cm(CL) is
#: nonlinear enough over a few degrees that the window is part of the estimator's
#: definition, so two callers sampling different windows measure different
#: quantities and disagree by ~0.002 on the same airplane. That is a quarter of
#: this project's SM window and it read, for four champions running, as the
#: design missing its own floor (HANDOFF issue 5). The NLP and the numeric
#: re-evaluation therefore share this constant rather than each choosing.
SM_ALPHA_OFFSETS = (-2.0, 0.0, 2.0)
#: Extra alphas the NUMERIC path samples for the nonlinearity diagnostic only —
#: they never enter the regression above, so they cost the NLP nothing.
SM_DIAGNOSTIC_OFFSETS = (-1.0, 1.0)


def _slope(xs, ys):
    """Least-squares slope dy/dx, written as plain arithmetic so it is
    symbolic-safe (the NLP builds this out of CasADi expressions)."""
    n = len(xs)
    x_bar = sum(xs) / n
    y_bar = sum(ys) / n
    cov = sum((xs[i] - x_bar) * (ys[i] - y_bar) for i in range(n))
    var = sum((xs[i] - x_bar) ** 2 for i in range(n))
    return cov / var


def static_margin_from_polar(cls, cms, offsets_deg, bodies, s_ref, c_ref):
    """SM = -dCm/dCL, from surface runs already made at `offsets_deg`.

    The single estimator, shared by the NLP and by the numeric re-evaluation.
    `offsets_deg` are relative to the trim alpha; only differences matter, so
    the absolute alpha may be symbolic without entering here. The Munk fuselage
    term is converted to CL-space via the lift slope measured on the same runs.
    """
    sm = -_slope(cls, cms)
    if bodies:
        cl_alpha_rad = _slope(offsets_deg, cls) * 180 / np.pi
        sm = sm - fuselage_cm_alpha(bodies, s_ref, c_ref) / cl_alpha_rad
    return sm


def static_margin(
    airplane, V: float, x_cg: float, c_ref: float, alpha0=2.0, bodies: list[dict] | None = None
) -> dict:
    """SM = -dCm/dCL about the CG; x_np = x_cg + SM * c_ref.

    A regression over an alpha window centered on alpha0 rather than a +/-1 deg
    finite difference: LiftingLine's Cm(alpha) is nonlinear enough that the local
    derivative varies strongly with alpha (see FINDINGS.md — the SM model's
    dominant fidelity issue, along with the missing fuselage moment). The
    per-alpha local slopes are returned so that nonlinearity stays visible.

    The reported margin comes from SM_ALPHA_OFFSETS, the same window the NLP
    constrains; the intermediate alphas feed only the diagnostic."""
    offsets = sorted(SM_ALPHA_OFFSETS + SM_DIAGNOSTIC_OFFSETS)
    alphas = np.array([alpha0 + d for d in offsets])
    runs = {d: _run_ll(airplane, V, alpha0 + d, 0.0, x_cg) for d in offsets}
    cls = {d: float(r["CL"]) for d, r in runs.items()}
    cms = {d: float(r["Cm"]) for d, r in runs.items()}
    sm = float(
        static_margin_from_polar(
            [cls[d] for d in SM_ALPHA_OFFSETS],
            [cms[d] for d in SM_ALPHA_OFFSETS],
            list(SM_ALPHA_OFFSETS),
            bodies,
            float(airplane.s_ref),
            c_ref,
        )
    )
    local = [
        {
            "alpha": float(alphas[i]),
            "sm_local": -float(
                (cms[offsets[i + 1]] - cms[offsets[i]])
                / (cls[offsets[i + 1]] - cls[offsets[i]])
            ),
        }
        for i in range(len(offsets) - 1)
    ]
    return {
        "static_margin": sm,
        "x_np_m": x_cg + sm * c_ref,
        "sm_local_slopes": local,
        "sm_alpha_window_deg": [float(alpha0 + d) for d in SM_ALPHA_OFFSETS],
    }


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
