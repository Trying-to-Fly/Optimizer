"""UIUC Propeller Data Site -> the same CT(J,Re)/CP(J,Re) fits as the APC tables.

Why bother when 443 APC tables already ship: APC's PER3 files are *simulation*
output — their own headers say "AIRFOIL AERO DATA GENERATED USING: POLAR
DIAGRAMS". The UIUC database is **wind-tunnel measurement**, and critically it
covers **folding** propellers, which APC's catalogue barely does (12 tables) and
which this project models by applying a flat 0.95 derate to a rigid-blade proxy.
Volume 3 alone is 40 Aero-Naut CAM carbon folding props — the exact hardware the
sample aircraft's PROP_CANDIDATES names and has only ever approximated.

Each propeller has one file per tested RPM (`J CT CP eta`) plus a static sweep
(`RPM CT CP`), which is the RPM spread the Reynolds dimension of the fit needs.

Two honest differences from the APC path, both recorded in the output:

- **Reynolds is estimated, not tabulated.** APC publishes `Reyn` at 75% span, so
  `ingest_props` backs the per-prop constant out of the data. UIUC does not, so
  c_75 is estimated from the ratio APC's own tables imply (c_75 ~ 0.064 D). The
  FIT is unaffected either way — log Re enters as log K + log(n*sqrt(...)), and a
  wrong K is absorbed by the stored normalisation — but the REPORTED Reynolds is
  then good to roughly +/-20%, so `re_estimated` is set true.
- **Narrower RPM band** (~2000-7000 vs APC's 1000-20000), so the fit extrapolates
  outside it. `rpm_range` records what was actually covered.

Run:
    uv run python tools/ingest_uiuc.py --fetch
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ingest_props import (  # noqa: E402  — one fitting core, deliberately shared
    CT_MIN,
    OMEGA_75,
    _design_matrix,
    _round,
    _to_horner_grid,
)

REPO = Path(__file__).parent.parent
CACHE = REPO / "data" / "props" / "_uiuc_cache"  # gitignored, regenerable
FITS = REPO / "src" / "planeopt" / "data" / "props"

BASE = "https://m-selig.ae.illinois.edu/props"
VOLUMES = (1, 2, 3, 4)

#: Air at sea level: rho/mu, for turning a blade speed into a Reynolds number.
RHO_OVER_MU = 1.225 / 1.81e-5
#: Chord at 75% span as a fraction of diameter. Not a guess — it is what APC's
#: own tabulated Reynolds implies for their 11 in props (337 = RHO_OVER_MU*c75*D).
C75_OVER_D = 0.0638

#: FOLDING FAMILIES. Folding is a property of the product line, not of a size,
#: so it is declared per (manufacturer, series) and kept reviewable rather than
#: inferred from a filename. Sources: the UIUC volume pages' own headings, and
#: AIAA 2020-2762 for the Volume 3 set ("Aero-Naut CAM Folding Propellers").
#: CAM (Graupner/aero-naut) and Kavan's FK are folding lines; Master Airscrew's
#: G/F is the glider/folding series; APC's Carbon Fiber blades are their folding
#: glider product. Everything not listed here is treated as FIXED.
FOLDING = {
    ("Aeronaut", "CAM Folding"),
    ("Aeronaut", "Carbon Electric"),
    ("APC", "Carbon Fiber"),
    ("Graupner", "CAM Prop"),
    ("Graupner", "CAM Slim"),
    ("Kavon", "FK"),
    ("Master_Airscrew", "G/F"),
}


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", s))).strip()


#: Filename prefix -> (manufacturer, series). The prefix is the only identifier
#: that is stable across volumes: Volume 1 marks manufacturers with <h> headings
#: and series with blue subheadings, Volumes 2-4 have no <h> headings at all, and
#: they disagree on whether the colour attribute is single- or double-quoted.
#: Volume 1's own headings are the source for everything it covers; the rest are
#: added explicitly, with Volume 3's identity taken from its title and AIAA
#: 2020-2762 ("Aero-Naut CAM Folding Propellers").
PREFIX = {
    "ance": ("Aeronaut", "Carbon Electric"),
    "ancf": ("Aeronaut", "CAM Folding"),
    "apc": ("APC", "Free Flight"),
    "apccf": ("APC", "Carbon Fiber"),
    "apce": ("APC", "Thin Electric"),
    "apcff": ("APC", "Free Flight"),
    "apcsf": ("APC", "Slow Flyer"),
    "apcsp": ("APC", "Sport"),
    "grcp": ("Graupner", "CAM Prop"),
    "grcsp": ("Graupner", "CAM Slim"),
    "grsn": ("Graupner", "Super Nylon"),
    "gwsdd": ("GWS", "Direct-Drive"),
    "gwssf": ("GWS", "Slow Flyer"),
    "kavfk": ("Kavon", "FK"),
    "kpf": ("Kyosho", "PF"),
    "kyosho": ("Kyosho", ""),
    "ma": ("Master_Airscrew", ""),
    "mae": ("Master_Airscrew", "Electric"),
    "magf": ("Master_Airscrew", "G/F"),
    "mas": ("Master_Airscrew", "Scimitar"),
    "rusp": ("Rev_Up", "Special Prop Series"),
    "zin": ("Zingali", ""),
}

#: Size in the filename, e.g. ancf_11x12, apccf_7.8x7, ancf_125x6.
_STEM = re.compile(r"data/(([a-z]+)_[\d.]+x[\d.]+)_")


def manifest(volume: int, page: str) -> list[dict]:
    """Every propeller on one volume page: identity + its data files.

    Diameter and pitch come from the page's own displayed size ("8 X 3.8"), never
    from the filename — Volume 3 drops decimal points (`ancf_125x6` IS 12.5x6)
    while Volume 1 keeps them (`apccf_7.8x7`), so filenames cannot be parsed for
    size without guessing where the point went.
    """
    toks: list[tuple[int, str, str]] = []
    toks += [(m.start(), "HEAD", _text(m.group(1)))
             for m in re.finditer(r'<font color=["\']#047["\']><b>(.*?)</b>', page, re.S)]
    toks += [(m.start(), "FILE", m.group(0))
             for m in _STEM.finditer(page)]
    toks.sort()

    props: dict[str, dict] = {}
    dia = pitch = None
    for _, kind, val in toks:
        if kind == "HEAD":
            size = re.fullmatch(r"([\d.]+)\s*[Xx]\s*([\d.]+)", val)
            if size:
                dia, pitch = float(size.group(1)), float(size.group(2))
            continue
        m = _STEM.match(val)
        stem, prefix = m.group(1), m.group(2)
        if dia is None:
            continue  # a link before any size heading has no identity
        mfr, series = PREFIX.get(prefix, ("unknown", prefix))
        p = props.setdefault(stem, {
            "stem": stem, "volume": volume, "manufacturer": mfr, "series": series,
            "diameter_in": dia, "pitch_in": pitch, "files": [],
        })
    # collect every file per prop separately: the size heading only marks where a
    # prop's block starts, and one block holds a static file plus one per RPM
    for m in re.finditer(r'href="(data/[^"]+\.txt)"', page):
        s = _STEM.match(m.group(1))
        if s and s.group(1) in props:
            props[s.group(1)]["files"].append(m.group(1))
    return list(props.values())


def _get(url: str, tries: int = 4) -> bytes:
    """One polite GET with backoff. The host rate-limits a burst of ~400 files,
    so a retry loop matters more here than concurrency does."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"gave up on {url}")


def fetch_all(props: list[dict], dest: Path, workers: int = 1,
              delay: float = 0.4, order: tuple = ()) -> int:
    """Sequential and paced by default. Eight concurrent workers got this client
    blocked at ~400 files; the host is a university web server, not a CDN."""
    dest.mkdir(parents=True, exist_ok=True)
    rank = {v: i for i, v in enumerate(order)}
    jobs = [(p["volume"], f) for p in sorted(props, key=lambda q: rank.get(q["volume"], 99))
            for f in p["files"]]
    jobs = [(v, f) for v, f in jobs if not (dest / f"v{v}_{Path(f).name}").is_file()]
    if not jobs:
        return 0

    def get(job):
        """A dead link must cost one file, not the other 1990."""
        vol, rel = job
        out = dest / f"v{vol}_{Path(rel).name}"
        try:
            out.write_bytes(_get(f"{BASE}/volume-{vol}/{rel}"))
            time.sleep(delay)
            return True
        except Exception:
            return False

    done = missing = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, got in enumerate(ex.map(get, jobs), 1):
            done += bool(got)
            missing += not got
            if i % 250 == 0:
                print(f"  {i}/{len(jobs)} files ({missing} unavailable)")
    if missing:
        print(f"  {missing} of {len(jobs)} links were dead (404) — skipped")
    return done


def _rows(prop: dict, cache: Path) -> np.ndarray:
    """(rpm, J, CT, CP) from every file of one propeller, static included at J=0."""
    out = []
    for rel in prop["files"]:
        path = cache / f"v{prop['volume']}_{Path(rel).name}"
        if not path.is_file():
            continue
        static = "_static_" in path.name
        rpm_tag = re.search(r"_(\d{3,5})\.txt$", path.name)
        for line in path.read_text(errors="ignore").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                a, b, c = (float(x) for x in parts[:3])
            except ValueError:
                continue
            if static:
                out.append((a, 0.0, b, c))          # RPM CT CP
            elif rpm_tag:
                out.append((float(rpm_tag.group(1)), a, b, c))  # J CT CP (eta)
    return np.array(out) if out else np.empty((0, 4))


def fit(prop: dict, cache: Path, out_dir: Path) -> dict:
    raw = _rows(prop, cache)
    if len(raw) == 0:
        raise ValueError("no parseable rows")
    rpm, J, Ct, Cp = raw.T
    keep = (Ct > CT_MIN) & (Cp > 0) & (rpm > 0)
    if keep.sum() < 40:
        raise ValueError(f"only {keep.sum()} usable rows")
    rpm, J, Ct, Cp = rpm[keep], J[keep], Ct[keep], Cp[keep]
    n = rpm / 60.0

    d_m = prop["diameter_in"] * 0.0254
    re_coeff = RHO_OVER_MU * C75_OVER_D * d_m * d_m
    Re = re_coeff * n * np.sqrt(OMEGA_75**2 + J**2)

    log_re = np.log(Re)
    ref, scale = float(log_re.mean()), float(log_re.std())
    scale = scale if scale > 1e-9 else 1.0
    u = (log_re - ref) / scale

    A = _design_matrix(J, u)
    ct_c = np.linalg.lstsq(A, Ct, rcond=None)[0]
    cp_c = np.linalg.lstsq(A, Cp, rcond=None)[0]
    ct_fit, cp_fit = A @ ct_c, A @ cp_c
    eta_raw, eta_fit = J * Ct / Cp, J * ct_fit / cp_fit
    ok = eta_raw > 0.05

    key = f"uiuc_{prop['stem'].replace('.', 'p')}"
    meta = {
        "schema": 2,
        "key": key,
        "source": f"UIUC PDB vol {prop['volume']}: {prop['stem']}",
        "source_db": "UIUC",
        "measured": True,
        "display_name": f"{prop['manufacturer']} {prop['series']} "
                        f"{prop['diameter_in']:g}x{prop['pitch_in']:g}".replace("_", " "),
        "manufacturer": prop["manufacturer"],
        "series": prop["series"],
        "folding": (prop["manufacturer"], prop["series"]) in FOLDING,
        "diameter_in": prop["diameter_in"],
        "pitch_in": prop["pitch_in"],
        "re_coeff": re_coeff,
        "re_estimated": True,
        "j_range": [0.0, float(J.max())],
        "re_range": [float(Re.min()), float(Re.max())],
        "log_re_ref": ref,
        "log_re_scale": scale,
        "ct_coeffs": _to_horner_grid(ct_c),
        "cp_coeffs": _to_horner_grid(cp_c),
        "ct_rms": float(np.sqrt(np.mean((ct_fit - Ct) ** 2))),
        "cp_rms": float(np.sqrt(np.mean((cp_fit - Cp) ** 2))),
        "eta_rel_pct": float(np.sqrt(np.mean((eta_fit[ok] / eta_raw[ok] - 1) ** 2)) * 100)
        if ok.any() else 0.0,
        "n_points": int(len(J)),
        "rpm_range": [int(rpm.min()), int(rpm.max())],
        # Partial coverage is legitimate — fewer RPM files just means a narrower
        # Reynolds span — but it must be visible rather than folded silently
        # into the fit, so a reader can tell a full prop from a half-fetched one.
        "files_used": sum(
            (cache / f"v{prop['volume']}_{Path(f).name}").is_file() for f in prop["files"]),
        "files_total": len(prop["files"]),
    }
    (out_dir / f"{key}.json").write_text(
        json.dumps(_round(meta), separators=(",", ":")), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download the data files first")
    ap.add_argument("--out", type=Path, default=FITS)
    ap.add_argument("--only-folding", action="store_true",
                    help="fetch/fit only the folding families (see FOLDING)")
    ap.add_argument("--delay", type=float, default=0.4,
                    help="seconds between requests (the host rate-limits bursts)")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    props = []
    for vol in VOLUMES:
        page_file = CACHE / f"volume-{vol}.html"
        if not page_file.is_file():
            page_file.write_bytes(_get(f"{BASE}/volume-{vol}/propDB-volume-{vol}.html"))
        props += manifest(vol, page_file.read_text(errors="ignore"))
    if args.only_folding:
        props = [p for p in props if (p["manufacturer"], p["series"]) in FOLDING]
    print(f"manifest: {len(props)} propellers"
          f"{' (folding only)' if args.only_folding else ''}, "
          f"{sum(len(p['files']) for p in props)} data files")

    if args.fetch:
        print(f"downloading (1 worker, {args.delay}s apart — the host blocks bursts)…")
        # folding volumes first: if the fetch is interrupted, the data the next
        # run actually needs is already on disk
        fetch_all(props, CACHE, delay=args.delay, order=(3, 1, 2, 4))

    args.out.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    for p in props:
        try:
            ok.append(fit(p, CACHE, args.out))
        except Exception as e:  # one bad prop must not lose the rest
            failed.append((p["stem"], str(e)))

    fold = [m for m in ok if m["folding"]]
    print(f"fitted {len(ok)} UIUC propellers -> {args.out}")
    print(f"  eta error: median {np.median([m['eta_rel_pct'] for m in ok]):.2f}%")
    print(f"  FOLDING: {len(fold)} of {len(ok)}")
    for mf in sorted({(m["manufacturer"], m["series"], m["folding"]) for m in ok}):
        print(f"    {'FOLD' if mf[2] else '    '}  {mf[0]:<16} {mf[1]}")
    if failed:
        print(f"  skipped {len(failed)}: " + ", ".join(f"{k} ({e})" for k, e in failed[:6]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
