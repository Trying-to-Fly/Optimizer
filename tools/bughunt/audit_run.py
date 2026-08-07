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
    # The objective NAME is top-level and the VALUE is the re-evaluation's best
    # point. `performance.objective` has never existed, so this line read
    # "<ABSENT> min" on every artifact ever written — a reading aid reporting a
    # missing field where the artifact is complete.
    print(f"objective         {j.get('objective', '<ABSENT>')} = "
          f"{get(j, 'performance', 'best', 'objective_value')} "
          f"{get(j, 'performance', 'objective_units')} "
          f"at V = {get(j, 'performance', 'best', 'V_ms')} m/s")

    # --- FINDINGS 28: is the headline entitled to be read as an answer? -----
    #
    # First, because §28 says so: "candidates_source is now the first thing to
    # read in its artifact". `feasible_fallback` means NO operating point was
    # airworthy and the headline is not an all-clear, which is invisible in
    # every other field — `airworthiness_price` is null in exactly that case
    # (there is no better legal point to name) and reads as "the filters cost
    # nothing".
    source = diag.get("candidates_source", "<ABSENT>")
    print(f"candidates_source {source}")
    if source == "feasible_fallback":
        print("  !! NO LEGAL OPERATING POINT — the headline is a fallback, "
              "not a design (FINDINGS 28)")
    violations = diag.get("reported_point_violations")
    if violations:
        for v in violations:
            print(f"  !! violates {v}")
    elif source == "feasible_fallback":
        print("  !! fallback fired but no violations recorded — read notes[0]")

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
        # `station_mm` is the key `solve.py` writes (and `equipment.py` beside
        # it). This checked `x_m` — which lives in the geometry export and the
        # manufacturing sheet, never here — so it reported the fc58751 defect as
        # still present on every artifact that had in fact fixed it.
        if not isinstance(v0, dict) or "station_mm" not in v0:
            print("  !! components carry mass without station")

    # --- whose trade rate the shadow price is (2026-08-07) ------------------
    #
    # The +20 g bump is re-solved on the shipped design so the quoted rate is
    # ITS rate; when that solve fails the value silently falls back to the
    # multistart screen's, measured before the studies chose the design.
    opt = get(j, "performance", "optimization", default={})
    shadow = opt.get("shadow_price_source") if isinstance(opt, dict) else None
    per_g = opt.get("shadow_price_obj_per_gram") if isinstance(opt, dict) else None
    if isinstance(shadow, dict):
        print(f"shadow_price      {per_g}  from {shadow.get('source')}")
        if shadow.get("source") != "final_design":
            print(f"  !! NOT THIS DESIGN'S RATE — measured on "
                  f"{shadow.get('measured_on_objective')}, quoted beside "
                  f"{shadow.get('reported_beside_champion')}")
            print(f"     final bump: {shadow.get('final_bump_failed')}")
    elif per_g is not None:
        print(f"shadow_price      {per_g}  <-- no provenance recorded "
              f"(artifact predates shadow_price_source)")

    # --- the two declared pod limits, and whether they BIND (2026-08-07) ----
    #
    # Neither can appear in `active_bounds`: that reports design-variable BOX
    # bounds and both of these are constraint rows.
    ab = diag.get("afterbody")
    if isinstance(ab, dict):
        f, fmax = ab.get("fineness"), ab.get("fineness_max")
        bt, btmin = ab.get("boat_tail_d_eq"), ab.get("boat_tail_min_d_eq")
        print(f"afterbody         f={f} (max {fmax})  "
              f"boat_tail={bt} d_eq (min {btmin})  "
              f"theta_max={ab.get('theta_max_deg')}")
        if ab.get("fineness_ceiling_active"):
            print("  !! FINENESS CEILING BINDING — a model-validity bound is "
                  "setting the pod, not the aeroplane")
        if ab.get("boat_tail_floor_active"):
            print("  !! BOAT-TAIL FLOOR STILL ACTIVE — the afterbody term is not "
                  "holding the tail open; do NOT delete the floor")
        if "fineness_ceiling_active" not in ab:
            print("  (no limit-activity flags — artifact predates them)")

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
