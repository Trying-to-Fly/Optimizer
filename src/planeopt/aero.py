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
    constraint that owns the dimension still does the rejecting.

    A body may also declare `base_drag_area_m2` — a drag AREA (D/q, m^2) that is
    not a skin-friction term at all: afterbody separation and the base pressure
    behind it (`fuselage.afterbody_terms`, MODEL_DETAILS 7.3). It is added
    OUTSIDE the excrescence factor, which pays for saddle steps, hatch lips and
    wires on a wetted surface and has nothing to say about a base. Bodies
    without the key — every frozen dv=None fixture — contribute exactly zero, so
    the M1 validation baseline is bit-identical.

    This function is the one seam where the buildup meets the design variables,
    and `aero.py` imports PLAIN numpy: `.get` and addition are symbolic
    transparent, anything else here would not be. New afterbody arithmetic
    belongs in `fuselage.py`, which imports `aerosandbox.numpy`."""
    d = 0.0
    d_base = 0.0
    for b in bodies:
        re_l = rho * V * geometry.smooth_floor(b["length_m"]) / mu
        cf = 0.074 / re_l**0.2
        d += cf * b["form_factor"] * b["wetted_area_m2"]
        d_base += b.get("base_drag_area_m2", 0.0)
    return (EXCRESCENCE * d + d_base) / s_ref


#: Vortex core radius for EVERY lifting-line call, in metres. AeroSandbox
#: defaults to 1e-8, which is no regularization at all: the induced velocity of
#: a filament goes as 1/r, so a control point that happens to sit a micron from
#: one gets an enormous induced velocity and the circulation solution is
#: garbage. On 2026-08-01 that produced NEGATIVE total drag on a wing with an
#: 86-degree-canted winglet — an L/D of 889 and 222 minutes of endurance, which
#: the optimizer went looking for because to a maximizer negative drag is free
#: endurance (FINDINGS section 18).
#:
#: 1e-4 m is chosen from measurement, not taste. It fixes the sign and brings the
#: in-loop mesh within ~1.3% of a 16-panel one on the offending design and ~2% on
#: the champion, while sitting a full order of magnitude below where the core
#: starts distorting the FINE mesh too (at 1e-3 the 16-panel answer itself moves
#: 8%). It is also the physically conservative direction: a real vortex core on a
#: model wing is millimetres, not nanometres.
#:
#: Refining the mesh was tried first and is the worse fix: more panels on a small
#: canted surface is more chances of near-coincident filaments, it grew the
#: CasADi graph on a solve that already peaks near 12 GB, and it converted the
#: negative drag into a NaN.
LL_VORTEX_CORE_RADIUS = 1e-4


def _run_ll(airplane, V, alpha, deflection, x_cg, control_name="ruddervator",
            spanwise_resolution=None):
    p = airplane.with_control_deflections({control_name: float(deflection)})
    # Omitted rather than defaulted when unset: the NLP runs at AeroSandbox's
    # own default, and passing a number that merely happens to equal it today
    # would silently pin this to a value the library could change underneath.
    res = {} if spanwise_resolution is None else {
        "spanwise_resolution": spanwise_resolution
    }
    return asb.LiftingLine(
        airplane=p,
        op_point=asb.OperatingPoint(velocity=V, alpha=float(alpha)),
        xyz_ref=[x_cg, 0, 0],
        vortex_core_radius=LL_VORTEX_CORE_RADIUS,
        **res,
    ).run()

#: Resolution the champion's drag is re-checked at, and how far the in-loop
#: answer may sit from it. The NLP runs LiftingLine at AeroSandbox's default 4
#: panels per section because it builds four of those graphs and each solve
#: already peaks near 12 GB — this is the cheap second opinion on that economy.
LL_CHECK_RESOLUTION = 16
LL_CHECK_TOL = 0.10


#: How far the static margin may move between the in-loop mesh and the fine one
#: before the reported margin is the DISCRETIZATION's rather than the
#: aeroplane's. Absolute, not fractional: SM is already a small dimensionless
#: number and a champion can sit near zero, where a ratio means nothing.
#: Set to the magnitude ALREADY KNOWN to change verdicts on this project rather
#: than to a round number: HANDOFF issue 5 records a ~0.002 estimator difference
#: reading, for four champions running, as the design missing its own floor. A
#: mesh that moves the margin by that much has moved the answer.
#:
#: The spec aircraft measures -0.0050 across a 4x refinement (0.0541 → 0.0491,
#: still falling at 16 panels), so it FAILS this and should: that is 2.5x the
#: known-consequential magnitude and 7% of the 0.07-wide stability window. An
#: earlier draft of this constant sat at 0.005, which the measured case passed
#: by 1e-5 — a threshold chosen to be survived rather than to mean something.
LL_SM_MESH_TOL = 0.002


def mesh_convergence_check(
    airplane, V: float, alpha: float, deflection: float, x_cg: float,
    control_name: str = "ruddervator",
    c_ref: float | None = None, bodies: list[dict] | None = None,
) -> dict:
    """Is the champion's drag a property of the aircraft or of the panel count?

    The in-loop model is a discretization, and a discretization can be WRONG in
    a way that flatters a design — which is not hypothetical here. On
    2026-08-01 a span-3.0 m solve reported 0.0275 N of total drag, an L/D of
    889 and 222 minutes of endurance, because at 4 panels per section a
    high-cant winglet contributed about -0.93 N: the optimizer had found a
    corner where the mesh, not the aeroplane, produced thrust (FINDINGS §18).

    Nothing catches that except asking a finer mesh. It costs two lifting-line
    runs at one operating point, against a battery measured in hours, and it
    turns "the model was wrong here" from something a person has to notice in a
    number into something the run says about itself.

    Given `c_ref` it also asks the same question of the STATIC MARGIN, which is
    a different question and a more important one. Drag is compared at a single
    operating point; the margin is a SLOPE over an alpha window, and a slope can
    be mesh-dependent while every individual point looks fine. Cm at the trim
    point is not the quantity to compare — trim drives it to ~0 by construction,
    so a delta there is noise about nothing. `dCm/dCL` is the quantity, and the
    verdict that matters is whether a sign change inside the window SURVIVES
    refinement: one that vanishes is a discretization artefact, one that
    persists is the model telling you something about the aeroplane. Costs two
    more sweeps (2 x 5 lifting-line runs), still seconds against hours.
    """
    plane = airplane.with_control_deflections({control_name: float(deflection)})
    op = asb.OperatingPoint(velocity=V, alpha=float(alpha))
    out = {}
    for label, res in (("in_loop", 4), ("fine", LL_CHECK_RESOLUTION)):
        r = asb.LiftingLine(
            airplane=plane, op_point=op, xyz_ref=[x_cg, 0, 0], spanwise_resolution=res,
            vortex_core_radius=LL_VORTEX_CORE_RADIUS,
        ).run()
        out[label] = {"spanwise_resolution": res, "D_n": float(r["D"]),
                      "L_n": float(r["L"]), "CL": float(r["CL"])}
    d_loop, d_fine = out["in_loop"]["D_n"], out["fine"]["D_n"]
    out["delta_frac"] = (d_loop - d_fine) / d_fine if d_fine else None
    # Both conditions matter: a NEGATIVE in-loop drag is impossible whatever the
    # fine mesh says, and a large disagreement means the number is the mesh's.
    out["converged"] = bool(
        d_loop > 0 and d_fine > 0 and abs(out["delta_frac"]) <= LL_CHECK_TOL
    )

    if c_ref is not None:
        sm = {}
        for label, res in (("in_loop", 4), ("fine", LL_CHECK_RESOLUTION)):
            s = static_margin(
                airplane, V, x_cg, c_ref, alpha0=alpha, bodies=bodies,
                spanwise_resolution=res,
            )
            local = [p["sm_local"] for p in s["sm_local_slopes"]]
            sm[label] = {
                "spanwise_resolution": res,
                "static_margin": s["static_margin"],
                "sm_local_slopes": s["sm_local_slopes"],
                # same rule as `solve.sm_sign_flip`: an already-negative margin
                # is not a hidden sign change, it is an obvious one
                "sign_consistent": bool(
                    s["static_margin"] <= 0 or all(v >= 0 for v in local)
                ),
            }
        delta = sm["fine"]["static_margin"] - sm["in_loop"]["static_margin"]
        sm["delta"] = float(delta)
        sm["converged"] = bool(abs(delta) <= LL_SM_MESH_TOL)
        # The diagnosis, and the reason this exists: does the pathology survive
        # a 4x finer mesh? If both meshes agree it is there, refinement is not
        # the explanation and the nonlinearity is the model's — for this project
        # that points at the viscous Cm, since the inviscid VLM sweep over the
        # same window is monotone (`vlm_static_margin_check`).
        sm["sign_flip_survives_refinement"] = bool(
            not sm["in_loop"]["sign_consistent"] and not sm["fine"]["sign_consistent"]
        )
        sm["sign_flip_is_mesh_artefact"] = bool(
            not sm["in_loop"]["sign_consistent"] and sm["fine"]["sign_consistent"]
        )
        out["static_margin"] = sm
    return out


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

#: Spanwise panels for the RE-EVALUATION's static margin, which is the number
#: the airworthiness gate reads. Not a preference: at AeroSandbox's default the
#: margin is OPTIMISTIC, and it converges downward (FINDINGS §38.2, same
#: champion, same window):
#:
#:     V        default     8        12       16       24
#:     9.5 m/s  0.05229  0.04973  0.04893  0.04845  0.04804
#:    10.5 m/s  0.08027  0.07728  0.07622  0.07566  0.07516
#:
#: About 0.005 of margin, which is a quarter of the declared floor and the
#: difference between "inside [0.08, 0.15]" and not: the 2026-08-11 sweep's
#: in-window points at 10.0 and 10.5 m/s fall to 0.0777 and 0.0752 here. Every
#: static margin this project reported before this constant existed is
#: optimistic by roughly that much.
#:
#: 24 rather than 16 because the sequence is flat between them (0.0004-0.0005)
#: and the cost is ~6 s per distinct sweep speed against a battery measured in
#: hours. The NLP's IN-LOOP margin still runs at the graph's own resolution —
#: refining that is a solve-time cost, not a diagnostic one, and the gate reads
#: this number.
SM_REEVAL_SPANWISE = 24


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


def local_slopes_with_uncertainty(cls, cms, alphas) -> tuple[list[dict], float]:
    """Per-interval -dCm/dCL, each with the error on measuring it.

    Pure, and separate from `static_margin`, because the question it settles is
    arithmetic rather than aerodynamic and should be answerable without a
    LiftingLine run.

    **Why the uncertainty exists at all — FINDINGS §38.3.** `sm_local` is a
    two-point difference quotient, and on rcv2 its numerator is tiny: `Cm` moves
    0.0024 across the entire +/-2 deg window at 9.5 m/s. Differenced at a 1 deg
    step the same champion reports a sign flip; at 0.5 and 2.0 deg it does not.
    The step was selecting the verdict. Since an airworthiness gate reads this,
    a negative slope has to be distinguishable from the noise before it counts.

    `sigma` is the residual scatter of a straight line through the WHOLE window
    — what `Cm` does that a constant `-dCm/dCL` cannot explain. Both endpoints
    of an interval carry it, so the difference carries `sigma*sqrt(2)`, and the
    slope divides that by the `CL` interval. Narrow intervals therefore report
    LARGER uncertainty, which is the point: that is where differencing is worst
    conditioned.

    **What this does NOT fix.** `sigma` is the residual of a straight line
    through the window, so it measures departure from linearity rather than the
    evaluation's noise floor, and the two coincide only when the window is wide
    enough to contain some curvature. Narrow the window and a curve looks
    straight: at half the production step `sigma` collapses from 5.2e-03 to
    6.2e-04 and slopes that the production reading dismisses become
    "significant" again. So this removes the false rejection at the setting the
    gate uses; it does not make the diagnostic step-independent. §38.5 says what
    would — a noise floor measured rather than inferred from the same five
    points it is judging. `tests/test_sm_local_slopes.py` pins both halves.

    Returns the per-alpha slopes and the sigma they were judged against.
    """
    cl = np.asarray(cls, dtype=float)
    cm = np.asarray(cms, dtype=float)
    slope, intercept = np.polyfit(cl, cm, 1)
    residual = cm - (intercept + slope * cl)
    # two degrees of freedom go to the fit; what is left estimates the scatter
    dof = max(len(cl) - 2, 1)
    sigma = float(np.sqrt(float((residual ** 2).sum()) / dof))

    out = []
    for i in range(len(cl) - 1):
        d_cl = float(cl[i + 1] - cl[i])
        if d_cl == 0.0:
            sm_local, uncertainty = float("nan"), float("inf")
        else:
            sm_local = -float(cm[i + 1] - cm[i]) / d_cl
            uncertainty = float(sigma * np.sqrt(2.0) / abs(d_cl))
        out.append({
            "alpha": float(alphas[i]),
            "sm_local": sm_local,
            "sm_local_uncertainty": uncertainty,
            # "This alpha is unstable" is a claim, and the airworthiness gate
            # acts on it. Only made when the negative slope is larger than the
            # error on measuring it.
            "locally_unstable": bool(sm_local < -uncertainty),
        })
    return out, sigma


def static_margin(
    airplane, V: float, x_cg: float, c_ref: float, alpha0=2.0,
    bodies: list[dict] | None = None, spanwise_resolution: int | None = None,
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
    runs = {
        d: _run_ll(airplane, V, alpha0 + d, 0.0, x_cg,
                   spanwise_resolution=spanwise_resolution)
        for d in offsets
    }
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
    local, sigma = local_slopes_with_uncertainty(
        [cls[d] for d in offsets], [cms[d] for d in offsets], list(alphas)
    )
    return {
        "static_margin": sm,
        "x_np_m": x_cg + sm * c_ref,
        "sm_local_slopes": local,
        "sm_local_sigma": sigma,
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


# --- the induced-drag cross-check runs an ENSEMBLE of meshes, not one --------
#
# HANDOFF issue 0a: this check reported `k_induced = -0.50` on the 2026-07-31
# champion — an inviscid wing whose drag FALLS as CL^2 rises, with CD = -0.54 in
# the raw sweep. Two things were wrong, and only the first is a clean fix.
#
# 1. Spanwise spacing. AeroSandbox's default is cosspace applied WITHIN each
#    wing section, so panels bunch against every section boundary. This project's
#    wing has four sections of unequal width (eta 0 / 0.16 / 0.31 / 0.80 / 1.0),
#    which leaves near-coincident horseshoes at those joints, a near-singular
#    AIC, and a circulation that is simply wrong. Uniform spanwise panels remove
#    the clustering and fix the champion outright. Chordwise cosspace is kept:
#    it is the ordinary way to resolve the leading edge, and it is not the
#    trigger.
#
# 2. It is still a fragile solve. With uniform spacing, INDIVIDUAL meshes on
#    high-cant geometries continue to blow up sporadically — a 2026-07-31
#    winglet plane returns k = 0.0226 / 0.0842 / 0.0219 at three neighbouring
#    resolutions, and a polyhedral one returns CL = 113 at (24, 12). The blow-ups
#    look perfectly physical in isolation (positive k, positive CD), so no
#    single-mesh sanity test can catch them.
#
# Hence a small ensemble and a MAJORITY rule: the reported k is the consensus of
# the meshes that agree with the median, and a configuration whose meshes cannot
# agree is reported as unreliable rather than silently shipped. Cost is ~40 s per
# configuration, once per run, against a winglet phase measured in minutes.
VLM_MESHES = ((8, 8), (12, 10), (16, 10))  # (spanwise per section, chordwise)
VLM_MESH_TOL = 0.15  # a mesh joins the consensus within this fraction of median
VLM_MIN_CONSENSUS = 2  # ... and this many must, out of len(VLM_MESHES)
#: How negative CD may go before a polar stops being a polar, as a fraction of
#: its own largest CD. Not zero: the lowest-alpha point carries the least drag
#: and the most truncation noise, and a mesh that returns CD = -9e-5 at CL 0.28
#: while being clean everywhere else is a good solve with a rounding error, not
#: a broken one. The failure this must still catch returned CD = -0.54.
VLM_CD_NOISE_FRAC = 0.02


def _vlm_polar(plane, V: float, alphas, mesh) -> tuple[list[float], list[float]]:
    """Inviscid CL/CD at each alpha on a uniformly-spanwise-panelled mesh."""
    spanwise, chordwise = mesh
    cls, cds = [], []
    for a in alphas:
        r = asb.VortexLatticeMethod(
            airplane=plane,
            op_point=asb.OperatingPoint(velocity=V, alpha=float(a)),
            xyz_ref=[0.0, 0.0, 0.0],
            spanwise_resolution=spanwise,
            spanwise_spacing_function=np.linspace,
            chordwise_resolution=chordwise,
        ).run()
        cls.append(float(r["CL"]))
        cds.append(float(r["CD"]))
    return cls, cds


def vlm_induced_check(
    planes: dict, V: float, alphas=(0.0, 1.5, 3.0, 4.5, 6.0, 7.5), meshes=VLM_MESHES
) -> dict:
    """Numeric second opinion on nonplanar induced drag (winglet study,
    MODEL_DETAILS 3.6): fit CD = CD0 + k*CL^2 to an inviscid VLM alpha sweep per
    configuration. LL is the in-loop model; comparing k across {winglet_on,
    winglet_off} checks the induced-drag delta with an independent method.
    (LL was the conservative of the two in the feasibility test.)

    Every configuration carries `reliable` and, when False, `unreliable_reason`.
    The failure mode this guards is not a crash but a plausible-looking number
    (see the ensemble note above), so the guard is the load-bearing part: the
    result is the consensus of `meshes`, per-mesh values are kept under
    `per_mesh` for audit, and an ensemble that cannot agree ships flagged.

    An inviscid solve has no viscous drag, so a mesh is admitted only if its
    polar has the right SHAPE: a positive fit slope, and drag rising with lift
    to within `VLM_CD_NOISE_FRAC`. `cd0_inviscid` is the fit intercept and
    should be ~0 — its magnitude is the residual of a straight line through a
    mildly nonlinear CD(CL^2), and a few 1e-4 is fit noise, not drag.
    """
    out = {}
    for label, plane in planes.items():
        ar = float(plane.b_ref**2 / plane.s_ref)
        per_mesh = []
        for mesh in meshes:
            cls, cds = _vlm_polar(plane, V, alphas, mesh)
            k, cd0 = np.polyfit(np.array(cls) ** 2, np.array(cds), 1)
            per_mesh.append({
                "mesh": list(mesh), "k_induced": float(k), "cd0_inviscid": float(cd0),
                # an inviscid polar that loses drag as it gains lift is not a
                # result to average in — it is a broken solve, so it is dropped.
                # The test is about the SHAPE of the polar (rising slope, drag
                # rising with lift) rather than any single point, so that noise
                # at the lowest-CL point cannot condemn an otherwise clean mesh.
                "physical": bool(
                    k > 0
                    and cds == sorted(cds)
                    and min(cds) > -VLM_CD_NOISE_FRAC * max(cds)
                ),
                "cl": cls, "cd": cds,
            })

        # Consensus: the median is the reference because it survives a single
        # blow-up, which is exactly the failure this ensemble exists for.
        # Everything within TOL of it votes, and the answer is the mean of the
        # votes. A dropped or outvoted mesh is NOT by itself a failure — being
        # outvoted is how the ensemble is supposed to absorb one bad solve.
        usable = [m for m in per_mesh if m["physical"]]
        agree = []
        if usable:
            median = float(np.median([m["k_induced"] for m in usable]))
            agree = [m for m in usable
                     if abs(m["k_induced"] - median) <= VLM_MESH_TOL * abs(median)]
        reasons = []
        averaged = agree
        if len(agree) < VLM_MIN_CONSENSUS:
            reasons.append(
                f"fewer than {VLM_MIN_CONSENSUS} of {len(per_mesh)} meshes agree on "
                "k_induced: " + ", ".join(
                    f"{m['k_induced']:+.4g} at {tuple(m['mesh'])}"
                    f"{'' if m['physical'] else ' (unphysical)'}" for m in per_mesh
                )
            )
            # still report a best guess, so the flagged number can be argued
            # with — but from everything usable, not from a "consensus" of one
            averaged = usable or per_mesh

        k = float(np.mean([m["k_induced"] for m in averaged]))
        entry = {
            "k_induced": k,
            "cd0_inviscid": float(np.mean([m["cd0_inviscid"] for m in averaged])),
            # span efficiency wrt PROJECTED span — e > 1 is the nonplanar payoff
            "e_projected_span": float(1 / (np.pi * ar * k)) if k else None,
            "meshes_in_consensus": [tuple(m["mesh"]) for m in agree],
            "meshes_averaged": [tuple(m["mesh"]) for m in averaged],
            "meshes_dropped_unphysical": [
                tuple(m["mesh"]) for m in per_mesh if not m["physical"]
            ],
            "alphas_deg": [float(a) for a in alphas],
            "per_mesh": per_mesh,
            "reliable": not reasons,
        }
        if reasons:
            entry["unreliable_reason"] = "; ".join(reasons)
        out[label] = entry
    return out


# --- lateral-directional: the yaw axis LL was believed not to have -----------
#
# MODEL_DETAILS 8.4 built the whole directional floor on "LL has no yaw axis".
# On asb 4.2.10 that is measurably false: LiftingLine answers sideslip with the
# right sign and a clean monotonic trend in V-angle. What it does NOT get right
# is the MAGNITUDE — on the 2026-08-05 champion geometry it over-predicts
# Cn_beta by 2.15x at t_dihedral 20 deg, easing to 1.34x at 55 deg. So LL's yaw
# axis is a usable SHAPE and an unusable NUMBER, and this check supplies the
# number the in-loop constraint is calibrated against.
#
# The guard cannot be the induced check's. That one leans on an inviscid polar
# having a shape — drag rising with lift — and a sideslip sweep has no such
# curve to lean on. It leans on SYMMETRY instead, which is both stronger and
# free: an aircraft symmetric about y = 0 must return Cn(-beta) = -Cn(beta)
# exactly, and a healthy VLM does. The champion returns +-0.006482 at +-4 deg to
# every digit it prints. A mesh that breaks antisymmetry has a broken AIC no
# matter how plausible its slope looks — which is the failure mode HANDOFF 0a
# is about, and it is still live: the DV_DEFAULTS geometry at (8, 8) returns
# CL = +123.1 against LiftingLine's 0.52 on the same aeroplane.
#: Sideslip stations. Zero is omitted deliberately — it is identically zero by
#: symmetry, so it costs a solve and constrains nothing.
LAT_BETAS = (-4.0, -2.0, 2.0, 4.0)
#: How far Cn(-b) + Cn(+b) may drift from zero, as a fraction of the sweep's
#: own largest |Cn|. Not zero: the far field is truncated slightly differently
#: on either side of a swept panel. The champion sits at ~1e-9 of this.
LAT_ASYM_TOL = 0.02
#: An inviscid CL above this at cruise alpha is a collapsed AIC, not an
#: aeroplane. Blunt on purpose — the failure it must catch returned 123.1.
LAT_CL_SANE_MAX = 3.0


def _vlm_lateral(plane, V: float, alpha: float, betas, mesh, x_cg: float) -> list[dict]:
    """Inviscid lateral coefficients at each sideslip angle, on one mesh."""
    spanwise, chordwise = mesh
    out = []
    for b in betas:
        r = asb.VortexLatticeMethod(
            airplane=plane,
            op_point=asb.OperatingPoint(velocity=V, alpha=float(alpha), beta=float(b)),
            xyz_ref=[x_cg, 0, 0],
            spanwise_resolution=spanwise,
            spanwise_spacing_function=np.linspace,
            chordwise_resolution=chordwise,
        ).run()
        out.append({k: float(r[k]) for k in ("CL", "CY", "Cl", "Cn")})
    return out


def vlm_directional_check(
    planes: dict, V: float, alpha: float, x_cg: float,
    betas=LAT_BETAS, meshes=VLM_MESHES,
) -> dict:
    """Numeric second opinion on directional stability (MODEL_DETAILS 8.4).

    Per configuration, sweep sideslip and fit the three lateral derivatives per
    degree: `cn_beta` (weathercock — positive is stable), `cl_beta` (dihedral
    effect — negative is stable) and `cy_beta` (side force, negative).

    Same ensemble/majority posture as `vlm_induced_check`, and for the same
    reason: the failure mode is a plausible number rather than a crash. The
    reported value is the consensus of `meshes`, per-mesh values are kept under
    `per_mesh` for audit, and an ensemble that cannot agree ships flagged with
    `reliable = False` rather than silently.

    A mesh is admitted only if it is SYMMETRIC — antisymmetric Cn about zero
    sideslip to `LAT_ASYM_TOL`, with a sane CL. Note that Cn_beta > 0 is NOT an
    admission test: an aircraft that is directionally unstable is a finding this
    must be able to report, not a solve it should throw away.
    """
    # Pair each -b with its +b, ONCE. Without at least one pair the symmetry
    # guard silently degrades to "everything passes", and a guard that quietly
    # stops guarding is worse than one that was never there — so this refuses
    # the sweep rather than returning numbers it cannot vouch for.
    pairs = [
        (i, j) for i, bi in enumerate(betas) for j, bj in enumerate(betas)
        if bi == -bj and bi < 0
    ]
    if not pairs:
        raise ValueError(
            f"betas={tuple(betas)} contains no +/- pair, so the antisymmetry "
            "guard cannot run. Pass symmetric sideslip stations (see LAT_BETAS)."
        )

    out = {}
    for label, plane in planes.items():
        per_mesh = []
        for mesh in meshes:
            rows = _vlm_lateral(plane, V, alpha, betas, mesh, x_cg)
            cn = [r["Cn"] for r in rows]
            slopes = {
                f"{k.lower()}_beta": float(np.polyfit(betas, [r[k] for r in rows], 1)[0])
                for k in ("Cn", "Cl", "CY")
            }
            # Symmetry: broken antisymmetry means the two halves of a symmetric
            # aeroplane did not solve to the same answer, which no amount of
            # slope-fitting can repair.
            scale = max(abs(c) for c in cn) or 1.0
            worst_asym = max(abs(cn[i] + cn[j]) / scale for i, j in pairs)
            per_mesh.append({
                "mesh": list(mesh), **slopes,
                "worst_antisymmetry": float(worst_asym),
                "physical": bool(
                    worst_asym <= LAT_ASYM_TOL
                    and all(abs(r["CL"]) < LAT_CL_SANE_MAX for r in rows)
                ),
                "cn": cn, "cl": [r["Cl"] for r in rows],
                "cy": [r["CY"] for r in rows], "cl_lift": [r["CL"] for r in rows],
            })

        # Consensus on cn_beta — the derivative the floor exists to protect.
        # Median as reference, for the same reason as the induced check: it
        # survives exactly one blow-up, which is the case this guards.
        usable = [m for m in per_mesh if m["physical"]]
        agree = []
        if usable:
            median = float(np.median([m["cn_beta"] for m in usable]))
            agree = [m for m in usable
                     if abs(m["cn_beta"] - median) <= VLM_MESH_TOL * abs(median)]
        reasons = []
        averaged = agree
        if len(agree) < VLM_MIN_CONSENSUS:
            reasons.append(
                f"fewer than {VLM_MIN_CONSENSUS} of {len(per_mesh)} meshes agree on "
                "cn_beta: " + ", ".join(
                    f"{m['cn_beta']:+.4g} at {tuple(m['mesh'])}"
                    f"{'' if m['physical'] else ' (unphysical)'}" for m in per_mesh
                )
            )
            averaged = usable or per_mesh

        entry = {
            k: float(np.mean([m[k] for m in averaged]))
            for k in ("cn_beta", "cl_beta", "cy_beta")
        }
        entry |= {
            # the verdict the declared floor is a stand-in for
            "directionally_stable": bool(entry["cn_beta"] > 0),
            "roll_stable": bool(entry["cl_beta"] < 0),
            "meshes_in_consensus": [tuple(m["mesh"]) for m in agree],
            "meshes_averaged": [tuple(m["mesh"]) for m in averaged],
            "meshes_dropped_unphysical": [
                tuple(m["mesh"]) for m in per_mesh if not m["physical"]
            ],
            "betas_deg": [float(b) for b in betas],
            "alpha_deg": float(alpha),
            "per_mesh": per_mesh,
            "reliable": not reasons,
        }
        if reasons:
            entry["unreliable_reason"] = "; ".join(reasons)
        out[label] = entry
    return out


# --- the pitching moment, which nothing else in this app looks at twice ------
#
# Drag has two cross-checks (`mesh_convergence_check`, `vlm_induced_check`) and
# the lateral derivatives now have one. Cm — and therefore the static margin —
# had NONE, which is backwards: it is the quantity this project already knows is
# its weakest, and the only one that decides whether the aeroplane is flyable.
#
# The 2026-08-05 champions report `static_margin = 0.0646` against a required
# window of [0.08, 0.15], with the local dCm/dCL running -0.0114 → +0.1805 over
# four degrees. The reported margin is a least-squares slope through points
# whose slope changes SIGN. Two very different things produce that, and no
# number from LiftingLine can separate them:
#
#   (a) Cm(alpha) really is that nonlinear on this airframe, or
#   (b) LiftingLine's Cm is noisy at 4 panels per section.
#
# (b) is not hypothetical. FINDINGS §18 is a 4-panel artefact that produced a
# winglet contributing -0.93 N and an L/D of 889. So this asks an independent
# METHOD — the VLM, which shares the library but not the discretization or the
# solution scheme — the same question over the same alpha window, and reports
# whether it sees the sign flip too.
#
# What it is NOT: a verdict. The VLM here is inviscid, so its Cm omits the
# viscous contribution LiftingLine gets from NeuralFoil, and the two will not
# agree in absolute value. The comparable quantity is the SHAPE — whether the
# local slope changes sign inside the window — which is what `sign_consistent`
# reports on each side.


def _vlm_pitch(plane, V: float, alphas, mesh, x_cg: float) -> list[dict]:
    """Inviscid CL/Cm at each alpha, on one mesh."""
    spanwise, chordwise = mesh
    out = []
    for a in alphas:
        r = asb.VortexLatticeMethod(
            airplane=plane,
            op_point=asb.OperatingPoint(velocity=V, alpha=float(a)),
            xyz_ref=[x_cg, 0, 0],
            spanwise_resolution=spanwise,
            spanwise_spacing_function=np.linspace,
            chordwise_resolution=chordwise,
        ).run()
        out.append({"CL": float(r["CL"]), "Cm": float(r["Cm"])})
    return out


def vlm_static_margin_check(
    planes: dict, V: float, alpha_trim: float, x_cg: float, c_ref: float,
    bodies: list[dict] | None = None, meshes=VLM_MESHES,
) -> dict:
    """Second opinion on SM = -dCm/dCL, by an independent method.

    Samples the SAME window the in-loop estimator uses (`SM_ALPHA_OFFSETS`,
    plus `SM_DIAGNOSTIC_OFFSETS` for the nonlinearity diagnostic) and runs it
    through the SAME estimator (`static_margin_from_polar`, including the Munk
    fuselage term when `bodies` is given), so the only difference between this
    number and LiftingLine's is the aerodynamic method.

    Reports `sign_consistent`: False when a local dCm/dCL goes negative inside a
    positive reported margin — the exact pathology `solve.sm_sign_flip` finds on
    the LL side. Agreement between the two is evidence the nonlinearity is the
    AIRFRAME's; disagreement points at the discretization.

    Same ensemble/majority guard as the other VLM checks, admitting a mesh only
    if CL is sane and RISES with alpha. A lifting surface whose lift falls with
    incidence has not solved.
    """
    offsets = sorted(SM_ALPHA_OFFSETS + SM_DIAGNOSTIC_OFFSETS)
    alphas = [alpha_trim + d for d in offsets]
    out = {}
    for label, plane in planes.items():
        per_mesh = []
        for mesh in meshes:
            rows = _vlm_pitch(plane, V, alphas, mesh, x_cg)
            cls = {d: rows[i]["CL"] for i, d in enumerate(offsets)}
            cms = {d: rows[i]["Cm"] for i, d in enumerate(offsets)}
            sm = float(static_margin_from_polar(
                [cls[d] for d in SM_ALPHA_OFFSETS],
                [cms[d] for d in SM_ALPHA_OFFSETS],
                list(SM_ALPHA_OFFSETS), bodies,
                float(plane.s_ref), c_ref,
            ))
            local = [
                {"alpha": float(alphas[i]),
                 "sm_local": -float((cms[offsets[i + 1]] - cms[offsets[i]])
                                    / (cls[offsets[i + 1]] - cls[offsets[i]]))}
                for i in range(len(offsets) - 1)
                # a zero CL step would divide by zero; that mesh is caught by
                # the monotonicity guard below rather than crashing here
                if cls[offsets[i + 1]] != cls[offsets[i]]
            ]
            lifts = [r["CL"] for r in rows]
            per_mesh.append({
                "mesh": list(mesh), "static_margin": sm,
                "sm_local_slopes": local,
                "sign_consistent": bool(
                    sm <= 0 or all(p["sm_local"] >= 0 for p in local)
                ),
                "physical": bool(
                    lifts == sorted(lifts)
                    and len(set(lifts)) == len(lifts)
                    and all(abs(c) < LAT_CL_SANE_MAX for c in lifts)
                ),
                "cl": lifts, "cm": [r["Cm"] for r in rows],
            })

        usable = [m for m in per_mesh if m["physical"]]
        agree = []
        if usable:
            median = float(np.median([m["static_margin"] for m in usable]))
            agree = [m for m in usable
                     if abs(m["static_margin"] - median) <= VLM_MESH_TOL * abs(median)]
        reasons = []
        averaged = agree
        if len(agree) < VLM_MIN_CONSENSUS:
            reasons.append(
                f"fewer than {VLM_MIN_CONSENSUS} of {len(per_mesh)} meshes agree on "
                "static_margin: " + ", ".join(
                    f"{m['static_margin']:+.4g} at {tuple(m['mesh'])}"
                    f"{'' if m['physical'] else ' (unphysical)'}" for m in per_mesh
                )
            )
            averaged = usable or per_mesh

        sm = float(np.mean([m["static_margin"] for m in averaged]))
        entry = {
            "static_margin": sm,
            "x_np_m": x_cg + sm * c_ref,
            # the SHAPE question, which is the comparable one across methods
            "sign_consistent": bool(all(m["sign_consistent"] for m in averaged)),
            "sm_local_slopes": averaged[0]["sm_local_slopes"] if averaged else [],
            "alpha_window_deg": [float(alpha_trim + d) for d in SM_ALPHA_OFFSETS],
            "meshes_in_consensus": [tuple(m["mesh"]) for m in agree],
            "meshes_averaged": [tuple(m["mesh"]) for m in averaged],
            "meshes_dropped_unphysical": [
                tuple(m["mesh"]) for m in per_mesh if not m["physical"]
            ],
            "per_mesh": per_mesh,
            "reliable": not reasons,
        }
        if reasons:
            entry["unreliable_reason"] = "; ".join(reasons)
        out[label] = entry
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
    c_s = []
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
