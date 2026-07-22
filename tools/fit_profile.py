"""Fit ConstructionProfile constants from slicer data (MODEL_DETAILS.md section 1.4).

Input: a CSV of sliced test parts, one row per part:

    name,kind,chord_m,span_m,n_joints,mass_kg
    wing_sec_180,section,0.180,0.225,0,0.0412
    wing_sec_220,section,0.220,0.225,0,0.0488
    wing_sec_260,section,0.260,0.225,0,0.0571
    joint_pair,joint,0.220,0.0,1,0.0080
    overhead_parts,overhead,0,0,0,0.0600

kind=section rows fit  mass = k_skin*2.05*chord*span + k_rib*span*chord^2/pitch
(least squares over >=2 chords); kind=joint rows set k_joint per joint;
kind=overhead rows sum into overhead_kg.

Mass column: use slicer filament LENGTH x measured g/m from a flow-calibration
print, not the slicer's mass estimate — foaming filaments make the slicer's
density assumption the dominant error.

Run: uv run python tools/fit_profile.py <parts.csv> [--rib-pitch 0.09]
Prints a ConstructionProfile(...) block to paste into the aircraft's profile module
(set calibrated=True once the values come from real slicer/scale data).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

WETTED_FACTOR = 2.05


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file", type=Path)
    ap.add_argument("--rib-pitch", type=float, default=0.09)
    ap.add_argument("--finish-factor", type=float, default=1.05)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv_file)))
    sections = [r for r in rows if r["kind"] == "section"]
    if len(sections) < 2:
        raise SystemExit("need >=2 section rows at different chords to separate skin/rib terms")

    A, y = [], []
    for r in sections:
        c, b = float(r["chord_m"]), float(r["span_m"])
        A.append([WETTED_FACTOR * c * b, b * c**2 / args.rib_pitch])
        y.append(float(r["mass_kg"]))
    (k_skin, k_rib), res, *_ = np.linalg.lstsq(np.array(A), np.array(y), rcond=None)
    pred = np.array(A) @ np.array([k_skin, k_rib])
    rms = float(np.sqrt(np.mean((pred - np.array(y)) ** 2)))

    joints = [r for r in rows if r["kind"] == "joint"]
    k_joint = (
        float(np.mean([float(r["mass_kg"]) / max(1, int(r["n_joints"])) for r in joints]))
        if joints
        else 0.008
    )
    overhead = sum(float(r["mass_kg"]) for r in rows if r["kind"] == "overhead")

    print(f"# fit from {args.csv_file.name}: {len(sections)} sections, "
          f"rms {rms*1000:.2f} g")
    print(f"""ConstructionProfile(
    name="<material_printer>",
    k_skin_kg_m2={k_skin:.4f},
    k_rib_kg_m2={k_rib:.4f},
    rib_pitch_m={args.rib_pitch},
    k_joint_kg={k_joint:.4f},
    section_length_m=0.225,
    overhead_kg={overhead:.4f},
    finish_factor={args.finish_factor},
    calibrated=True,
)""")


if __name__ == "__main__":
    main()
