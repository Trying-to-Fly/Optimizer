"""Build document — what a person needs at the bench, not at the design desk.

`report.html` answers "is this design any good". `design_brief.md` answers "what
do I design around". These files answer "what do I cut, and what must I hit":
spar stock and lengths, hinge lines, edge curves, and the one number a model
aircraft actually lives or dies by — where the CG has to end up.

Everything geometric is read off the SAME airplane object the solver analysed,
via `asb.Wing`'s own placement functions, so the build document cannot drift
from the thing that was evaluated.

General-purpose rule (EXECUTION_PLAN §3): this module derives only what the
framework can see for any aircraft — surfaces, edges, hinges, masses, balance.
Anything architecture-specific (spars, stock lists, print parts, control throws)
comes from the aircraft module's optional hook

    manufacturing(dv) -> dict[str, dict | list[dict]]

mapping section titles to either {label: value} rows or a list of uniform dicts.
A list is rendered as a table AND written beside the document as its own CSV, so
a cut list can go straight into a spreadsheet. Aircraft without the hook still
get every generic section.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np

from .. import types


def _airfoil_name(xsec) -> str:
    return getattr(getattr(xsec, "airfoil", None), "name", None) or "unknown"


def _le_te(wing, i) -> tuple[np.ndarray, np.ndarray]:
    le = np.array(wing._compute_xyz_le_of_WingXSec(i), dtype=float).flatten()
    te = np.array(wing._compute_xyz_te_of_WingXSec(i), dtype=float).flatten()
    return le, te


def edges(airplane) -> list[dict]:
    """Leading- and trailing-edge polylines, one ordered point list per surface.

    The loft between stations is STRAIGHT — that is the geometry the solver
    analysed, not a simplification made here — so these points are the complete
    edge, not a sampling of a curve. Sketch them in order and connect with lines.

    Each row also carries the running span station and the dihedral of the
    segment that follows, which is what a build jig is actually set from.
    """
    rows = []
    for wing in airplane.wings:
        pts = [_le_te(wing, i) for i in range(len(wing.xsecs))]
        run = 0.0
        for i, (le, te) in enumerate(pts):
            if i > 0:
                prev_le = pts[i - 1][0]
                run += float(np.linalg.norm(le[1:] - prev_le[1:]))  # y-z arc length
            nxt = pts[i + 1][0] if i + 1 < len(pts) else None
            dihedral = ""
            if nxt is not None:
                dy, dz = float(nxt[1] - le[1]), float(nxt[2] - le[2])
                dihedral = round(float(np.degrees(np.arctan2(dz, dy))), 3)
            for edge, p in (("LE", le), ("TE", te)):
                rows.append({
                    "surface": wing.name,
                    "edge": edge,
                    "station": i,
                    "x_m": round(float(p[0]), 6),
                    "y_m": round(float(p[1]), 6),
                    "z_m": round(float(p[2]), 6),
                    "chord_m": round(float(wing.xsecs[i].chord), 6),
                    "span_station_m": round(run, 6),
                    "next_segment_dihedral_deg": dihedral,
                    "symmetric": bool(getattr(wing, "symmetric", False)),
                })
    return rows


def hinges(airplane) -> list[dict]:
    """Hinge lines for every control surface the aircraft declared.

    A control surface attaches to a section and governs the panel OUTBOARD of
    it, so each row is one panel: the hinge line runs from that station to the
    next. `hinge_frac` is a chord fraction, so on a tapered panel the hinge line
    is not perpendicular to the root — the reported endpoints are the truth.
    """
    rows = []
    for wing in airplane.wings:
        for i, xsec in enumerate(wing.xsecs[:-1]):
            for cs in getattr(xsec, "control_surfaces", None) or []:
                frac = float(cs.hinge_point)
                ends = []
                for j in (i, i + 1):
                    le, te = _le_te(wing, j)
                    ends.append((le + frac * (te - le), float(wing.xsecs[j].chord)))
                (p_in, c_in), (p_out, c_out) = ends
                rows.append({
                    "surface": wing.name,
                    "control": cs.name,
                    "from_station": i,
                    "to_station": i + 1,
                    "hinge_frac_chord": round(frac, 4),
                    "x_in_m": round(float(p_in[0]), 6),
                    "y_in_m": round(float(p_in[1]), 6),
                    "z_in_m": round(float(p_in[2]), 6),
                    "x_out_m": round(float(p_out[0]), 6),
                    "y_out_m": round(float(p_out[1]), 6),
                    "z_out_m": round(float(p_out[2]), 6),
                    "control_chord_in_m": round((1 - frac) * c_in, 6),
                    "control_chord_out_m": round((1 - frac) * c_out, 6),
                    "hinge_length_m": round(float(np.linalg.norm(p_out - p_in)), 6),
                    "symmetric_pair": bool(getattr(cs, "symmetric", False)),
                })
    return rows


def surfaces(airplane) -> list[dict]:
    """Every surface the aircraft actually built, straight off the airplane.

    Deliberately not read from `run.json`'s geometry summary: that summary is
    produced from a separate build and has been seen to omit a surface the
    analysed airplane carries (the winglet). A build document that lists fewer
    parts than exist is worse than no build document.
    """
    rows = []
    for wing in airplane.wings:
        names = []
        for xsec in wing.xsecs:
            n = _airfoil_name(xsec)
            if not names or names[-1] != n:
                names.append(n)
        rows.append({
            "surface": wing.name,
            "airfoil": " -> ".join(names),
            "span_mm": round(float(wing.span()) * 1000, 1),
            "area_m2": round(float(wing.area()), 5),
            "root_chord_mm": round(float(wing.xsecs[0].chord) * 1000, 1),
            "tip_chord_mm": round(float(wing.xsecs[-1].chord) * 1000, 1),
            "sections": len(wing.xsecs),
            "mirrored": bool(getattr(wing, "symmetric", False)),
        })
    return rows


def balance(result: types.RunResult, airplane) -> dict | None:
    """Where the CG must land, and how much room there is.

    Static margin is defined against `airplane.c_ref` in `solve`, so the window
    is computed against the same reference — a mean chord taken any other way
    would silently move the target.
    """
    x_np = (result.diagnostics or {}).get("neutral_point_m")
    x_cg = (result.masses or {}).get("x_cg_m")
    if x_np is None or x_cg is None:
        return None
    c_ref = float(airplane.c_ref)
    out = {
        "x_cg_m": float(x_cg),
        "x_np_m": float(x_np),
        "c_ref_m": c_ref,
        "static_margin": (result.constraints or {}).get("static_margin"),
    }
    sm_range = (result.constraints or {}).get("static_margin_range")
    if sm_range:
        lo, hi = float(sm_range[0]), float(sm_range[1])
        # SM = (x_np - x_cg) / c_ref, so a BIGGER margin is a MORE FORWARD CG
        out["cg_aft_limit_m"] = x_np - lo * c_ref
        out["cg_fwd_limit_m"] = x_np - hi * c_ref
        out["cg_window_mm"] = (hi - lo) * c_ref * 1000
        out["sm_range"] = [lo, hi]
    return out


# --------------------------------------------------------------------------- render

def _nz(v: float) -> float:
    """Kill negative zero. A build doc printing "-0.0 g" reads as a bug."""
    return v + 0.0 if v else 0.0


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{_nz(v):,.4g}"
    return str(v)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _table(rows: list[dict]) -> list[str]:
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_fmt(row.get(c, "")) for c in cols) + " |")
    return out + [""]


def render(result: types.RunResult, airplane, aircraft=None) -> str:
    """The build document as markdown."""
    return _build(result, airplane, aircraft)[0]


def _build(result: types.RunResult, airplane, aircraft=None) -> tuple[str, dict]:
    perf = result.performance or {}
    champ = (perf.get("optimization") or {}).get("champion") or {}
    dv = champ.get("dv")
    units = perf.get("objective_units", "")

    L = [
        f"# Build document — {result.aircraft} / {result.mission}",
        "",
        f"From the `{result.created}` run. Every dimension here is read off the",
        "same geometry the solver analysed.",
        "",
        "**Datum and units.** Millimetres unless stated. Aircraft frame: **+x aft**",
        "from the nose datum, **+y starboard**, **+z up**. Surfaces marked",
        "symmetric are given as the STARBOARD half only — mirror about y = 0.",
        "",
    ]

    bal = balance(result, airplane)
    if bal:
        L += ["## 1. Balance — get this right first", ""]
        L += [f"- **CG target:** **{bal['x_cg_m'] * 1000:.1f} mm** aft of the nose datum"]
        if "cg_fwd_limit_m" in bal:
            lo, hi = bal["sm_range"]
            L += [
                f"- **Allowable CG range:** {bal['cg_fwd_limit_m'] * 1000:.1f} mm "
                f"(forward, {hi:.0%} margin) to {bal['cg_aft_limit_m'] * 1000:.1f} mm "
                f"(aft, {lo:.0%} margin) — a **{bal['cg_window_mm']:.0f} mm** window",
                f"- **Neutral point:** {bal['x_np_m'] * 1000:.1f} mm; reference chord "
                f"{bal['c_ref_m'] * 1000:.1f} mm",
            ]
        sm = bal.get("static_margin")
        if sm is not None:
            L += [f"- **As-designed static margin:** {sm:.4f}"]
        ballast = ((result.masses or {}).get("components") or {}).get("nose_ballast")
        if ballast is not None:
            L += [f"- **Nose ballast in this design:** {abs(ballast) * 1000:.0f} g"]
        if "cg_fwd_limit_m" not in bal:
            L += ["- **CG limits: not available.** This run predates the static-margin",
                  "  range being recorded in `run.json`. Re-solve to get the window."]
        L += ["", "Aft of the aft limit the aircraft is unflyable, not merely twitchy.",
              "Weigh and balance before the first flight, not after.", ""]

    surf = surfaces(airplane)
    if surf:
        L += ["## 2. Surfaces", ""]
        L += _table(surf)
        L += ["Every surface the solver analysed, including any the report's summary",
              "table omits. `mirrored` surfaces are given as the starboard half.",
              "",
              "Section-by-section loft (leading/trailing edge points, chord, twist,",
              "airfoil) is in `../geometry/stations.csv`; the placed airfoil outlines",
              "are in `../geometry/sections_3d.csv`. Edge polylines are in",
              "`edges.csv` beside this document — the loft between stations is",
              "STRAIGHT, so those points are the whole edge, not a sampling.", ""]

    hinge_rows = hinges(airplane)
    if hinge_rows:
        L += ["## 3. Control surfaces", ""]
        for r in hinge_rows:
            L += [
                f"- **{r['control']}** on `{r['surface']}`, station {r['from_station']}"
                f"→{r['to_station']}: hinge at **{r['hinge_frac_chord']:.0%} chord**, "
                f"length {r['hinge_length_m'] * 1000:.1f} mm, control chord "
                f"{r['control_chord_in_m'] * 1000:.1f} → "
                f"{r['control_chord_out_m'] * 1000:.1f} mm"
                + (" (mirrored pair)" if r["symmetric_pair"] else ""),
            ]
        L += ["", "The hinge is a constant CHORD FRACTION, so on a tapered panel the",
              "hinge line is not square to the root. Endpoints are in `hinges.csv`.", ""]

    comps = (result.masses or {}).get("components") or {}
    if comps:
        auw = (result.masses or {}).get("auw_kg") or sum(comps.values())
        L += ["## 4. Mass budget", "", f"Target all-up weight **{auw * 1000:.0f} g**.",
              "", "| component | mass (g) | share |", "| --- | --- | --- |"]
        for name, kg in sorted(comps.items(), key=lambda kv: -abs(kv[1])):
            L.append(f"| {name} | {_nz(kg * 1000):.1f} | {_nz(kg / auw * 100):.1f}% |")
        L += ["", f"| **total** | **{auw * 1000:.0f}** | |", ""]
        shadow = ((perf.get("optimization") or {}).get("shadow_price_obj_per_gram"))
        if shadow:
            L += [f"Every 100 g over target costs about **{abs(shadow) * 100:.1f} {units}**.", ""]

    tables: dict[str, list[dict]] = {}
    hook = getattr(aircraft, "manufacturing", None)
    if hook is not None:
        auw = (result.masses or {}).get("auw_kg")
        for n, (section, body) in enumerate(hook(dv, auw_kg=auw).items(), start=5):
            L += [f"## {n}. {section}", ""]
            if isinstance(body, list):
                if not body:
                    continue
                tables[section] = body
                L += _table(body)
                L += [f"Also written as `{_slug(section)}.csv`.", ""]
            else:
                L += [f"- **{label}:** {_fmt(value)}" for label, value in body.items()]
                L += [""]

    L += ["---", "",
          "Generated by `planeopt build`. Re-run it after any re-solve — every",
          "number above moves with the design.", ""]
    return "\n".join(L), tables


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write(result: types.RunResult, airplane, aircraft, run_dir: Path) -> Path:
    """Write the build document + its CSVs into `run_dir/manufacturing/`."""
    out = Path(run_dir) / "manufacturing"
    out.mkdir(parents=True, exist_ok=True)
    doc, tables = _build(result, airplane, aircraft)
    (out / "BUILD.md").write_text(doc, encoding="utf-8")
    _write_csv(out / "edges.csv", edges(airplane))
    _write_csv(out / "hinges.csv", hinges(airplane))
    _write_csv(out / "surfaces.csv", surfaces(airplane))
    for section, rows in tables.items():
        _write_csv(out / f"{_slug(section)}.csv", rows)
    return out
