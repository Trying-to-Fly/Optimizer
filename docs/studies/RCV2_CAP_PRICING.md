# Pricing the caps behind the rcv2 corners

> **STATUS: INTERIM — the battery that produces this is still running** (started
> 2026-08-07 00:26 local, 9-hour budget, branch `rcv2-cap-pricing`). Numbers
> below are every cell measured so far and nothing else. Raw data:
> `docs/studies/rcv2_cap_pricing/cells.jsonl`, one JSON line per cell, appended
> as each lands.
>
> **The headline is already a reversal, so read the caveat in §3 before acting
> on it.**

## 1. Why

The `20260806T031736` rcv2 battery spent **287.7 of its 417.5 minutes (69%)** on
ten members that produced nothing, all `Maximum_WallTime_Exceeded`. Three
studies returned no verdict (tail type, both candidates; fuselage topology; wing
dihedral) and the flatness sweep reported 2 of its 6 spans.

`tools/degeneracy.py` settled what those members are: **not degenerate** (cond
2.49, smallest singular value 0.41, LICQ holds) but **over-constrained corners**
— 18 rows violated at once, dominated by lift equilibrium and the static-margin
floor. FINDINGS §14.5.7 measured that more clock does not convert one.

HANDOFF names the remedy — raise chord, raise span, widen the SM window, or
carry less kit — and says it is the user's decision. **None of the four had a
price.** This measures them, on the recipe §14.5.8 validated on `vtail_sample`.

## 2. Stage A — do the corners still fail at the shipped caps?

Every member re-run on the current tree (`1ff0917`), 15-minute budget, one solve
per process, the configuration each member declares.

| member | battery verdict | here | minutes | SM | AUW kg |
|---|---|---|---|---|---|
| `nominal` | converged | **converged 105.818** | 2.64 | 0.0800 | 2.158 |
| `tail_conventional` | **no verdict** | **converged 100.867** | 4.73 | 0.0800 | 2.229 |
| `tail_ttail` | **no verdict** | **converged 98.118** | 3.50 | 0.0800 | 2.275 |
| `fuselage_integrated` | **no verdict** | **converged 102.001** | 2.44 | 0.0800 | 2.232 |

*(remaining members still running)*

**All four land on the same five limits at once**: `span` on its 2.0 m cap,
`c_root` on its 0.275 m cap, `cs_frac` on its 0.4 upper bound, `ballast_kg` on
zero, and the static margin **exactly on its 0.0800 floor** — which is what a
binding constraint looks like (§14.5.8: the relaxed corners "both land exactly
on whatever floor they are given"). So the aeroplane IS in the corner the
battery's failures were attributed to. It simply solves there now, in 2-5
minutes.

## 3. The caveat that has to be read first

**The battery ran on a tree that has since been reverted.**

| | |
|---|---|
| battery started | 2026-08-06 03:17 |
| the ordering-row rescale reverted | 2026-08-06 08:22 (`1363ea8`) |

That rescale was **provably solution-preserving** (nine converged members
matched to eight significant figures) and **cost ~45% in solve time**; it took
`winglet_study__off` from 5.18 to 27.50 min and pushed
`winglet_study__continuous_cant` — which had converged in 11.97 min — past its
30-minute budget while still converging. The battery ran with it in place; the
revert landed five hours later.

So an unknown share of the ten lost members was **that regression, not a cap**,
and the four converged members above are consistent with the share being large.

The revert commit already drew the line on its own evidence, and it is the line
this study has to keep drawing: genuine corners read *"dual blow-up: stuck, not
slow"*, while the regression's victim read *"the primal side stopped moving."*
`solve._convergence_trace` prints that reading and this harness records it.

**What the four converged rows do NOT license:** "the caps are fine." They
license "these four members are not cap-blocked on the current tree." Only the
members that still fail can be used to price a cap, which is what stages D and E
are for.

## 4. A second difference, smaller but real

The battery's discrete studies run **greedily** — each study solves with the
previously adopted values, so its `tail_conventional` member carried the adopted
prop and topology. The cells above carry each member's **declared baseline**
(incumbent prop `ancf_11x6`). Same label, different aeroplane.

Reproducing the greedy state is cheap and is planned: `solve.screen_discrete`
ranks the prop catalogue at the champion's operating point **with no NLP at
all**, so recovering the prop that battery would have adopted costs seconds. It
is not done yet, and until it is, a converged cell here does not prove the same
member converges in a battery.

## 5. What is still running

| stage | question |
|---|---|
| A | *(above)* — plus `dihedral_polyhedral2`, `printed_mass_x1.10` |
| B | what each of the four caps costs on the champion itself |
| C | `candidates_source` on the converged champion — **is a converged rcv2 design airworthy at all**, or does its sweep have no legal point (FINDINGS §28)? |
| D | which relaxation unsticks each corner that DOES still fail |
| E | bisect the SM floor — "give up 0.01" and "give up 0.03" are different decisions |
| F | the four lost flatness spans |

## 6. Reproducing

    .runqueue/runlock uv run python tools/price_caps.py drive
    uv run python tools/price_caps.py report
    uv run python tools/price_caps.py cell --member tail_ttail --relax sm_floor_0.05
