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
