"""APC performance tables -> smooth CT(J)/CP(J) fits (MODEL_DETAILS.md section 2.1).

Reads PER3_*.dat files from data/props/, restricts to the RPM range relevant to this
aircraft class, fits low-order polynomials over the useful J range, and writes one
JSON per prop with coefficients + fit metadata, plus a fit-quality plot.

Also writes a pitch-blended proxy for the Aeronaut CAM 11x6 folder:
coefficients = (1-w)*11x5.5E + w*11x7E with w = (6-5.5)/(7-5.5) = 1/3.
Run: uv run python tools/ingest_props.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).parent.parent
SOURCE = REPO / "data" / "props"  # raw APC .dat tables + fit-quality plots (repo material)
FITS = REPO / "src" / "planeopt" / "data" / "props"  # fitted coefficients (shipped package data)
RPM_RANGE = (3000, 10000)  # cruise-relevant for 1-2.5 kg class on 3-4S
CT_DEG, CP_DEG = 3, 3


def parse_per3(path: Path) -> np.ndarray:
    """Return array of rows (rpm, J, Ct, Cp) across all RPM blocks."""
    rows, rpm = [], None
    for line in path.read_text().splitlines():
        m = re.search(r"PROP RPM =\s+(\d+)", line)
        if m:
            rpm = int(m.group(1))
            continue
        parts = line.split()
        if rpm is None or len(parts) < 5:
            continue
        try:
            v, j, pe, ct, cp = (float(x) for x in parts[:5])
        except ValueError:
            continue
        rows.append((rpm, j, ct, cp))
    return np.array(rows)


def fit_prop(dat_file: Path, key: str) -> dict:
    raw = parse_per3(dat_file)
    sel = (raw[:, 0] >= RPM_RANGE[0]) & (raw[:, 0] <= RPM_RANGE[1])
    rpm, J, Ct, Cp = raw[sel].T

    # Fit over J where the prop still produces meaningful thrust
    ok = Ct > 0.005
    j_max = float(J[ok].max())
    m = J <= j_max
    ct_c = np.polyfit(J[m], Ct[m], CT_DEG)
    cp_c = np.polyfit(J[m], Cp[m], CP_DEG)

    ct_fit, cp_fit = np.polyval(ct_c, J[m]), np.polyval(cp_c, J[m])
    meta = {
        "source": dat_file.name,
        "rpm_range": RPM_RANGE,
        "j_range": [0.0, j_max],
        "ct_coeffs": ct_c.tolist(),
        "cp_coeffs": cp_c.tolist(),
        "ct_rms": float(np.sqrt(np.mean((ct_fit - Ct[m]) ** 2))),
        "cp_rms": float(np.sqrt(np.mean((cp_fit - Cp[m]) ** 2))),
        "n_points": int(m.sum()),
    }
    (FITS / f"{key}.json").write_text(json.dumps(meta, indent=2))

    jj = np.linspace(0, j_max, 100)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
    ax[0].plot(J[m], Ct[m], ".", ms=2, alpha=0.4)
    ax[0].plot(jj, np.polyval(ct_c, jj), "r-")
    ax[0].set(xlabel="J", ylabel="Ct", title=key)
    ax[1].plot(J[m], Cp[m], ".", ms=2, alpha=0.4)
    ax[1].plot(jj, np.polyval(cp_c, jj), "r-")
    ax[1].set(xlabel="J", ylabel="Cp")
    fig.tight_layout()
    fig.savefig(SOURCE / f"{key}_fit.png", dpi=110)
    plt.close(fig)
    return meta


def main():
    FITS.mkdir(parents=True, exist_ok=True)
    m55 = fit_prop(SOURCE / "PER3_11x55E.dat", "apc_11x55e")
    m7 = fit_prop(SOURCE / "PER3_11x7E.dat", "apc_11x7e")

    w = (6.0 - 5.5) / (7.0 - 5.5)
    blend = {
        "source": "blend: (1-w)*apc_11x55e + w*apc_11x7e, w=%.3f (pitch interpolation)" % w,
        "rpm_range": RPM_RANGE,
        "j_range": [0.0, min(m55["j_range"][1], m7["j_range"][1])],
        "ct_coeffs": ((1 - w) * np.array(m55["ct_coeffs"]) + w * np.array(m7["ct_coeffs"])).tolist(),
        "cp_coeffs": ((1 - w) * np.array(m55["cp_coeffs"]) + w * np.array(m7["cp_coeffs"])).tolist(),
        "note": "proxy for Aeronaut CAM 11x6 folding; folding derate applied separately",
    }
    (FITS / "apc_11x6_blend.json").write_text(json.dumps(blend, indent=2))
    for k, m in [("apc_11x55e", m55), ("apc_11x7e", m7)]:
        print(f"{k}: {m['n_points']} pts, J<= {m['j_range'][1]:.2f}, "
              f"Ct rms {m['ct_rms']:.4f}, Cp rms {m['cp_rms']:.4f}")
    print("apc_11x6_blend written")


if __name__ == "__main__":
    main()
