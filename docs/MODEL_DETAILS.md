# Model Details

Companion to `OPTIMIZATION_CONCEPT.md`. That document defines the idea and formulation;
this one pins down each module's actual equations, data, and calibration. The framework
is **general-purpose**: aircraft-specific facts (hardware, construction method, geometry
architecture, mission) enter as input data, never as code. Values tagged **[sample]**
are for the test aircraft in `DESIGN_SPEC.md`, used to develop and validate the
framework — not baked-in assumptions.

---

## 1. Mass & CG model

**Contract:** given the design vector and an aircraft configuration, return a list of
`(mass, CG station)` pairs — one per component — from which AUW, aircraft CG, and every
component's sensitivity fall out. Mass and CG are one model, not two: the placement of
each mass is computed from the same geometry that generates it.

### 1.1 Decomposition

| Group | Treatment |
|---|---|
| Fixed equipment | Per-aircraft input list of (mass, station). Stations may themselves be design variables (e.g. battery tray position). **[sample]** battery 430 g, motor+prop 190 g, ESC 80 g, servos ~48 g, FC/GPS/RX 60 g, hardware/misc 50 g ≈ 858 g total. |
| Printed lifting surfaces (wing, tail) | Physics-based decomposition with calibrated constants — §1.2. |
| Spars | Continuously sized design variables with structural constraints — §1.3. |
| Boom | Linear density × length: mass responds to the tail-arm variable. **[sample]** 12×10 woven CF ≈ 56 g/m. |
| Fuselage/pod | Constant per aircraft for now (**[sample]** 250 g); parameterize only if/when fuselage geometry enters the design space. |
| Ballast | Design variable, ideally driven to zero. |

### 1.2 Printed-surface mass model

For skin-and-printed-ribs construction (no slicer infill), each physical piece scales
differently with geometry — this is what makes the optimizer's area/chord/span trades
meaningful rather than artifacts of a lumped `k·S^a` fit:

```
m_surface = f_finish × [ k_skin·S_wet  +  k_rib·b·c̄²/p_rib  +  k_joint·b/L_sec  +  m_overhead ]
```

| Term | Scaling logic |
|---|---|
| `k_skin·S_wet` | Skin mass ∝ wetted area. S_wet computed from the actual section perimeter (≈ 2.05 × planform area for ~9% t/c). Single-perimeter LW-PLA ballpark ≈ 250–300 g/m² — calibration replaces this guess. |
| `k_rib·b·c̄²/p_rib` | Ribs at fixed spanwise pitch `p_rib`; each rib's mass ∝ airfoil cross-section area ∝ chord². Punishes chord specifically. |
| `k_joint·b/L_sec` | Print-section joints (lip + pins + glue) per section of length `L_sec`. Modeled **continuously** (not ceil'd) to stay differentiable; round to integer sections in post-processing. |
| `m_overhead` | Per-surface constant: servo mounts, root tabs, bolt blocks, tips/winglets, hinge hardware. |
| `f_finish` | ≈ 1.05 on printed terms: epoxy, CA hinges, tape seals — real and always forgotten. |

The constants `{k_skin, k_rib, p_rib, k_joint, L_sec, m_overhead, f_finish}` form a
**construction profile** — one per material/printer/print-strategy combination, supplied
as input data and calibrated per §1.4. The tool ships with the LW-PLA/A1 profile
derived from the sample aircraft.

Geometry architecture (e.g. the sample plane's constant-chord center section + tapered
outer panels, spar/joint layout) is likewise part of the aircraft configuration, not
the code: the parameterized-geometry module maps the design vector onto whatever
architecture the config declares, and the mass model consumes the result.

**Sanity anchor [sample]:** skin ≈ 0.73 m² × 270 g/m² ≈ 197 g, leaving ~250 g of the
450 g wing budget for ribs + joints + overhead + spar sockets — plausible for this
construction; calibration pins it down.

### 1.3 Spar model — continuous sizing

Spar dimensions are **design variables**, not fixed hardware:

- Variables: outer diameter and wall thickness per spar segment (center / outer, per
  the architecture config).
- Mass: `ρ_CF · π/4 · (OD² − ID²) · length`, ρ_CF ≈ 1.6 g/cm³; segment lengths follow
  the architecture (e.g. outer spar to 85% of outer panel).
- Constraints (these replace the "within fixed-tube capability" phrasing in the
  concept doc's constraint table):
  - Root bending stress at limit load (n ≈ 5 g): `σ = M·r/I ≤ σ_allow / SF`
    (woven CF tube allowable ~350–500 MPa; keep SF conservative until validated).
  - Tip deflection at limit load ≤ cap (e.g. ~5% of semi-span).
  - Optional: torsion (aileron reaction), local socket bearing.
- The optimizer drives the spar to the constraint boundary — i.e. sized-to-load — and
  the shadow prices reveal what stiffness/strength actually costs in minutes.
- **Post-processing:** round the converged spar to the nearest real catalog tube,
  re-verify constraints, and re-evaluate endurance. The continuous optimum is the
  guide; the catalog tube is what gets built.

### 1.4 Calibration plan (status: nothing sliced yet)

1. Generate 2–3 wing sections of the sample aircraft at different chords (e.g. 180 /
   220 / 260 mm), slice in Bambu Studio with the real LW-PLA profile.
2. Take mass from slicer **filament length × measured g/m** (from a flow-calibration
   print) rather than the slicer's mass estimate — foaming filaments make the slicer's
   density/flow assumptions the dominant error.
3. Fit `k_skin` and `k_rib` by regression on the decomposition; `k_joint` and
   `m_overhead` from slicing the joint features and fittings directly.
4. When real printed parts exist, weigh them: **reality factor** = weighed / slicer,
   applied globally and tracked over time. Slicer data builds the model; the scale
   corrects it.

### 1.5 Margin policy — sensitivity, not padding

No mass-growth factor is baked into the optimization. Instead, every result reports:

- **Shadow price**: minutes of endurance per gram of printed structure (free from the
  gradient optimizer).
- **±10% re-solve**: re-run the optimization with printed-structure mass scaled ±10%;
  report the endurance delta and — more importantly — whether the **active constraint
  set changes** (a design that flips from stall-limited to weight-limited under +10%
  is fragile in a way the endurance number alone won't show).

### 1.6 CG output

Each component's CG comes from its own geometry at station-level fidelity (skin at the
surface's area centroid, spar at segment midpoint, fixed equipment at declared
stations). Gram-level precision is pointless; what matters is that CG *moves correctly*
when the optimizer moves geometry — that coupling (tail arm ↔ ballast ↔ weight) is the
reason this model exists.

---

## 2. Propulsion & energy model

**Contract:** given airspeed `V`, required thrust `T` (= trimmed drag from the aero
module), and a powertrain config, return electrical power draw `P_elec` plus
diagnostics (RPM, advance ratio `J`, per-stage efficiencies). The module is
objective-agnostic; mission evaluators (§5) compose it — e.g. the endurance mission's
`endurance = E_usable / (P_elec + P_avionics)`.

### 2.1 Chain, stage by stage

| Stage | Model |
|---|---|
| Propeller | **Proxy data table**: published APC performance data fit as smooth differentiable surfaces **CT(J, Re), CP(J, Re)** — advance ratio *and* blade Reynolds at 75% span (§2.1.1). The whole published catalogue ships (443 tables, `planeopt props`), so prop choice is a design decision, not a data limit. **[sample]** Aeronaut CAM 11×6 folding → APC 11×6, times a fixed folding-prop derate ≈ 0.95 (root cutout, hub, fold hinges). |
| Motor | Equivalent circuit from config (Kv, R, I0): `Q = Kt(I−I0)`, `RPM = Kv(V_bus − IR)` — AeroSandbox's `motor_electric_performance` implements exactly this. **[sample]** D3548 900 kV; R and I0 from vendor data, tagged as uncertain (vendor values run optimistic). |
| ESC | Constant efficiency ≈ 0.95. |
| Battery | Fixed bus voltage at discharge-average (**[sample]** 3.7 V/cell → 14.8 V), not full-charge voltage. |

Coupling into the optimizer: prop RPM is an additional variable with a thrust-match
equality constraint (`CT(J,Re)·ρ·n²·D⁴ = T`); shaft power then follows from CP(J,Re),
and the motor circuit yields current and `P_elec`. This keeps everything smooth and
lets the optimizer *see* the prop leaving its efficient advance-ratio range as cruise
speed moves — which a fixed chain efficiency would hide.

### 2.1.1 Why Reynolds is the second fit variable (2026-07-28)

APC tabulates each prop across a wide RPM sweep, and at a fixed advance ratio CT and
CP drift systematically with Reynolds. The original fit was `CT(J)` alone over a
hardcoded RPM window, which forced a choice no single constant can make honestly: the
window has to sit on the operating point, but the right centre depends on the aircraft
*and* on the prop — a 5″ prop cruises above 15 000 rpm, a 22″ prop below 4 000. With
one catalogue-wide window the shipped fits were measurably wrong where it mattered:
against raw APC rows in the sample plane's own cruise band, the 11×7E fit carried
**6.9% efficiency error**, enough to move endurance by several minutes.

Fitting Reynolds as a second variable removes the window entirely — every RPM block is
data, and the model is evaluated at whatever Reynolds the operating point actually has.
Measured the same way, error drops to **0.36%** (catalogue median 1.2%).

Reynolds costs nothing extra to carry, because it follows from the operating point.
The blade at 75% span sees `W₇₅ = n·D·√((0.75π)² + J²)`, so

```
Re = re_coeff · n · √((0.75π)² + J²)        n in rev/s
```

with `re_coeff = (ρ/μ)·c₇₅·D` a per-prop constant. Backed out of APC's own Reynolds
column it is constant to ~0.2% across every prop and RPM block, so it is **stored, not
modelled**. Both fits are nested-Horner polynomials (degree 3 in J, 2 in log Re), which
keeps them differentiable and identical through the numeric and CasADi-symbolic paths.

Two filters apply at ingest: rows above tip Mach 0.75 are dropped (a polynomial cannot
follow transonic drag rise), and APC's marine props are excluded by name rather than by
accident — they are the same file format in a different fluid.

### 2.2 Energy accounting

```
E_usable = capacity × V_nominal × usable_fraction
```

**[sample]** 4.0 Ah × 14.8 V × 0.80 ≈ 47.4 Wh. Climb, launch, and reserve are outside
the model; mission figures are comparative single-operating-point numbers, not
flight-plan promises. `P_avionics` is a constant config value (servos + FC + RX,
~2–4 W).

### 2.3 Uncertainty posture — no measurement path

There is no bench wattmeter and no planned calibration measurement, so the propulsion
chain stays datasheet/data-table only. Consequences, stated explicitly:

- Chain efficiency is the **dominant uncertainty** of the whole program (mass is
  calibratable via the slicer; this is not).
- Reporting mirrors the mass-margin policy: re-solve at ±10% chain efficiency and
  report the endurance delta plus any active-constraint-set change.
- Because every candidate shares the same propulsion model, **design ranking is far
  more trustworthy than absolute minutes** — conclusions should be phrased as "A beats
  B by X%" rather than "A flies N minutes." The advance-ratio diagnostic (cruise J vs.
  peak-η J) plus `re_75` / `re_in_range` are the sanity checks that the proxy table is
  being read inside the region it was fitted on.
- **A ranking is only comparable within one propulsion model.** The 2026-07-27 run
  (§FINDINGS) is the cautionary case: the prop was freed as a discrete study in the
  same run whose airframe changed, so a +11 min "wing win" was almost entirely a prop
  swap. When the propulsion side changes — table, fit, candidate list — the previous
  champion must be re-solved under the new model before any delta is quoted.
- Rigid APC blades stand in for folding CAM blades behind a flat 0.95 derate, and the
  motor's R and I₀ are vendor figures that run optimistic. **Better tables do not touch
  either.** No amount of catalogue coverage substitutes for the bench wattmeter this
  program has deliberately declined; coverage buys *choice*, not accuracy.

### 2.4 Installation effects — declared per-mount factors (2026-07-24)

The motor mount (pusher / puller / future variants) is a discrete candidate
list in `discrete_options` (§6.3). Mass placement is exact (the motor
PointMass rides the declared mount — boom tip vs pod nose — through the
ordinary mass/CG machinery). The installation aerodynamics, which no
module can compute at this fidelity, enter as **declared per-mount
factors** (`MOUNT_EFFECTS`, uncalibrated ballparks the study prices):

- **Pusher**: prop-efficiency derate (**[sample]** 0.95 — the prop works in
  the boom + tail wake), composed multiplicatively into the prop's
  `folding_derate`. Note: every run before 2026-07-24 silently omitted this
  penalty (§3.5 listed it as unmodeled), so absolute minutes drop ~5%
  against older FINDINGS entries; rankings are unaffected.
- **Puller**: clean inflow (derate 1.0), but the slipstream scrubs the pod —
  declared drag factor (**[sample]** ×1.10) on the pod body's form factor;
  wetted area itself is untouched.

Unmodeled either way and left to build judgment: cooling, prop ground/hand
clearance, folding-blade behavior against the pod, noise.

---

## 3. Aero & trim model

**Contract:** given geometry, mass/CG, and an operating point (V, α, control
deflections), return lift, drag (all sources), pitching moment, and stability
derivatives — smooth and differentiable throughout.

### 3.1 Drag and lift buildup

| Source | Method |
|---|---|
| Induced drag, lift, moments, downwash at tail | VLM on the full lifting configuration (wing + V-tail). Span efficiency and wing–tail interference come out of the same solve. |
| Profile drag of lifting surfaces | Strip-theory: **NeuralFoil** evaluated per spanwise station at local (CL, Re). Differentiable, no external runs; one-off XFOIL spot-checks per champion airfoil remain cheap insurance but are not part of the loop. |
| Fuselage, boom, interference | Component buildup: flat-plate Cf × form factor × wetted area per body, plus an interference/excrescence margin (~5–10%) for saddle, hatch lips, wires, hinge gaps. Config-supplied wetted areas. |

### 3.2 Surface finish — dual evaluation

Printed layer lines can destroy the laminar runs that airfoils in this class (e.g.
SD7037) depend on, so every champion is evaluated twice:

- **Optimize on smooth polars** (NeuralFoil, natural transition).
- **Re-evaluate with forced transition** (NeuralFoil's forced-transition / low n_crit
  inputs, trip near the LE) and report both endurance numbers.
- **Rejection rule:** a design whose *ranking* among candidates flips when tripped is
  laminar-fragile and is rejected regardless of its smooth-polar performance.

### 3.3 Trim — explicit control deflection

The ruddervators are modeled as real control surfaces in the geometry, and trim is
part of the optimization state:

- Symmetric ruddervator deflection δ_trim is a free variable at each operating point.
- Equality constraint: pitching moment about the *mass-model-produced* CG = 0 at cruise.
- Inequality: δ_trim stays well inside the physical throw — **[sample]** equivalent TE
  deflection ≤ ⅓ of the ±12 mm low-rate throw, reserving the rest for maneuver and gust.
- Trim drag is then real drag from the VLM + strip solve, not an estimate.

### 3.4 Stability quantities

- **Neutral point / static margin:** from the same VLM (dCm/dCL), differentiable, so
  the static-margin window is an ordinary smooth constraint against the mass model's CG.
- **Stall / CL_max:** critical-section method — at the stall condition no spanwise
  station may exceed its local NeuralFoil cl_max. Implemented (2026-07-23) as:
  Schrenk spanwise loading + washout increment (a_2d ≈ 5.7/rad) over stations taken
  from the wing's cross-sections and panel midpoints; local cl_max(Re) from a
  per-airfoil log-linear fit of NeuralFoil maxima; constraint via smooth-max
  (log-sum-exp). Captures taper/washout/planform-shape effects and doubles as the
  tip-stall diagnostic (the report plots cl/cl_max spanwise at stall). Documented
  approximation: Schrenk loading, not the LL distribution.
- **Gust margin:** CL_cruise ≤ ~0.7 × CL_max (from the concept doc's trim row).
- **Lateral-directional:** not dynamically modeled. A declared vertical-tail-volume
  floor stands in as the constraint (§8 — V-tail effective vertical area
  S·sin²Γ with the V-angle free; conventional/T fin area directly); flow5 and
  flight test own the rest.

### 3.5 Known fidelity limits (restated from the concept doc)

VLM + 2D strip corrections; the pusher prop's wake operation is priced only as a
declared efficiency derate (§2.4), not modeled; fuselage lift/moment contributions
are approximated by the buildup only. flow5 cross-checks champions; flight test
closes the gap.

### 3.6 Winglets and the projected-span cap

Winglets only make sense against a span cap: with span free, flat span always wins
on induced drag, so the optimizer never grows one. With a manufacturing cap on
**projected (front-view y) span**, a winglet raises effective aerodynamic span
without widening the footprint, paying with wetted area, mass, and toe-setting risk.
The model lets the NLP referee that trade:

- **Representation**: the winglet is a **separate `asb.Wing`** ("winglet") rooted at
  the wing tip — not extra tip xsecs. Feasibility test (2026-07): LiftingLine handles
  the tip junction cleanly either way, but the in-wing variant corrupts the VLM
  cross-check; the separate surface also keeps the Schrenk stations, the dihedral
  proxy, `Wing.span()`, and per-surface mass accounting clean by construction.
  Variables (aircraft-level): length, cant (floored at ~55 deg so the panel can't
  become a stall-model-invisible span extension), root-chord ratio, taper, toe.
- **Span bookkeeping**: the architecture places panels by **arc length** (y from
  cos(dihedral), z from sin) — the `span` variable is material span, and
  `b_ref` = projected span. The cap applies to projected span *including* the
  winglet's y-projection; material span is bounded by the same cap. Consequence
  observed at the 2.2 m sample cap: the optimizer cants outer panels (polyhedral)
  to tuck full material span + winglet inside the footprint.
- **Induced-drag fidelity**: LL sees the nonplanar benefit (k_induced fell ~7.5%
  for a 0.15 m winglet in the feasibility test) but is *conservative* vs an
  inviscid VLM fit (~12%). Champions get a numeric VLM second opinion
  (`aero.vlm_induced_check`, CD = CD0 + k·CL² fit over a 6-alpha sweep, on/off
  comparison).

  **That second opinion is an ENSEMBLE of three meshes, and it self-certifies.**
  AeroSandbox's default spanwise spacing (`cosspace` within each wing section)
  bunches panels against section boundaries; on this wing's four unequal sections
  that leaves near-coincident horseshoes, a near-singular AIC and a circulation
  that is simply wrong — every run before 2026-07-31 reported a NEGATIVE
  `k_induced`, i.e. an inviscid wing producing thrust (FINDINGS §16.1). Uniform
  spanwise panels fix it, but individual meshes still blow up sporadically on
  high-cant geometries, and a blown-up mesh looks perfectly physical on its own.
  So the reported value is the consensus of the meshes that agree with the
  median, `per_mesh` carries all three for audit, and a configuration whose
  meshes cannot agree ships with `reliable: false` and a reason rather than a
  number. `cd0_inviscid` is the fit intercept and should be ~0: an inviscid solve
  has no viscous drag, so its magnitude is fit residual, not drag.
- **Exclusions, all conservative**: winglet contributes nothing to the Schrenk
  critical-section stall model, the effective-dihedral floor, or s_ref. Its own
  stall risk is handled by a toe bound (±3 deg) and a 60k mean-chord Re floor
  (relaxed vs the 90k wing-tip rule) — a per-section winglet loading limit is a
  known gap (FINDINGS).
- **Dihedral credit** (same change): each panel's contribution to the lateral floor
  is now `(180/π)·sin·cos` of its angle — ≈ the raw angle at small angles, →0
  vertical — so a near-vertical panel (continuous-cant study, `d3_max_deg`≈88)
  cannot game the floor.
- **Mass**: printed pair via its own ConstructionProfile plus explicit tip-socket
  joiners (~16 g/aircraft, sample) — at sample constants the pair costs ~55 g,
  which is the hurdle the drag saving must clear in the on/off study.

---

## 4. Constraint formalization

Assembly of every constraint as it actually enters the NLP. Mission-type numbers
(stall limit, wind, static-margin window, ballast cap) are **mission/config inputs**;
[sample] values shown are the test aircraft's.

**Equalities** (structure of the problem, not "limits"):

| Constraint | Form |
|---|---|
| Weight closure | Implicit — AUW and CG are composed from the mass model, never free variables. |
| Lift = weight | At each operating point. |
| Pitch trim | Cm(CG) = 0 at cruise, via δ_trim (§3.3). |
| Thrust match | CT(J)·ρ·n²·D⁴ = D_trimmed at cruise, via prop RPM (§2.1). |

**Inequalities:**

| Constraint | Form | [sample] |
|---|---|---|
| Stall | Second operating point at V_stall_limit, lift = weight; critical-section: smooth-max over stations of (cl / cl_max_local) ≤ 1 | V_stall ≤ 8 m/s |
| Min cruise speed | V_cruise ≥ V_wind + penetration margin (the wind model for endurance-class objectives — see §5.2) | ≥ ~9–10 m/s |
| Static margin | SM_min ≤ (x_np − x_cg)/MAC ≤ SM_max | 8–15% |
| Gust margin | CL_cruise ≤ 0.7 × CL_max | — |
| Trim authority | deflection ≤ (⅓ throw)/control chord — the degree cap is derived from the free hinge fraction (§8) | ±12 mm throw |
| Ballast | 0 ≤ m_ballast ≤ cap | 70 g |
| Tip Reynolds | Re_tip ≥ floor (wing); tail/fin mean chord ≥ relaxed floor (§8) | 90k / 60k |
| Spar stress | σ_root ≤ σ_allow/SF at limit load (§1.3) | n = 5 g |
| Spar stiffness | tip deflection ≤ cap at limit load | ~5% semi-span |
| Spar fit | dihedral-curve sag across each straight spar's run + spar OD ≤ usable section depth (§9) | 0.70 × t/c × c |
| Manufacturing | chord ≤ printable max; battery-bay volume respected (pod frozen) | A1: chord ≲ 245 mm |
| Directional | vertical-tail volume ≥ declared floor (§8; V-tail counts S·sin²Γ) | Vv ≥ 0.030 |
| Bounds | span, taper, chord, speeds, spar dims — simple box bounds | span 1.5–2.2 m etc. |

Smoothness rule: anything involving a max over stations or a table lookup uses a
smooth surrogate (log-sum-exp, fitted curves) — no `if`, no `ceil`, no interpolation
kinks inside the loop.

---

## 5. Mission layer — objectives

The framework owns no objective. A **mission config** declares: the objective (from
the library below), the operating point(s) at which it is evaluated, the mission-type
constraint values of §4 (stall limit, wind, ballast cap, static-margin window), and
any secondary quantities to sweep (§5.3). The physics modules (§1–3) are
objective-agnostic contracts; mission evaluators compose their outputs. Two
principles bind every library entry:

- **Never a proxy** — optimize the real mission quantity (minutes, km, m/s, Wh/km),
  never L/D or CL^1.5/CD as a stand-in. Classic results (best-endurance speed near
  max CL^1.5/CD, speed-to-fly shifting into a headwind) must emerge, not be assumed.
- **Operating point co-optimized** — the speed/CL/trim at which the objective is
  evaluated is always part of the design vector.

### 5.1 Objective library (v1)

| Objective | Evaluator | Wind treatment |
|---|---|---|
| **Endurance** *(sample mission)* | maximize E_usable / (P_elec + P_avionics) | Constraint: V ≥ V_wind + penetration margin. Wind doesn't change loiter power at a given airspeed; *whether this constraint is active* is itself a key output. |
| **Range** | maximize E_usable × (V − V_wind) / (P_elec + P_avionics) — distance over ground | In the objective (ground speed). Fly-faster-into-headwind emerges naturally. |
| **Min energy per distance** | minimize (P_elec + P_avionics) / (V − V_wind) — Wh/km | In the objective. Dual of range at fixed E_usable; kept as its own entry for battery-sizing and payload studies where E_usable varies. |
| **Max cruise speed** | maximize V subject to *sustained* operation: continuous motor/ESC current ratings, config throttle-fraction cap | Irrelevant (airspeed objective). |
| **Raw max speed** | maximize V at full throttle: P_available = P_required equality, burst current limit | Irrelevant. Flutter/divergence are beyond model fidelity — report V_max against a declared config placard speed rather than pretending to predict the structural limit. |

Every entry reuses the same trim/stall/structure/manufacturing constraints of §4,
evaluated at its own operating point. Extending the library means writing a new
evaluator over the same module contracts — no module changes.

### 5.2 Wind

Objective-dependent, defined per library entry above — there is no global wind rule.
V_wind and the penetration margin are mission inputs (**[sample]** ~4 m/s wind +
margin → V_min ≈ 9–10 m/s for the endurance mission).

### 5.3 Competing objectives — two mechanisms

- **ε-constraint sweeps (the principled path):** always solve for ONE objective; each
  other cared-about quantity becomes a constraint whose bound is swept (e.g. maximize
  endurance s.t. cruise speed ≥ X, sweep X) → a true Pareto front from repeated,
  warm-started solves. The shadow price at each point is the local exchange rate
  between the objectives — often the most decision-relevant number produced.
- **Normalized weighted sum (the quick look):** one solve on Σ wᵢ·(objᵢ / objᵢ*),
  each term normalized by its single-objective optimum so weights are meaningful
  across units. Cannot reach non-convex parts of the front — treat as exploration,
  not conclusion.

The champion report (§6.4) is identical regardless of mechanism.

---

## 6. Optimization mechanics

### 6.1 Solver and problem shape

AeroSandbox `Opti` (CasADi + IPOPT), exact gradients by automatic differentiation
end-to-end — which is precisely why every module above insists on smoothness. The
mission's operating point(s) and the stall-check point live in one NLP. Variables get
scale hints (log-scale for strictly positive quantities like masses and chords) so
IPOPT sees O(1) numbers.

### 6.2 Initialization and local optima

The sample aircraft is the default initial guess. Because the problem is small,
**multi-start** from a handful of perturbed initial points is cheap insurance against
local optima; disagreement between starts is itself a reported diagnostic.

### 6.3 Discrete outer loop

Plain enumeration: one full continuous solve per discrete candidate (airfoil, or any
future configuration question), then champions compared side-by-side under the full
reporting battery. No integer programming, ever.

### 6.4 The champion report

Every champion gets the same battery, assembling the diagnostics from all modules:

1. Design vector + active constraint set + shadow prices in objective units
   (e.g. minutes/gram, minutes/mm for the endurance mission).
2. Re-solves: printed mass ±10% (§1.5), chain efficiency ±10% (§2.3), tripped polars
   (§3.2) — each reporting the objective delta **and any active-constraint-set change**.
3. Sanity panel: span efficiency, tip lift distribution, cruise CL vs. drag bucket,
   trim drag fraction, advance ratio vs. peak-η J, spar rounded to catalog tube.
4. Flatness: 1D sweep of span around the optimum **with all other variables
   re-optimized at each point** (a frozen-variable sweep exaggerates curvature);
   on a plateau, prefer the smaller/stiffer/cheaper end.
5. Winglet study (§3.6, when the aircraft enables winglets): paired winglet-off
   re-optimization at the same cap (objective delta), VLM induced-drag second
   opinion at the champion geometry, and a continuous-cant cross-check (outer
   panel freed to ~88 deg, explicit winglet off — indicative only, since the
   Schrenk stations include the canted panel).
6. Discrete studies (§6.3, when the aircraft declares
   `discrete_options = {attr: [candidates]}` — fuselage topology §7.4, tail
   type §8, any future configuration question): one full re-optimization per
   declared alternative, run in declared order (greedy — each study inherits
   the previous studies' adopted values); a winner becomes the champion
   (per-candidate objective deltas and the adoption verdict reported either
   way in `discrete_studies`).

### 6.5 Phase 1 validation gate

Before any optimization: run the fixed sample aircraft through all models and check
plausibility. Important: the sample spec's performance figures (stall ~8.3 m/s,
cruise 80–110 W, endurance 30–40 min) are **rough estimates, not ground truth** —
agreement with them proves nothing. The gate's hard anchors are **published data from
real comparable aircraft** (1.5–2.2 m electric endurance types with logged cruise
power, printed-structure weights from published 3D-printed designs — collected in
`VALIDATION_ANCHORS.md`), forming plausibility bands for W/kg at cruise, Wh/km,
wing-loading-vs-stall-speed, and printed g/m² of wing area. The spec numbers serve
only as weak priors; a large model-vs-spec discrepancy triggers investigation, not
automatic model correction. Triage remains in order of calibratability: mass (slicer
data) → aero (XFOIL spot-check) → propulsion (uncalibratable; adjust posture, not
the model). Optimization results are not trusted until the model sits inside the
real-aircraft bands.

---

## 7. Fuselage — parametric loft

Frozen through M4.5, the fuselage becomes designable via a **parametric loft**
(decided 2026-07-23): declared cross-sections and guide stations loft into an
`asb.Fuselage` whose driving parameters the NLP optimizes continuously, with a
discrete **topology study** (§7.4) covering the one non-continuous question.
First iteration varies lengths + cross-section scale; section shape exponents
stay fixed.

### 7.1 Geometry — the loft IS the model

`planeopt.fuselage.loft`: superellipse cross-sections along the station line,
a **streamlined family by construction** — the optimizer sizes the fuselage,
the family guarantees it looks like one. Nose: elliptical-arc radius growth,
tangent at the bay shoulder, section shape blending from circular at the tip
to the bay's rounded rectangle (shape 4). Bay: constant section. Tail:
cubic-Hermite **boat-tail** (tangent at both the shoulder and the 12 % end
cap — no straight cone), blending back to circular. Symbolic-safe (floats or
Opti variables; all station fractions and radius multipliers are plain
floats), and the NLP reads the loft's **own integrals** (`area_wetted()`,
`volume()`), so geometry and model cannot drift apart.

Sample-aircraft variables: `pod_nose`, `pod_bay`, `pod_tail` (lengths) and
`pod_xs` (cross-section scale on the spec's 68×88 mm). Anchor: the bay's aft
end is pinned at the wing-saddle joint station (0.410 m); the nose grows
forward from it, the tail cone aft. Defaults reproduce the spec pod exactly
(nose tip at station 0, length 585 mm); `dv=None` keeps returning the frozen
M1 baseline numbers forever (validation continuity — the 0.183 m² pod assumed
an untapered prism, so the loft's 0.135 m² is not a regression but a better
integral of the same shape).

### 7.2 Packaging constraints — floors are user data

Component envelopes (battery L×W×H, ESC/FC lengths) are **declared data —
user input in the app (M5)**; the sample carries spec values. Symbolic
constraints:

- inner bay section (printed wall + liner clearance per side) ≥ battery
  width/height + 4 mm;
- the battery (CG at `x_battery`) stays inside the bay with 3 mm end margins —
  these symbolic bounds are the real `x_battery` limits (its box bound is a
  wide backstop only), so CG travel and loft stretch trade against each other;
- bay ≥ battery + 50 mm (travel + leads); bay + cone root ≥ the full
  battery+ESC+FC stack;
- proportion floors (nose ≥ 1.0 d_eq, pod-boom boat-tail ≥ 1.8 d_eq): the
  flat-plate + form-factor model cannot rank end-cap *shape quality*, so
  plane-like proportions are imposed as geometry, not hoped for (the spec
  pod's 30 mm nose predates these — the `dv=None` fixture is exempt);
- pod-boom: an exposed boom must exist (pod tail cap + 100 mm ≤ tail block);
- **wing-saddle carry-through (no floating wing)**: the constant-section bay
  must physically carry the wing root — bay start ≤ LE − 10 mm and bay end ≥
  LE + 0.60 · c_root (the bay aft end is a variable, `pod_bay_end`, not an
  anchor since this rework) — and the pod top is *derived* as
  `SADDLE_EMBED − h/2`, embedding ~6 mm above the wing chord plane, so a
  shrunken pod can never leave the wing floating above the fuselage
  (2026-07-23 user requirement; unbuildable otherwise).

### 7.3 Aero and mass from the loft

Aero enters through the **existing validated flat-plate buildup** (§3.1), NOT
through LiftingLine: asb's LL adds its own fuselage model when one is attached,
which would double-count drag against the M1-validated buildup. The aero
Airplane stays wings-only; the loft attaches to a *viz twin* for the 3D
artifacts only. `fuselage.body_dict` supplies the buildup entry: form factor
from fineness (Hoerner, 1 + 60/f³ + f/400) × 1.08 interference, calibrated so
the spec pod reproduces its frozen 1.25 — slenderness becomes a real trade on
a preserved baseline. The Munk destabilizing dCm/dα (§3.4) now takes the
loft's symbolic volume inside the NLP.

Mass: pod = k_skin × S_wet + overhead (1.465 kg/m² + 50 g), calibrated to
reproduce the frozen 250 g at the spec loft — same uncalibrated-ballpark
caveat as the wing construction profile (§1.4). ESC/FC stations ride the loft
as length fractions of the spec layout; ballast rides the (possibly
stretched) nose tip.

The **boom is an outcome, not a constant**: it spans the pod's tail cap to
the tail block (station from `tail_arm`), so its mass (linear density × that
emergent length) and its drag entry (`fuselage.boom_body`, symbolic length)
both respond as the optimizer trades pod length, tail arm, and overall
aircraft length; `tail_arm` carries deliberately wide bounds so total length
is genuinely optimized.

### 7.4 Topology study — discrete outer loop

The aircraft declares a **list** of candidate topologies (an entry in
`discrete_options`, the generic declared-study mechanism of §6.3/§6.4 item 6)
— the CF boom is a candidate the study *prices*, never an assumption. Sample: `pod_boom` (lofted pod + CF boom, the spec
layout) and `integrated` (the pod's tail cone runs all the way to the tail
block — cone length derived from `tail_arm`, printed cone replaces the boom,
plus an internal 8 mm CF stiffener to keep the printed tail credible at this
fidelity); twin-boom or others slot in as more declared entries. Per §6.3,
plain enumeration: one full re-optimization per candidate; the winner becomes
the champion and the numeric re-evaluation runs with it. Reported in the
champion battery either way (§6.4 item 6) — this is how the app *suggests*
whether a boom is worth it.

### 7.5 CAD round-trip (imported fuselage)

The parametric loft (§7.1) is the recommendation engine; a real airplane's
fuselage is designed by a human. Workflow (decided 2026-07-23):

1. **Brief** — `planeopt brief <run> -a <aircraft>` renders `design_brief.md`
   from a champion run: packaging floors, length budgets and proportion
   floors, battery-CG window, fixed interfaces, and shadow-price deviation
   costs. Everything comes from declared data via the aircraft's optional
   `design_brief(dv, shadow_per_g)` hook — any archetype, any mission.
2. **CAD** — the user designs around the brief (SolidWorks or similar) and
   exports **.STEP**.
3. **Import + review** — `planeopt.cadimport.load_step` (optional `cad`
   extra: cadquery/OpenCascade) reads exact B-rep wetted area and volume plus
   a station scan; `planeopt.shapereview.review` applies the drag *rules*
   (nose fineness ≥ 1.0 d_eq, boat-tail half-angle ≤ 21° — set so the app's
   own floor-tight loft passes — fineness band 4–9) and prices the
   wetted-area delta vs the minimal loft through the skin-mass model and the
   mass shadow price. Honest scope: the flat-plate + FF model cannot rank
   surface sculpting, so the review checks rules and prices integrals — it
   does not pretend to CFD.
4. **Re-optimize** — the imported shape becomes the fuselage
   (`ImportedShape.body_dict` feeds the same buildup + Munk contract), with
   two scale variables (length, cross-section) so the app sizes the user's
   shape without mutating its character; scales pin to 1 to take it as-is.
   (NLP wiring lands with the first imported-fuselage aircraft.)

---

## 8. Tail — declared types, per-dimension surfaces

Through M4.6 the tail was one uniform `tail_scale` knob on the spec V-tail;
the fuselage-phase champion pinned it at its 0.70 floor, making the
parameterization the binding limitation. Decided 2026-07-23 (fifth session):
tail TYPE is the only discrete choice; everything inside a type is a
continuous per-dimension variable. `tail_scale` is retired.

### 8.1 Types — the discrete study

The aircraft declares `tail_type` plus a candidate list in
`discrete_options["tail_type"]` (**[sample]** `vtail`, `conventional`,
`ttail`), enumerated by the generic mechanism (§6.3): one full
re-optimization per type, winner adopted, all priced in `discrete_studies`.
Per type the generator produces consistently named surfaces so mass mapping
(§1.2) works by construction profile: `vtail` (tail profile) or `hstab`
(tail profile) + `fin` (fin profile — smaller overhead, no in-surface servo).
The T-tail additionally prices a declared stab-on-fin mount mass
(**[sample]** 20 g at the tail block) and mounts the hstab at the fin tip
(LL sees the raised surface leave the wing's downwash field).

### 8.2 Variables and placement

Free within a type: `t_span`, `t_c_root`, `t_taper`, `t_sweep` (in-plane LE
sweep), `t_dihedral` (V-angle, V-tail only), `cs_frac` (hinge/chord fraction,
0.2–0.4), and for conventional/T the fin's own `fin_height`, `fin_c_root`,
`fin_taper`, `fin_sweep`. The surface's **AC is placed exactly `tail_arm`
behind the wing AC including the sweep offset** (root LE at
`ac_x − s̄·tanΛ − 0.25·MAC`, with s̄ the arc distance to the MAC station), so
sweep cannot buy moment arm the boom-length accounting doesn't pay for.
Tail and fin mean chords carry a 60k Reynolds floor (relaxed vs the 90k
wing-tip rule — winglet precedent).

### 8.3 Trim surface and throw policy

The pitch surface is a real `ControlSurface` named by the aircraft
(`pitch_control_name`: "ruddervator" / "elevator") — the framework's trim
solve and NLP read the declared name, never a hardcoded one. Deflection
effectiveness and its drag increment come from asb's control-surface model
(effectiveness `1 − hinge^2.75`). The throw limit stays policy — trim uses
≤ ⅓ of the declared TE throw (**[sample]** ±12 mm) — but the *degree* cap is
now derived: `limit = (⅓·throw)/(cs_frac · t_c_mean)`. A larger hinge
fraction gains effectiveness per degree yet loses allowed degrees, so
`cs_frac` is a genuine trade, not a free knob. No servo-torque model
(decision 2026-07-23).

### 8.4 Directional floor

LL has no yaw axis: without a constraint, fins optimize to zero and V-tails
shed angle. A declared vertical-tail-volume floor stands in (§3.4):
`Vv = S_v_eff · l_v / (S_ref · b_proj) ≥ v_tail_volume_min`, with
`S_v_eff = S_tail·sin²Γ` for the V-tail (angle free) and the fin's area for
conventional/T; `l_v ≈ tail_arm` (CG sits near the wing AC at this
fidelity). **[sample]** floor 0.030 — provenance: the spec's own tail works
out to Vv = 0.034, and 0.02–0.04 is class practice.

---

## 9. Wing planform and dihedral (architecture v4)

Reworked 2026-07-26 (user decision). Two changes that deliberately pull in
opposite directions, each for its own reason:

- **Planform becomes smooth.** v2/v3's three independent chord ratios
  (`r1`–`r3`) sat on three *equal-width* panels. The ratios looked like
  freedom, but the widths were never optimizable at all — the breaks were an
  arbitrary discretization wearing a design vector's clothes. Chord is now one
  two-parameter curve (§9.1), and stations become a fidelity choice.
- **Dihedral may become piecewise.** The v3 smooth curve (§9.2) is retained as
  the incumbent, but a **two-panel** form (§9.3) is now a candidate beside it,
  priced by a study. The curve family provably cannot express the one shape
  that matters at a binding span cap: flat inboard with a hard-canted tip.

The user's constraint on the rework was that a **plain straight wing must stay
reachable**. It does, exactly — see the named members below.

### 9.1 Planform — one superellipse family

Chord over arc fraction η ∈ [0, 1] from root to tip:

    c(η) = c_root · [ λ + (1 − λ)·(1 − η^a)^(1/a) ]

Two variables, `taper` (λ) and `fullness` (a), replace three. Its named
members are **exact**, not approximations — which is what makes "let the
optimizer choose the planform" honest rather than a shape lottery:

| parameters | planform |
| --- | --- |
| λ = 1 (any a) | constant chord — a **rectangular wing** |
| a = 1 | **straight taper** — the classic trapezoid |
| a = 2, λ = 0 | a true **ellipse** |
| a > 2 | chord held out mid-span, dropped near the tip |

`fullness` is bounded [1, 4] and `taper` [0.35, 1.0], so the family spans
rectangular through elliptical to held-chord, and cannot invert.

**Leading-edge convention is a variable, not a decision.** The user asked for
straight-LE, straight-TE and straight-quarter-chord to all be available to the
optimizer. Rather than enumerate three discrete cases, one variable spans them
as interior points:

    x_le(η) = le_shear · (c_root − c(η))            le_shear ∈ [0, 1]

`le_shear = 0` is a straight LE (all chord change on the TE), `0.25` a straight
quarter-chord line, `1` a straight TE — and anything between is valid.

**Endpoint rule (CasADi).** `c(0) = c_root` and `c(1) = λ·c_root` hold for
every `a`, so both are returned analytically and never evaluated through the
symbolic power. Evaluating them would form `0^(1/a)` and `log 0`, whose
derivative with respect to `a` is NaN — which does not fail loudly, it poisons
the entire Jacobian. This is the same hazard as §9.2's `η^q` at η = 0.
`tests/test_wingcurve.py` pins it, and a 384-corner sweep of the variable
bounds confirms a NaN-free, Inf-free Jacobian in both dihedral forms.

**Aerodynamic centre.** Once the LE can shear, the wing AC no longer sits
0.25·c_mean behind the root LE, so the tail is now placed off the **true
area-weighted quarter-chord AC**, computed exactly from the trapezoidal panels
(`geometry.mac_and_ac`). Straight-TE moves the AC ~22 mm aft of straight-LE on
the sample wing: without this the tail would have collected moment arm the boom
length never paid for. `c_ref` is unchanged (still the mean chord, a
symbolic-safe MAC proxy) so static-margin numbers stay comparable with M4.x —
a known inconsistency, documented rather than silently fixed.

### 9.2 Dihedral form A — the smooth curve (v3 incumbent)

Unchanged from v3:

    δ(η) = dihedral_tip · η^d_exp        d_exp ∈ [0, 2]

`d_exp = 0` is exactly a single simple dihedral angle; `d_exp > 0` is a fully
curved wing, flat at the root (which the wing saddle wants) with curvature
building outboard. δ is sampled at each panel's midpoint.

Its build standard is the **straight spar**: the curve sags away from any
straight line drawn through it, so each spar run must carry that sag plus its
own diameter inside the usable section depth,

    sag(η) + spar_OD ≤ SPAR_DEPTH_FRACTION · t/c · c(η)

with curve height from the small-angle integral `z(η) = semi·δ_tip[rad]·
η^(q+1)/(q+1)` (≤ 11% high at the 20° tip cap; the family is convex, so the
checked stations bound the sag). At `d_exp = 0` sag is identically zero:
simple dihedral always fits. **[sample]** depth fraction 0.70.

### 9.3 Dihedral form B — two panels (`polyhedral2`)

One break, at the station the wing is jointed at anyway:

    δ(η) = dihedral_inner   for η < eta_break
           dihedral_outer   for η ≥ eta_break

`dihedral_inner` keeps the ordinary 20° cap. **`dihedral_outer` is free to
60°** — the point of the form. Panels place by *arc* length, so `span` is
material span and front-view width is Σ w·cos δ; canting the outer panel
therefore **spends projected span**, the quantity the manufacturing cap is
written against. At 55° cant a 2.0 m wing projects 1.744 m.

**Why this is not just "more dihedral freedom".** The v3 curve is monotone and
capped at 20° at the tip, so it cannot represent *flat inboard, steeply canted
outboard*. At a binding projected-span cap that shape is not a dihedral
distribution at all — it is a **blended winglet made of wing**: lifting area
outside the capped width, with no separate-surface junction and a continuous
chord. LiftingLine sees the nonplanar induced benefit (§3.6). The bolted-on
explicit winglet has been rejected twice (−0.50 and −0.96 min, FINDINGS §8/§9);
a blended tip is a different object and had never been priced.

**What it costs, so the study is honest:**

- **One spar joint per side.** Each panel is planar, so a straight spar fits
  each *with zero sag* — the §9.2 sag constraint is replaced by the ordinary
  fit check at each run's thinnest (outboard) station. The kink is carried by a
  joiner block instead: `DIHEDRAL_JOINER_KG` = 16 g per side, the same figure
  v2 charged at every break and v3 deleted along with them.
- **Projected span**, as above.
- **Roll-moment arm is now the projected y** of each panel centroid, not its
  arc distance. v3 used arc distance, where the two barely differ at 4°; at 60°
  it would hand a canted panel twice the arm it actually has, letting it game
  the lateral floor. This is a correction the new freedom *requires*.

**Cant ceiling of 60° is a MODEL limit, not a structural one.** Past roughly
that angle a Schrenk station on a near-vertical panel stops meaning anything
the critical-section stall method (§3.4) can use, and the wing would be
optimized against a stall model that cannot see it. Raising the cap requires
fixing that model first — the same caveat that keeps the continuous-cant
winglet cross-check indicative-only.

### 9.4 Shared structure

Both forms read one shared panel list (`_wing`), so geometry, constraints and
the mass model cannot drift apart. Stations come from `geometry.station_grid`:
`WING_STATIONS_INNER` + `WING_STATIONS_OUTER` (2 + 2), with a station landing
**exactly on the break** — so which panels are inboard is an index question and
nothing ever compares against a design-variable *value*. Outer stations are
sine-clustered toward the tip, where a superellipse does all its curving.

Station count is a **fidelity knob that costs RAM**: each station becomes an
`asb.WingXSec` that LiftingLine subdivides again, and one solve already peaks
near 13 GB (§`memory.py`). v4 is deliberately held at four panels / five
stations, so it buys a smooth planform, a free joint station and an optional
kink **without growing the CasADi graph at all**.

`eta_break` belongs to the wing, not to either dihedral form: a built wing is
jointed somewhere regardless, and it inherits the freedom v3 carried as
`center_width`. The forms differ in exactly one thing — whether the dihedral is
allowed to change across that joint — which is what makes the study a clean
comparison.

**Expect the distribution to stay a flat direction.** v3's champion converged
to `d_exp = 0` with spar-fit *inactive*: the optimizer sees no benefit from
dihedral at all (LL has no lateral DOF), so dihedral is driven purely by the
lateral-stability floor, which a uniform angle meets most cheaply. A mild
two-panel polyhedral should therefore land on the same uniform answer. The
result worth watching is the **hard-canted** one, where the mechanism is
induced drag at the span cap rather than dihedral distribution.
