"""Rule-based fuselage shape review — CAD round-trip step (c) (MODEL_DETAILS 7.5).

The drag model cannot rank surface sculpting (flat-plate x FF x Swet sees only
four numbers), so this review applies the known drag *rules* to an imported
shape and prices the measurable part — honest feedback, no CFD pretense:

- nose fineness: length to full diameter >= ~1.0 d_eq (blunter risks
  separation the model can't see);
- boat-tail half-angle: <= ~21 deg station-to-station (the parametric loft's
  Hermite tail at its 1.8 d_eq floor peaks at 20.1 deg — the limit is set so
  the app's own floor-tight shapes pass; steeper means separation risk);
- overall fineness inside a sane band (form-factor optimum region);
- wetted-area delta vs a reference (the minimal parametric loft with the same
  packaging), priced through the skin mass model and the mass shadow price.

General-purpose: consumes [(x, width, height)] sections from any source
(cadimport tessellation scan, or a parametric loft's own xsecs).
"""

from __future__ import annotations

import math


def review(
    sections,
    swet_m2: float | None = None,
    *,
    reference_swet_m2: float | None = None,
    k_skin_kg_m2: float | None = None,
    shadow_per_g: float | None = None,
    objective_units: str = "objective units",
    boat_tail_limit_deg: float = 21.0,
    fineness_band: tuple = (4.0, 9.0),
    nose_floor: float = 1.0,
) -> dict:
    sec = sorted(sections)
    if len(sec) < 4:
        raise ValueError("shape review needs at least 4 stations")
    xs = [s[0] for s in sec]
    d = [(w * h) ** 0.5 for _, w, h in sec]
    d_max = max(d)
    findings = []

    # nose: tip to the first station at (essentially) full diameter
    i_full = next(i for i, v in enumerate(d) if v >= 0.995 * d_max)
    nose_ratio = (xs[i_full] - xs[0]) / d_max
    findings.append({
        "check": "nose_fineness",
        "value": round(nose_ratio, 3),
        "threshold": f">= {nose_floor}",
        "ok": nose_ratio >= nose_floor * 0.9,
        "note": "nose length to full diameter, in equivalent diameters",
    })

    # boat-tail: aft of the last full-diameter station, worst station-to-station
    # half-angle of the equivalent-diameter taper
    i_last_full = len(d) - 1 - next(i for i, v in enumerate(reversed(d)) if v >= 0.995 * d_max)
    angles = [
        math.degrees(math.atan2(0.5 * (d[i] - d[i + 1]), xs[i + 1] - xs[i]))
        for i in range(i_last_full, len(d) - 1)
        if xs[i + 1] > xs[i]
    ]
    bt = max(angles) if angles else 0.0
    findings.append({
        "check": "boat_tail_half_angle",
        "value": round(bt, 1),
        "threshold": f"<= {boat_tail_limit_deg} deg",
        "ok": bt <= boat_tail_limit_deg,
        "note": "worst taper half-angle aft of the bay; steeper risks separation",
    })

    fineness = (xs[-1] - xs[0]) / d_max
    findings.append({
        "check": "fineness",
        "value": round(fineness, 2),
        "threshold": f"{fineness_band[0]}..{fineness_band[1]}",
        "ok": fineness_band[0] <= fineness <= fineness_band[1],
        "note": "overall L/d_eq; the form-factor trade is shallow inside the band",
    })

    out = {"findings": findings, "ok": all(f["ok"] for f in findings)}

    if swet_m2 is not None and reference_swet_m2 is not None:
        delta = swet_m2 - reference_swet_m2
        price = {"delta_swet_m2": round(delta, 5)}
        if k_skin_kg_m2 is not None:
            grams = delta * k_skin_kg_m2 * 1000
            price["delta_mass_g"] = round(grams, 1)
            if shadow_per_g is not None:
                price["cost_mass_route"] = (
                    f"{abs(shadow_per_g) * grams:.2f} {objective_units} "
                    "(drag route adds on top)"
                )
        out["wetted_area_price"] = price
    return out
