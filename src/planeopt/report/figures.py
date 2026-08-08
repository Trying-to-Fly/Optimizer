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


#: Figure furniture, in inches. Explicit because the axes are placed by hand:
#: both views are TRUE SCALE, and a wing is far wider than it is deep, so the
#: height each one needs is a property of the aeroplane rather than a constant.
_FIG_W_IN = 9.0
_PAD_LEFT_IN = 0.75      # y label + tick labels
_PAD_RIGHT_IN = 0.25
_PAD_TOP_IN = 0.40       # the top view's title
_PAD_GAP_IN = 0.60       # gap between the views + the front view's title
_PAD_BOTTOM_IN = 0.55    # x label + tick labels

#: The front view's floor, in inches.
#:
#: Its data is a few centimetres of dihedral across two metres of span — about
#: 1.5% — so a box at true aspect is a sliver roughly 30 px tall, and the two y
#: tick labels it prints do not fit in it. They OVERLAPPED, which is how this
#: was found. The floor keeps the box readable; `adjustable="datalim"` then
#: widens the z limits to match it, so the extra room appears as margin above
#: and below the aeroplane and the dihedral angle stays true.
_FRONT_MIN_H_IN = 1.15

#: The top view's clamp, for aircraft this figure has never seen. A very short
#: span with a deep chord would otherwise ask for a metre-tall figure.
_TOP_MIN_H_IN, _TOP_MAX_H_IN = 1.0, 4.5


def planform_compare(planes: dict, out_dir: Path, fname="planform_compare.png") -> None:
    """Overlay top-view planforms + front-view dihedral for named airplanes.

    planes: {label: asb.Airplane}. The report's 'what actually changed' figure.

    Both views are drawn to TRUE SCALE, which is the whole point of the figure —
    a planform stretched to fill a box is a picture of a different wing. What
    that costs is that the figure's proportions are the aeroplane's, so the axes
    are placed explicitly from the data extents rather than by `tight_layout`.
    Sizing them any other way puts the mismatch somewhere: as blank paper when
    the box is too tall, or as collided tick labels when it is too short. Both
    were present before this was worked out.
    """
    outlines = []
    for label, plane in planes.items():
        wing = plane.wings[0]
        outlines.append((label, _wing_outline(wing), _front_outline(wing)))

    span = max(
        (max(o[1][0]) - min(o[1][0]) for o in outlines if o[1][0]), default=1.0
    ) or 1.0
    chord_extent = max(
        (max(o[1][2]) - min(o[1][1]) for o in outlines if o[1][1]), default=0.1
    )
    dihedral_extent = max(
        (max(o[2][1]) - min(o[2][1]) for o in outlines if o[2][1]), default=0.0
    )

    box_w = _FIG_W_IN - _PAD_LEFT_IN - _PAD_RIGHT_IN
    top_h = min(_TOP_MAX_H_IN, max(_TOP_MIN_H_IN, box_w * chord_extent / span))
    front_h = max(_FRONT_MIN_H_IN, box_w * dihedral_extent / span)
    fig_h = _PAD_TOP_IN + top_h + _PAD_GAP_IN + front_h + _PAD_BOTTOM_IN

    fig = plt.figure(figsize=(_FIG_W_IN, fig_h))
    ax_top = fig.add_axes((
        _PAD_LEFT_IN / _FIG_W_IN,
        (_PAD_BOTTOM_IN + front_h + _PAD_GAP_IN) / fig_h,
        box_w / _FIG_W_IN,
        top_h / fig_h,
    ))
    ax_front = fig.add_axes((
        _PAD_LEFT_IN / _FIG_W_IN,
        _PAD_BOTTOM_IN / fig_h,
        box_w / _FIG_W_IN,
        front_h / fig_h,
    ))

    colors = plt.cm.tab10.colors
    for i, (label, (ys, les, tes), (yf, zf)) in enumerate(outlines):
        c = colors[i % 10]
        ax_top.plot(ys, les, "-", color=c, lw=1.6, label=label)
        ax_top.plot(ys, tes, "-", color=c, lw=1.6)
        ax_top.plot([ys[0]] * 2, [les[0], tes[0]], "-", color=c, lw=1.6)
        ax_top.plot([ys[-1]] * 2, [les[-1], tes[-1]], "-", color=c, lw=1.6)
        ax_front.plot(yf, zf, "-", color=c, lw=1.6)

    ax_top.invert_yaxis()  # x aft-positive: draw LE up
    ax_top.set(ylabel="x (m)", title="Wing planform (top view)")
    ax_top.legend(fontsize=8)
    ax_front.set(xlabel="y (m)", ylabel="z (m)", title="Dihedral (front view)")
    # `datalim`, not the default `box`: the box is already the right size, and
    # letting matplotlib shrink it to satisfy the aspect is what produced the
    # blank band above the planform. Widening the limits instead keeps true
    # scale AND the allocated box.
    for a in (ax_top, ax_front):
        a.set_aspect("equal", adjustable="datalim")
        a.grid(alpha=0.3)
    # Four ticks at most: with a wing this flat, the default locator offers more
    # z values than the axis has room to print.
    ax_front.yaxis.set_major_locator(plt.MaxNLocator(4))
    fig.savefig(out_dir / fname, dpi=110)
    plt.close(fig)


def three_view(plane, out_dir: Path, fname="three_view.png") -> None:
    """AeroSandbox shaded three-view of the (numeric) airplane."""
    import matplotlib.pyplot as _plt

    plane.draw_three_view(show=False)
    fig = _plt.gcf()
    fig.savefig(out_dir / fname, dpi=110)
    _plt.close(fig)


def interactive_3d(plane, run_dir: Path, fname="interactive_3d.html") -> None:
    """Rotatable 3D model (plotly, self-contained HTML) written next to
    report.html — open in any browser; no display server needed."""
    fig = plane.draw(backend="plotly", show=False)
    fig.update_layout(title=plane.name, scene_aspectmode="data")
    fig.write_html(run_dir / fname, include_plotlyjs=True)


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
