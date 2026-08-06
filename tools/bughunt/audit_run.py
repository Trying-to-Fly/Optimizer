"""Audit a run artifact for the claims today's uncommitted work added.

Not a test — a reading aid. Every line prints what the artifact SAYS, so a
missing field is visible as absent rather than as a default.
"""
import json
import sys
from pathlib import Path


def get(d, *path, default="<ABSENT>"):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def main(run_dir):
    run = Path(run_dir)
    j = json.loads((run / "run.json").read_text())
    diag = j.get("diagnostics", {})

    print(f"== {run.name}")
    print(f"status            {j.get('status', '<ABSENT>')}")
    print(f"objective         {get(j, 'performance', 'objective')} "
          f"{get(j, 'performance', 'objective_units')}")

    # --- FINDINGS 24.1: the run must carry its own input -------------------
    dv = j.get("design_vector", "<ABSENT>")
    src = diag.get("design_source", "<ABSENT>")
    print(f"design_source     {src}")
    if dv == "<ABSENT>":
        print("design_vector     <ABSENT>  <-- FIELD MISSING")
    else:
        print(f"design_vector     {len(dv)} keys, "
              f"{'EMPTY (spec)' if not dv else sorted(dv)[:4]}")
        if src == "spec" and dv:
            print("  !! spec run recorded a non-empty vector (FINDINGS 24.1)")
        if src == "parametric" and not dv:
            print("  !! parametric run recorded nothing")
        bad = [k for k, v in (dv or {}).items()
               if not isinstance(v, (float, int, bool, str))]
        if bad:
            print(f"  !! non-JSON-scalar values: {bad}")

    # --- FINDINGS 24.2: a capped run must shout ----------------------------
    mi = diag.get("max_iter", "<ABSENT>")
    trunc = diag.get("iteration_truncated", "<ABSENT>")
    notes = j.get("notes", [])
    print(f"max_iter          {mi}   iteration_truncated={trunc}")
    if trunc is True:
        head = notes[0] if notes else "<NO NOTES>"
        ok = "NOT AN OPTIMIZATION" in str(head)
        print(f"  notes[0] shouts   {ok}  ({str(head)[:70]}...)")

    # --- the selection-time gate -------------------------------------------
    print(f"design_trustworthy {diag.get('design_trustworthy', '<ABSENT>')}")
    skipped = diag.get("characterization_skipped")
    if skipped:
        print(f"  characterization_skipped {skipped}")
    gate = diag.get("objective_mesh_check")
    if isinstance(gate, dict):
        print(f"  gate delta_frac  {gate.get('delta_frac'):+.4f} "
              f"converged={gate.get('converged')}")

    # --- fc58751: mass AND station -----------------------------------------
    comps = get(j, "masses", "components", default={})
    if isinstance(comps, dict) and comps:
        k0 = next(iter(comps))
        v0 = comps[k0]
        print(f"components        {len(comps)} entries; sample {k0} -> {v0}")
        if not isinstance(v0, dict) or "x_m" not in v0:
            print("  !! components carry mass without station")

    # --- the new cross-checks ----------------------------------------------
    mesh = diag.get("aero_mesh_check")
    if isinstance(mesh, dict):
        print(f"aero_mesh_check   drag converged={mesh.get('converged')} "
              f"delta_frac={mesh.get('delta_frac')}")
        sm = mesh.get("static_margin")
        if sm is None:
            print("  static_margin     <ABSENT>  <-- new arm did not run")
        else:
            print(f"  SM in_loop={get(sm, 'in_loop', 'static_margin')} "
                  f"fine={get(sm, 'fine', 'static_margin')} "
                  f"converged={sm.get('converged')}")
            print(f"  sign_flip survives={sm.get('sign_flip_survives_refinement')} "
                  f"artefact={sm.get('sign_flip_is_mesh_artefact')}")
    else:
        print("aero_mesh_check   <ABSENT>")

    for key in ("vlm_directional_check", "directional_check",
                "vlm_static_margin_check", "sm_cross_check"):
        if key in diag:
            print(f"{key}  {json.dumps(diag[key])[:200]}")

    print(f"notes             {len(notes)}")
    for n in notes:
        print(f"  - {str(n)[:110]}")

    files = sorted(p.name for p in run.iterdir())
    print(f"files             {files}")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        main(d)
        print()
