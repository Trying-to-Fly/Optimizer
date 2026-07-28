"""APC performance tables -> smooth CT(J,Re)/CP(J,Re) fits (MODEL_DETAILS.md section 2.1).

Reads PER3_*.dat files, fits low-order polynomials in advance ratio AND blade
Reynolds number, and writes one JSON per prop with coefficients + fit metadata.

Why two variables. APC tabulates each prop across a wide RPM sweep, and CT/CP at
a given J drift systematically with Reynolds. An earlier version fitted CT(J)
alone over a hardcoded RPM window, which forced a choice no single number can
make honestly: the window has to be centred on the operating point, but the
right centre depends on the aircraft AND on the prop (a 5 in prop cruises above
15000 rpm, a 22 in prop below 4000). Fitting Reynolds as a second variable
removes the window entirely -- every RPM block is data, and the solver evaluates
at whatever Reynolds the operating point actually has. Measured against raw APC
rows in an 11x7E's cruise band, this cuts efficiency error from ~6.9% to <1%.

Reynolds is recoverable from the operating point, so nothing extra has to be
carried: the blade sees W_75 = n*D*sqrt((0.75*pi)^2 + J^2) at 75% span, hence

    Re = re_coeff * n * sqrt((0.75*pi)^2 + J^2)      n in rev/s

with re_coeff = (rho/mu) * c_75 * D a per-prop constant. Backed out of the data
it holds to ~0.2% across every prop and RPM block, so it is stored, not modelled.

Run:
    uv run python tools/ingest_props.py --fetch      # whole APC catalogue
    uv run python tools/ingest_props.py              # whatever .dat files are local
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).parent.parent
SOURCE = REPO / "data" / "props"  # raw APC .dat tables (repo material)
CACHE = SOURCE / "_apc_cache"  # bulk-archive extract, gitignored (67 MB)
FITS = REPO / "src" / "planeopt" / "data" / "props"  # fitted coeffs (shipped package data)

# The published archive of every performance file. Plain text compresses ~8x, so
# the whole catalogue is a ~8 MB download for ~67 MB of data.
ARCHIVE_URL = "https://www.apcprop.com/wp-content/uploads/2026/02/PERFILES_WEB-202602.zipx"

# CT and CP are fitted through the SAME design matrix, so they share both degrees
# — one constant each, rather than a per-coefficient pair that cannot actually differ.
J_DEG = 3  # degree in advance ratio
RE_DEG = 2  # degree in log Reynolds
CT_MIN = 0.005  # below this the prop is not usefully thrusting
TIP_MACH_MAX = 0.75  # exclude transonic RPM blocks: the polynomial cannot follow drag rise
OMEGA_75 = 0.75 * np.pi  # 75%-span radius ratio, as an angular-to-linear factor


class UnderwaterProp(Exception):
    """APC also publishes marine props. Same file format, different fluid."""


def parse_per3(path: Path) -> np.ndarray:
    """Return array of rows (rpm, J, Ct, Cp, tip Mach, Re at 75% span).

    Columns are located by name, not position: the marine files swap the tip-Mach
    column for tip speed in ft/s, which read positionally is silently wrong.
    """
    text = path.read_text(errors="ignore")
    if "(Underwater)" in text:
        raise UnderwaterProp("marine prop — an aircraft library must not offer it")
    header = next((ln for ln in text.splitlines() if "Adv_Ratio" not in ln and "J " in ln
                   and "Ct" in ln and "Reyn" in ln), None)
    cols = header.split() if header else []
    try:
        i_j, i_ct, i_cp = cols.index("J"), cols.index("Ct"), cols.index("Cp")
        i_mach, i_re = cols.index("Mach"), cols.index("Reyn")
    except ValueError as e:
        raise ValueError(f"unrecognised column layout: {cols or 'no header row'}") from e

    rows, rpm, width = [], None, len(cols)
    for line in text.splitlines():
        m = re.search(r"PROP RPM =\s+(\d+)", line)
        if m:
            rpm = int(m.group(1))
            continue
        parts = line.split()
        if rpm is None or len(parts) < width:
            continue
        try:
            v = [float(x) for x in parts[:width]]
        except ValueError:
            continue
        rows.append((rpm, v[i_j], v[i_ct], v[i_cp], v[i_mach], v[i_re]))
    return np.array(rows) if rows else np.empty((0, 6))


def identity(path: Path) -> dict:
    """Diameter/pitch from the file's own header line.

    The filename drops the decimal point (11x5.5E ships as PER3_11x55E.dat), so
    the header's display name is the only unambiguous source.
    """
    head = path.read_text(errors="ignore").splitlines()[0].split()
    name = head[0] if head else path.stem
    m = re.match(r"^([A-Z]*)(\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)(.*)$", name)
    if not m:
        return {"display_name": name, "diameter_in": None, "pitch_in": None}
    prefix, dia, pitch, suffix = m.groups()
    return {
        "display_name": name,
        "diameter_in": float(dia),
        "pitch_in": float(pitch),
        "series": (prefix + suffix).strip() or None,
    }


def _design_matrix(J, u):
    """Columns J^i * u^k, i ascending outer, k ascending inner."""
    return np.column_stack(
        [J**i * u**k for i in range(J_DEG + 1) for k in range(RE_DEG + 1)]
    )


def _to_horner_grid(coeffs: np.ndarray) -> list[list[float]]:
    """lstsq solution -> nested-Horner grid, descending in J (outer) and u (inner)."""
    return coeffs.reshape(J_DEG + 1, RE_DEG + 1)[::-1, ::-1].tolist()


def fit_prop(dat_file: Path, key: str, out_dir: Path) -> dict:
    raw = parse_per3(dat_file)
    if len(raw) == 0:
        raise ValueError("no parseable performance rows")
    rpm, J, Ct, Cp, mach, Re = raw.T

    keep = (Ct > CT_MIN) & (mach <= TIP_MACH_MAX) & (Re > 0) & (rpm > 0)
    if keep.sum() < 40:
        raise ValueError(f"only {keep.sum()} usable rows after Ct/Mach filtering")
    rpm, J, Ct, Cp, Re = rpm[keep], J[keep], Ct[keep], Cp[keep], Re[keep]
    n = rpm / 60.0

    # Reynolds as a per-prop constant times the local blade speed (see module docstring)
    k_re = Re / (n * np.sqrt(OMEGA_75**2 + J**2))
    re_coeff = float(np.mean(k_re))
    re_coeff_spread = float(k_re.max() / k_re.min() - 1.0)

    log_re = np.log(Re)
    re_ref, re_scale = float(log_re.mean()), float(log_re.std())
    re_scale = re_scale if re_scale > 1e-9 else 1.0
    u = (log_re - re_ref) / re_scale

    A = _design_matrix(J, u)
    ct_c = np.linalg.lstsq(A, Ct, rcond=None)[0]
    cp_c = np.linalg.lstsq(A, Cp, rcond=None)[0]

    ct_fit, cp_fit = A @ ct_c, A @ cp_c
    eta_fit = J * ct_fit / cp_fit
    eta_raw = J * Ct / Cp
    ok = eta_raw > 0.05  # relative eta error is meaningless as eta -> 0

    meta = {
        "schema": 2,
        "key": key,
        "source": dat_file.name,
        **identity(dat_file),
        "re_coeff": re_coeff,
        "j_range": [0.0, float(J.max())],
        "re_range": [float(Re.min()), float(Re.max())],
        "log_re_ref": re_ref,
        "log_re_scale": re_scale,
        "ct_coeffs": _to_horner_grid(ct_c),
        "cp_coeffs": _to_horner_grid(cp_c),
        "ct_rms": float(np.sqrt(np.mean((ct_fit - Ct) ** 2))),
        "cp_rms": float(np.sqrt(np.mean((cp_fit - Cp) ** 2))),
        "eta_rel_pct": float(np.sqrt(np.mean((eta_fit[ok] / eta_raw[ok] - 1) ** 2)) * 100),
        "re_coeff_spread_pct": re_coeff_spread * 100,
        "n_points": int(len(J)),
        "rpm_range": [int(rpm.min()), int(rpm.max())],
    }
    # 443 tables ship inside the wheel and the .exe, so they are written compact
    # and rounded to 12 significant digits -- still far finer than APC's own
    # 4-decimal source data, and a third of the size of indented full-precision.
    (out_dir / f"{key}.json").write_text(
        json.dumps(_round(meta), separators=(",", ":")), encoding="utf-8"
    )
    return meta


def _round(o, sig: int = 12):
    if isinstance(o, float):
        return float(f"%.{sig}g" % o)
    if isinstance(o, dict):
        return {k: _round(v, sig) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v, sig) for v in o]
    return o


def key_for(dat_file: Path) -> str:
    """PER3_11x7E.dat -> apc_11x7e (the existing shipped naming)."""
    return "apc_" + dat_file.stem.replace("PER3_", "", 1).lower()


def fetch_archive(dest: Path) -> int:
    """Download + extract every PER3_*.dat from the published APC archive."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "_archive.zipx"
    print(f"downloading {ARCHIVE_URL}")
    with urllib.request.urlopen(ARCHIVE_URL, timeout=300) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    print(f"  {tmp.stat().st_size / 1e6:.1f} MB")
    written = 0
    with zipfile.ZipFile(tmp) as z:
        for entry in z.namelist():
            base = Path(entry).name
            if base.upper().startswith("PER3_") and base.upper().endswith(".DAT"):
                (dest / base).write_bytes(z.read(entry))
                written += 1
    tmp.unlink()
    print(f"  extracted {written} PER3 files to {dest}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true",
                    help="download the full APC archive into the cache first")
    ap.add_argument("--source", type=Path, action="append", default=None,
                    help="directory of PER3_*.dat files (repeatable)")
    ap.add_argument("--out", type=Path, default=FITS, help="where to write fitted JSONs")
    args = ap.parse_args()

    if args.fetch:
        fetch_archive(CACHE)

    sources = args.source or [SOURCE, CACHE]
    dats: dict[str, Path] = {}
    for d in sources:
        if d.is_dir():
            for p in sorted(d.glob("PER3_*.dat")):
                dats.setdefault(key_for(p), p)  # earlier source wins
    if not dats:
        print(f"no PER3_*.dat found in {[str(d) for d in sources]}; try --fetch",
              file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    ok, failed, marine = [], [], []
    for key, path in sorted(dats.items()):
        try:
            ok.append(fit_prop(path, key, args.out))
        except UnderwaterProp:
            marine.append(key)
        except Exception as e:  # a malformed file must not lose the other 442
            failed.append((key, str(e)))

    worst = sorted(ok, key=lambda m: -m["eta_rel_pct"])[:5]
    print(f"fitted {len(ok)} props -> {args.out}")
    print(f"  eta error: median {np.median([m['eta_rel_pct'] for m in ok]):.2f}%, "
          f"worst {worst[0]['eta_rel_pct']:.2f}% ({worst[0]['key']})")
    print(f"  Re-model spread: max {max(m['re_coeff_spread_pct'] for m in ok):.2f}%")
    if worst:
        print("  least-well-fitted: " + ", ".join(
            f"{m['key']} {m['eta_rel_pct']:.1f}%" for m in worst))
    if marine:
        print(f"  excluded {len(marine)} underwater props: {', '.join(marine)}")
    if failed:
        print(f"  FAILED {len(failed)}: " + ", ".join(f"{k} ({e})" for k, e in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
