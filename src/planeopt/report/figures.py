"""Diagnostic figures for the champion report, saved to <run>/figures/*.png.

The HTML renderer embeds anything in that directory as base64 — figure modules
stay decoupled from templating.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def power_curves(sweep: list[dict], mission, objective, out_dir: Path) -> None:
    pts = [s for s in sweep if "infeasible" not in s]
    if not pts:
        return
    V = [s["V_ms"] for s in pts]

    fig, ax = plt.subplots(1, 3, figsize=(12, 3.4))
    ax[0].plot(V, [s["P_elec_w"] for s in pts], "o-", ms=3)
    ax[0].set(xlabel="V (m/s)", ylabel="P_elec (W)", title="Power required")
    ax[1].plot(V, [s["L_over_D"] for s in pts], "o-", ms=3)
    ax[1].set(xlabel="V (m/s)", ylabel="L/D", title="Trimmed L/D")
    if any("objective_value" in s for s in pts):
        ax[2].plot(V, [s.get("objective_value") for s in pts], "o-", ms=3)
        ax[2].set(xlabel="V (m/s)", ylabel=objective.units, title=f"{objective.name} vs V")
    for a in ax:
        a.axvline(mission.v_min_ms, color="r", ls="--", lw=1, alpha=0.6)
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "power_curves.png", dpi=110)
    plt.close(fig)


def flatness_plot(flat: list[dict], champion: dict, out_dir: Path) -> None:
    pts = [f for f in flat if f["objective_value"] is not None]
    if not pts:
        return
    fig, ax = plt.subplots(figsize=(5, 3.4))
    ax.plot([f["span"] for f in pts], [f["objective_value"] for f in pts], "o-", ms=4)
    ax.axvline(champion["dv"]["span"], color="g", ls="--", lw=1, alpha=0.7)
    ax.set(xlabel="span (m), all else re-optimized", ylabel="objective",
           title="Flatness of the optimum")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "flatness.png", dpi=110)
    plt.close(fig)


def _wing_outline(wing):
    """Top-view LE/TE polyline (y, x) pairs for one wing, both halves."""
    ys, les, tes = [], [], []
    for xs in wing.xsecs:
        ys.append(xs.xyz_le[1])
        les.append(xs.xyz_le[0])
        tes.append(xs.xyz_le[0] + xs.chord)
    if wing.symmetric:
        ys = [-y for y in reversed(ys)] + ys
        les = list(reversed(les)) + les
        tes = list(reversed(tes)) + tes
    return ys, les, tes


def _front_outline(wing):
    """Front-view (y, z) dihedral polyline."""
    ys = [xs.xyz_le[1] for xs in wing.xsecs]
    zs = [xs.xyz_le[2] for xs in wing.xsecs]
    if wing.symmetric:
        ys = [-y for y in reversed(ys)] + ys
        zs = list(reversed(zs)) + zs
    return ys, zs


def planform_compare(planes: dict, out_dir: Path, fname="planform_compare.png") -> None:
    """Overlay top-view planforms + front-view dihedral for named airplanes.

    planes: {label: asb.Airplane}. The report's 'what actually changed' figure.
    """
    fig, (ax_top, ax_front) = plt.subplots(
        2, 1, figsize=(9, 6.5), height_ratios=[3, 1], sharex=True
    )
    colors = plt.cm.tab10.colors
    for i, (label, plane) in enumerate(planes.items()):
        wing = plane.wings[0]
        ys, les, tes = _wing_outline(wing)
        c = colors[i % 10]
        ax_top.plot(ys, les, "-", color=c, lw=1.6, label=label)
        ax_top.plot(ys, tes, "-", color=c, lw=1.6)
        ax_top.plot([ys[0]] * 2, [les[0], tes[0]], "-", color=c, lw=1.6)
        ax_top.plot([ys[-1]] * 2, [les[-1], tes[-1]], "-", color=c, lw=1.6)
        yf, zf = _front_outline(wing)
        ax_front.plot(yf, zf, "-", color=c, lw=1.6)
    ax_top.invert_yaxis()  # x aft-positive: draw LE up
    ax_top.set(ylabel="x (m)", title="Wing planform (top view)")
    ax_top.legend(fontsize=8)
    ax_top.set_aspect("equal")
    ax_front.set(xlabel="y (m)", ylabel="z (m)", title="Dihedral (front view)")
    ax_front.set_aspect("equal")
    for a in (ax_top, ax_front):
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / fname, dpi=110)
    plt.close(fig)


def three_view(plane, out_dir: Path, fname="three_view.png") -> None:
    """AeroSandbox shaded three-view of the (numeric) airplane."""
    import matplotlib.pyplot as _plt

    plane.draw_three_view(show=False)
    fig = _plt.gcf()
    fig.savefig(out_dir / fname, dpi=110)
    _plt.close(fig)


def stall_spanwise(stall: dict, out_dir: Path) -> None:
    """Spanwise cl/clmax at the stall condition — shows WHERE the wing stalls."""
    if "stations_y" not in stall:
        return
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(stall["stations_y"], stall["ratios_at_stall"], "o-", ms=4)
    ax.axhline(1.0, color="r", ls="--", lw=1)
    ax.axvline(stall["critical_y"], color="orange", ls=":", lw=1.5,
               label=f"critical @ y={stall['critical_y']:.2f} m")
    ax.set(xlabel="y (m)", ylabel="cl / cl_max",
           title=f"Section loading at stall (V={stall['v_stall_ms']:.1f} m/s)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "stall_spanwise.png", dpi=110)
    plt.close(fig)
