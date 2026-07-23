"""Design brief — step (a) of the CAD round-trip workflow (MODEL_DETAILS 7.5).

Renders a dimensioned, designer-facing markdown brief from a completed run:
what to design around (packaging floors, length budgets, interfaces, balance
windows) and what deviations cost in objective units.

General-purpose rule: this module renders only DECLARED data. Everything
aircraft-specific comes from the aircraft module's optional hook

    design_brief(dv, shadow_per_g=None) -> dict[str, dict[str, str | float]]

mapping section titles to ordered {label: value} rows. Aircraft without the
hook still get the generic header (champion state + shadow prices).
"""

from __future__ import annotations

from .. import types


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.4g}"
    return str(v)


def render(result: types.RunResult, aircraft) -> str:
    perf = result.performance
    opt = perf.get("optimization") or {}
    champ = opt.get("champion") or {}
    dv = champ.get("dv")
    shadow = opt.get("shadow_price_obj_per_gram")
    units = perf.get("objective_units") or result.diagnostics.get("objective_units", "")

    lines = [
        f"# Design brief — {result.aircraft} / {result.mission}",
        "",
        f"Generated from `{result.created}` run artifacts. Numbers below are the",
        "model's optimum and the constraints that bound it — design around them,",
        "and use the prices to judge deviations.",
        "",
    ]
    if champ:
        lines += [
            f"**Champion:** {champ['objective_value']:.1f} {units} at "
            f"V = {champ['V_ms']:.1f} m/s, AUW {champ['auw_kg']:.3f} kg, "
            f"static margin {champ.get('static_margin', float('nan')):.3f}.",
            "",
        ]
    if shadow is not None:
        lines += [
            f"**Mass price:** {abs(shadow) * 100:.2f} {units} per 100 g added "
            "anywhere on the aircraft (from the champion re-solve). Any wetted-area",
            "or structure choice can be converted through this.",
            "",
        ]

    hook = getattr(aircraft, "design_brief", None)
    if hook is not None:
        for section, rows in hook(dv, shadow_per_g=shadow).items():
            lines.append(f"## {section}")
            lines.append("")
            for label, value in rows.items():
                lines.append(f"- **{label}:** {_fmt(value)}")
            lines.append("")

    lines += [
        "---",
        "",
        "Import the finished CAD as .STEP (`planeopt` CAD round-trip): the app",
        "verifies packaging, reviews the shape against drag rules, prices the",
        "wetted-area delta, and re-optimizes the aircraft around it.",
        "",
    ]
    return "\n".join(lines)
