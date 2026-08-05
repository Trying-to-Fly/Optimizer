"""Geometry helpers shared by aircraft architecture mappings.

The mapping itself (design vector -> asb.Airplane) lives in each aircraft's config
module — the framework never assumes an architecture (OPTIMIZATION_CONCEPT.md scope).
This module holds reusable, symbolic-safe helpers only.
"""

from __future__ import annotations

import math

import aerosandbox as asb
import aerosandbox.numpy as anp


def smooth_floor(x, floor: float = 0.0, tau: float = 1e-3):
    """`max(x, floor)`, but differentiable and finite on both sides.

    A dimension the optimizer does not own directly — an exposed boom length, a
    clearance, a gap — is only kept positive by a nonlinear constraint, and an
    interior-point method reaches the solution through points that violate those.
    A length that goes negative on the way then produces a negative Reynolds
    number, `(-Re)**0.2` is NaN, and one NaN in a constraint row poisons the
    solve rather than merely rejecting the point (HANDOFF issue 3: 52 such
    warnings, all inside the pusher solve, at row 72 of `g`).

    The hyperbola `floor + ((x-f) + sqrt((x-f)^2 + tau^2)) / 2` is the standard
    smooth hinge: strictly above `floor`, exact to within tau^2/(4(x-f)) once
    clear of it, and with a bounded derivative through it. `tau` is a LENGTH in
    the same units as x — 1 mm by default, a hundredth of the 100 mm boom
    clearance it sits under, where it costs 2.5 um. No feasible design feels it.
    """
    d = x - floor
    return floor + 0.5 * (d + anp.sqrt(d * d + tau * tau))


def superellipse_chords(etas, c_root, taper, fullness):
    """Chord at each arc-fraction station on one smooth two-parameter family.

        c(eta) = c_root * [lam + (1 - lam) * (1 - eta^a)^(1/a)]

    `taper` (lam) is the tip/root chord ratio and `fullness` (a) sets how the
    chord is distributed between them. The family is chosen because its named
    members are exact rather than approximate:

        lam = 1          constant chord — a plain rectangular wing
        a   = 1          straight taper — the classic trapezoid
        a   = 2          a true ellipse
        a   > 2          fuller mid-span, chord held out then dropped near the tip

    so "straight wing" remains reachable as a point of the continuous family
    instead of a separate discrete case. Two variables replace the three
    independent panel chord ratios they supersede, and the equal-width panel
    breaks they implied disappear: stations become a discretization choice, not
    a design choice.

    `etas` must be sorted with etas[0] == 0 (root) and etas[-1] == 1 (tip).
    Those two are returned analytically — c(0) = c_root and c(1) = lam*c_root
    for EVERY a, so their derivative with respect to `fullness` is exactly
    zero. Evaluating them symbolically instead would form 0^(1/a) and log(0),
    whose derivatives are NaN and poison the whole Jacobian. Interior stations
    are strictly inside (0, 1) and safe. This is the same endpoint rule the
    dihedral curve needs (MODEL_DETAILS section 9).
    """
    chords = [c_root]
    for eta in etas[1:-1]:
        g = (1 - eta**fullness) ** (1 / fullness)
        chords.append(c_root * (taper + (1 - taper) * g))
    chords.append(c_root * taper)
    return chords


def station_grid(eta_break, n_inner: int = 2, n_outer: int = 2) -> list:
    """Arc-fraction stations root -> tip, with a station landing exactly on the
    break so a piecewise dihedral needs no branching on a design-variable value.

    `eta_break` may itself be a design variable: only the fixed sub-fractions
    go through math.sin, so the returned stations stay symbolic-safe. Its
    bounds must keep it strictly inside (0, 1) — every interior station is then
    strictly inside too, which is what superellipse_chords requires.

    The count is a fidelity knob, not a design choice, and it is deliberately
    left at the panel count the four-panel wing used: these stations become
    asb.WingXSec sections, each of which LiftingLine subdivides further, so
    adding stations grows the CasADi graph and the ~14.5 GB solve peak with it
    (memory.py). Chord resolution therefore costs RAM and buys nothing once the
    curve is resolved.

    Outer stations are clustered toward the tip (sine spacing), which is where a
    superellipse does all its curving — a uniform grid spends its stations on
    the flat part and chops the tip off with one long straight segment.
    """
    inner = [eta_break * j / n_inner for j in range(n_inner)]
    span = 1.0 - eta_break
    outer = [eta_break + span * math.sin(math.pi / 2 * k / n_outer) for k in range(n_outer)]
    return inner + outer + [1.0]


def le_offsets(chords, shear):
    """Streamwise LE offset per station for a chosen sweep convention.

        x_le(eta) = shear * (c_root - c(eta))

    One variable spans every straight-edge planform the user asked to be able
    to choose between, as interior points rather than as a discrete menu:

        shear = 0      straight leading edge (all chord change on the TE)
        shear = 0.25   straight quarter-chord line
        shear = 1      straight trailing edge

    Anything between is a valid intermediate, so the optimizer picks the
    convention itself instead of being handed one.
    """
    return [shear * (chords[0] - c) for c in chords]


def panel_areas(widths, chords):
    """Trapezoid area of each panel from its width and bounding chords."""
    return [w * (chords[k] + chords[k + 1]) / 2 for k, w in enumerate(widths)]


def mac_and_ac(widths, chords, le_x):
    """(MAC, quarter-chord x of the area-weighted AC) for a piecewise-linear
    half wing, exact for the trapezoids the geometry is actually built from.

    Needed the moment the leading edge stops being straight: with a swept or
    sheared planform the AC no longer sits a quarter of the root chord behind
    the root LE, so a tail placed off the root LE would collect free moment arm
    the boom-length accounting never pays for. Symbolic-safe — no branching.

    Per panel, with chord and LE station both linear in the spanwise
    coordinate: integral c ds = w(c0+c1)/2, integral c^2 ds = w(c0^2+c0c1+c1^2)/3,
    and integral x_le c ds = w(2x0c0 + x0c1 + x1c0 + 2x1c1)/6.
    """
    area = c2 = xc = 0
    for k, w in enumerate(widths):
        c0, c1 = chords[k], chords[k + 1]
        x0, x1 = le_x[k], le_x[k + 1]
        area = area + w * (c0 + c1) / 2
        c2 = c2 + w * (c0**2 + c0 * c1 + c1**2) / 3
        xc = xc + w * (2 * x0 * c0 + x0 * c1 + x1 * c0 + 2 * x1 * c1) / 6
    mac = c2 / area
    return mac, (xc + 0.25 * c2) / area


def _airfoils(wing: asb.Wing) -> str:
    """The airfoil(s) a surface actually carries, root to tip.

    Read off the built geometry rather than off the aircraft's declared
    attribute: the airfoil is a discrete outer-loop candidate (MODEL_DETAILS
    6.3), so what the report must state is what this run FLEW, which the
    airplane object knows and a config constant can drift from. A surface that
    changes section along the span reports the whole progression.
    """
    names = []
    for xsec in wing.xsecs:
        name = getattr(getattr(xsec, "airfoil", None), "name", None) or "unknown"
        if not names or names[-1] != name:
            names.append(name)
    return " -> ".join(names)


def summarize(airplane: asb.Airplane) -> dict:
    """Geometry summary block for reports (floats only — call on numeric geometry)."""
    wing = airplane.wings[0]
    out = {
        "name": airplane.name,
        "span_m": float(wing.span()),
        "span_projected_m": float(airplane.b_ref),  # front-view y-span (the capped one)
        "area_m2": float(wing.area()),
        "aspect_ratio": float(wing.aspect_ratio()),
        "mean_chord_m": float(wing.area() / wing.span()),
        "n_wings": len(airplane.wings),
        # per-surface dims, architecture-agnostic (span() is front-view arc
        # length, so a vertical fin reports its height here)
        "surfaces": {
            w.name: {
                "airfoil": _airfoils(w),
                "span_m": round(float(w.span()), 4),
                "area_m2": round(float(w.area()), 5),
                "root_chord_m": round(float(w.xsecs[0].chord), 4),
                "tip_chord_m": round(float(w.xsecs[-1].chord), 4),
            }
            for w in airplane.wings
        },
    }
    wl = next((w for w in airplane.wings if w.name == "winglet"), None)
    if wl is not None:
        r0, r1 = wl.xsecs[0], wl.xsecs[-1]
        dy = float(r1.xyz_le[1] - r0.xyz_le[1])
        dz = float(r1.xyz_le[2] - r0.xyz_le[2])
        out["winglet"] = {
            "length_m": float((dy**2 + dz**2) ** 0.5),
            "cant_deg": float(__import__("math").degrees(__import__("math").atan2(dz, dy))),
            "root_chord_m": float(r0.chord),
            "tip_chord_m": float(r1.chord),
            "toe_deg": float(r0.twist),
        }
        out["span_projected_m"] += 2 * dy  # cap applies winglet-inclusive
    return out
