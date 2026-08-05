# FUSELAGE AFTERBODY DRAG — implementation plan (2026-08-05)

Closes the "needs a deeper plan before code" gap in HANDOFF's FUSELAGE DRAG
FIDELITY section. This is Tier 1 (in-loop algebraic afterbody terms + fineness
cap). The four judgement calls HANDOFF flagged as "decide, do not assume" were
decided by the user on 2026-08-05:

1. **Model form: effective-base.** One mechanism covers boat-tail separation
   AND base drag: the station where the local closure angle first exceeds the
   separation threshold defines an enlarged effective base, and unrecovered
   base pressure is charged on that area. This subsumes HANDOFF's question 2
   (max-angle vs integral) — the criterion is the first threshold crossing,
   which is closed-form for the Hermite family.
2. **θ_sep = 12°** — conservative end of the 12–15° axisymmetric-afterbody
   band. Declared data, adjustable.
3. **Fineness cap f ≤ 8** — a model-validity bound in the `lift_to_drag_max`
   idiom, not a predicted optimum (see §4).
4. **The `pod_tail ≥ 1.8·d_eq` floor stays for one battery**, then is deleted
   as a measured no-op once `active_bounds` shows it inactive (see §7).

Everything below is stated so the implementer makes no further physics
decisions — only code ones.

## 1. The model

Geometry (existing, `fuselage.loft`): tail radius fraction
`r(u) = 1 − (1−r_cap)(3u² − 2u³)`, `u ∈ [0,1]`, local radius
`R(u) = (d_eq/2)·r(u)`, station `x = tail_len·u`. All quantities below use the
**d_eq-equivalent axisymmetric convention** — the section is 68×88 so the
vertical-plane angle is ~14% steeper in tangent; the correlations are
axisymmetric, so d_eq is the consistent choice, and the understatement is noted
here rather than corrected. Revisit only if the w:h ratio is ever unlocked.

Local closure half-angle: `tan θ(u) = (d_eq/2)·(1−r_cap)·6u(1−u) / tail_len`,
maximum at u = 0.5:

    tan θ_max = 1.5 · (d_eq/2) · (1 − r_cap) / tail_len        (HANDOFF's formula)

**Separation station** — first downstream crossing of the threshold, on the
rising side (u* ∈ (0, 0.5]). With `ρ ≡ tan θ_sep / tan θ_max`:

    u* = (1 − sqrt(1 − ρ)) / 2

**Effective base**: radius fraction `r_sep = r(u*)`; charged area is the
d_eq-equivalent disc at the separation station minus the (always-occluded)
socket cap:

    A_charged = (π/4) · d_eq² · (r_sep² − r_cap²)              (≥ 0 by construction:
                                                                r is decreasing, so r_sep ≥ r_cap)

**Onset ramp** — the hidden discontinuity: as θ_max → θ_sep⁺, u* → 0.5 where
r ≈ (1+r_cap)/2 ≈ 0.56, NOT r_cap, so the raw charged area would jump at
onset. Physically, separation near onset is weak/intermittent; numerically,
IPOPT needs continuity. So the charge is ramped in the excess:

    h = smooth_floor(tan θ_max − tan θ_sep)                    (geometry.smooth_floor, tau default)
    λ = h² / (h² + RAMP²)          RAMP = tan 15° − tan 12° ≈ 0.0553   ("~3° of excess")

λ is 0 below onset, ~0.83 at the current champion (θ_max ≈ 18.5° after the
r_cap fix in §3), → 1 for strongly separated afterbodies. RAMP is declared
data, adjustable.

**The drag term** (a drag AREA, D/q in m², constant with V at our Re/M):

    base_drag_area_m2 = CD_BASE · λ · A_charged
    CD_BASE = 0.159

CD_BASE matches asb 4.2.10's `fuselage_base_drag_coefficient` at M → 0
(MIL-HDBK-762, Fig 5-140 base-pressure data), per HANDOFF's suggestion 3, so
Tier 2's AeroBuildup cross-check compares like with like. **Label: declared,
uncalibrated.** Applying a blunt-base coefficient to a separated-boattail
effective base is the standard Hoerner-style bookkeeping, not a calibration.

**Symbolic guards** (all forced by iterates outside the feasible box, the
lesson of HANDOFF issue 3 / the boom NaN):

- `tail_len` enters denominators → `smooth_floor(tail_len)` first (the
  integrated topology's tail_len is a difference of design variables).
- `1 − ρ` goes negative whenever θ_max < θ_sep → `sqrt(smooth_floor(1 − ρ))`.
  The resulting garbage u* is harmless because λ = 0 kills the charge there;
  the guard exists so the sqrt is finite, not so u* is meaningful.
- Never a bare `max` anywhere — `smooth_floor` only.

## 2. What it is NOT charging (scope honesty)

- The **nose** is still assumed attached — the `pod_nose ≥ 1.0·d_eq` floor
  remains a proxy, unchanged. Out of scope; noted so nobody thinks the
  afterbody term covers it.
- The **boom** tip sockets into the tail block → occluded, no base term.
- No pressure-gradient interaction between wing saddle and afterbody — this is
  a body-alone correlation.

## 3. Geometry fix shipped in the same change: r_cap derived from the socket

The boom is 12 mm OD; the champion's cap is r_cap·d_eq ≈ 7.4 mm — **the boom
is larger than the cap it sockets into** (HANDOFF's flagged inconsistency).
Resolution: in pod_boom topology the cap IS the boom socket, so

    r_cap = boom_od / d_eq          (symbolic — d_eq is a design expression)

`loft()` already runs on `aerosandbox.numpy`; a symbolic r_cap is safe. The
module docstring's "all radius multipliers are plain floats" sentence must be
updated — it is a description, not a mechanism. Integrated topology keeps
r_cap = 0.12 (tail-block joint, existing convention). Guard: assert/constrain
r_cap well below 1 is unnecessary in practice (d_eq ≈ 61 mm ≫ 12 mm) but the
loft should tolerate it; do not add a constraint row for a case the bounds
already exclude.

Two consequences, both intended:

- The socket cap is **fully occluded in both topologies by construction**, so
  base drag ONLY ever appears through the separation term — one mechanism, as
  decided.
- At the champion, r_cap moves 0.12 → ~0.195, so (1 − r_cap) drops and
  **θ_max moves 20.1° → ≈18.5° before any drag is charged**. Wetted area and
  volume shift slightly too. This alone moves every objective; see §8.

## 4. The fineness cap

    f = pod_length / d_eq ≤ 8      →  constraint row  length / (FINENESS_CAP · d_eq) ≤ 1
                                       (dimensionless, per the standing rule)

`FINENESS_CAP = 8.0`, declared on the aircraft beside `lift_to_drag_max`, and
in the same idiom: **a solve landing ON it is a defect report, not an
optimum.** Sourcing: Hoerner puts the real minimum-drag fineness band for a
body of revolution at ~6–7; the Hoerner FF's own artificial minimum is at
16.38; and the current model's fixed-volume stretch actually pays until f ≈ 9
(the FF slope stops beating √L wetted-area growth there — measured on the
formula, 2026-08-05). 8 sits above the physical band and the champion's 6.2,
and below the artefact optimum, so it clips the exploit while leaving the
expected afterbody-lengthening response room (§6 predicts f ≈ 7.2).

## 5. Implementation map

| where | what |
| --- | --- |
| `fuselage.py` | new `afterbody_terms(d_eq, tail_len, r_cap, cd_base=0.159, theta_sep_deg=12.0, ramp=0.0553) -> dict` beside `body_dict` (it owns the fineness→FF derivation already; afterbody physics lives with it). Returns `{"base_drag_area_m2": ...}`. Symbolic-safe (asb.numpy + geometry.smooth_floor). |
| `fuselage.loft` | accept symbolic `r_cap` (no code change expected beyond the docstring; verify). |
| `aircraft.py` (`vtail_sample`) | `parasite_bodies`: compute r_cap per §3, pass it to `_pod_loft`/`loft`, merge `afterbody_terms(...)` keys into the pod dict. `geometry_constraints`: add the fineness row (§4). `pod_tail ≥ 1.8·d_eq` floor: UNTOUCHED this change (§7). Declare `FINENESS_CAP`, and the afterbody constants if they live at aircraft level — prefer module-level constants in `fuselage.py` since they are family physics, not aircraft choices. |
| `aero.body_cd0` | read the additive key: accumulate `d_extra += b.get("base_drag_area_m2", 0.0)`; return `(EXCRESCENCE·d + d_extra)/s_ref`. **The base term does NOT get the 1.08 excrescence factor** — it is not a skin-friction excrescence. `aero.py` imports plain numpy; `b.get(..., 0.0)` and addition are the only operations, which are symbolic-transparent — compute NOTHING else there. |
| `dv=None` frozen baseline | unaffected by construction: the frozen dicts never gain the new key, `.get` defaults to 0, `tests/test_fuselage.py` 0.183 pin must stay green untouched. |
| diagnostics | champion re-eval records `afterbody: {theta_max_deg, u_star, lambda, base_drag_area_m2, share_of_body_drag}` in `run.json`; report gets a line beside the body-drag buildup. Computed numerically at the champion point, not extracted from the graph. |
| docs | MODEL_DETAILS §7 (the model, constants, sources); HANDOFF + FINDINGS comparability note (§8). |

## 6. Expected magnitudes at the 2026-08-05 champion (estimates, for checking the build — not targets)

With r_cap → 0.195, θ_max ≈ 18.5°, ρ ≈ 0.63, u* ≈ 0.20, r_sep ≈ 0.92,
λ ≈ 0.83:

    A_charged ≈ 2.4e-3 m²   →   base_drag_area ≈ 3.2e-4 m²
    ≈ +35% on body drag  ≈ +2% on total drag at 9.5 m/s  ≈ −2 to −3 min endurance

**Note this is 4× the +8% the HANDOFF scoping hinge suggested** — the
effective-base form charges the area at the separation station, which at ~19°
is most of the body's cross-section. That is the model being honest about a
separated afterbody, not a bug — but it means the optimizer's response will be
decisive, not marginal. Expected response: lengthen the tail toward
θ_max ≈ 12–14° (tail_len ≈ 155–175 mm from 110.6), landing near f ≈ 7.2 —
inside the f ≤ 8 cap, off the 1.8·d_eq floor. If the first battery does
roughly this, the mechanism is working; if pod_tail stays pinned, the term is
too weak and the constants need revisiting BEFORE the floor is trusted away.

## 7. Rollout — the floor stays one battery

Ship the term with `pod_tail ≥ 1.8·d_eq` untouched. The next battery then
answers, via machinery that already exists:

- `active_bounds` / the constraint's slack: is the floor inactive now?
- the afterbody diagnostics: did θ_max settle near the threshold?
- the champion delta: is it within shouting distance of §6's estimate?

If the floor is inactive → delete it in the following change as a **measured
no-op** (state the slack in the commit). If still pinned → the correlation is
too weak; revisit constants, do not delete the floor. This is the
measure-then-move sequence, chosen over same-change removal because with an
uncalibrated constant and no floor, the first battery's boat-tail would be set
entirely by a number nobody has validated.

## 8. Comparability — this moves every objective

Exactly like the vortex-core fix: the r_cap geometry change plus the new term
shift every objective, and flatness figures are not comparable across it. The
run that first carries this change must be flagged in HANDOFF the same way
("comparisons carry this"), and FINDINGS gets the entry after the battery, not
before. Do not compare the next champion's minutes against 142.087 without
naming this change as a cause.

## 9. Tests

1. Frozen fixture: existing `test_spec_fixture_bodies_frozen` passes untouched.
2. `afterbody_terms`: long tail (θ_max < 12°) → charge exactly 0 (to smooth_floor tolerance).
3. θ_max formula matches a finite-difference of the actual loft's radii (guards the closed form against the Hermite implementation drifting).
4. Monotonicity: charge strictly decreases as tail_len grows — the gradient the whole change exists to create.
5. Continuity at onset: charge → 0 smoothly as θ_max → θ_sep⁺ (no jump; evaluate a dense ramp across the threshold).
6. Symbolic safety: build through `casadi`/Opti and evaluate at nasty points — tail_len ≤ 0, θ_max < θ_sep — finite everywhere (the 1500-point box-sample idiom, scaled down).
7. `body_cd0`: additive key respected, absent key → bit-identical to today, base term NOT multiplied by EXCRESCENCE.
8. pod_boom loft cap width equals boom OD; integrated keeps 0.12.
9. Fineness row present and dimensionless (value ≈ 6.2/8 at the champion vector).
