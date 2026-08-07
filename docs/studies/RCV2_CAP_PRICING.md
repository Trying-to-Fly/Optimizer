# Pricing the caps behind the rcv2 corners

> **STATUS: INTERIM** — stages A, B and C are measured; the three stage-B cells
> the machine slept through are being re-measured and stage F is still to run.
> Branch `rcv2-cap-pricing`. Raw data: `docs/studies/rcv2_cap_pricing/cells.jsonl`,
> one JSON line per cell.

## 0. The two results, before anything else

1. **Every corner the battery lost converges here in 2-5 minutes.** All six
   members, including the three studies that returned no verdict and the exact
   member `degeneracy.py` was run on. Stage A cost ~19 minutes of solving for
   what cost that battery 287.7 minutes of nothing.
2. **Every failure this study produced was the laptop going to sleep**, not a
   constraint. IPOPT's guard is a WALL clock, so a suspended process is charged
   for the time it spends suspended. See §4 — it may also be the largest single
   explanation for the original battery's ten losses, and it is checkable there
   in one command.

## 1. Why

The `20260806T031736` rcv2 battery spent **287.7 of its 417.5 minutes (69%)** on
ten members that produced nothing, all `Maximum_WallTime_Exceeded`. Three
studies returned no verdict (tail type, both candidates; fuselage topology; wing
dihedral) and the flatness sweep reported 2 of its 6 spans.

`tools/degeneracy.py` settled what those members are: **not degenerate** (cond
2.49, LICQ holds) but **over-constrained corners** — 18 rows violated at once.
FINDINGS §14.5.7 measured that more clock does not convert one. HANDOFF names
the remedy — raise chord, raise span, widen the SM window, or carry less kit —
and says it is the user's decision. **None of the four had a price.**

## 2. Stage A — the corners do not reproduce

Current tree (`1ff0917`), 15-minute budget, one solve per process, each member
in the configuration it declares.

| member | battery | here | min | SM | AUW kg |
|---|---|---|---|---|---|
| `nominal` | converged | 105.818 | 2.64 | 0.0800 | 2.158 |
| `tail_conventional` | **no verdict** | **100.867** | 4.73 | 0.0800 | 2.229 |
| `tail_ttail` | **no verdict** | **98.118** | 3.50 | 0.0800 | 2.275 |
| `fuselage_integrated` | **no verdict** | **102.001** | 2.44 | 0.0800 | 2.232 |
| `dihedral_polyhedral2` | **no verdict** | **103.362** | 2.68 | 0.0800 | 2.221 |
| `printed_mass_x1.10` | **no verdict** | **96.504** | 2.74 | 0.0800 | 2.326 |

**All six land on the same five limits at once**: `span` on its 2.0 m cap,
`c_root` on its 0.275 m cap, `cs_frac` on its 0.4 bound, `ballast_kg` on zero,
and the static margin **exactly on its 0.0800 floor**. The aeroplane IS in the
corner the failures were attributed to. It simply solves there.

## 3. Stage C — the converged champion is airworthy

`diagnostics.candidates_source` = **`legal`**, and notes[0] is the ordinary
stall caveat rather than §28's fallback banner.

This closes the question §28.4 left open. That section measured a **3-iteration**
rcv2 champion whose every swept speed was illegal (trim at 4.2x its throw limit,
SM 0.439) and asked whether a CONVERGED battery would solve its own balance —
it has `ballast_kg`, ten placement variables and the throw limit as a hard NLP
row, so it should. **It does.**

## 4. Every failure here was idle sleep, and the clock is a wall clock

Nine cells "exceeded" a 30-minute wall budget after 2-6 minutes of solving. The
cause is not the solver:

```
00:16:46  Entering Sleep state due to 'Idle Sleep'
00:42:46  Entering Sleep state ...   01:02:18 'Maintenance Sleep'
01:19:26  01:35:29  01:52:34  02:10:26  02:26:53  ...
```

`solve._solve_nlp` sets `ipopt.max_wall_time`, deliberately and correctly — it
is protecting the run's wall clock against a solve that starts swapping
(HANDOFF, and the comment at `solve.py:1618`). But a **suspended process is
charged for its suspension**, so a member that spans an idle-sleep window is
killed for time it never got to use.

| cell | ran (local) | verdict | machine |
|---|---|---|---|
| six baselines + `sm_floor_0.05` | 00:17-00:41 | **all converged** | awake |
| `c_root_0.300` | 01:12-01:18 | wall-time | slept 01:02-01:18 |
| `span_cap_2.2` | 02:06-02:08 | wall-time | slept 01:52-02:08 |
| `kit_core` | 02:51-02:54 | wall-time | slept 02:26-… |

Perfect separation, and the 31-, 48- and 43-minute gaps BETWEEN those cells are
the machine asleep between them. `solve._convergence_trace` called all three
*"still converging when the clock stopped — the one case where a larger
`--solve-timeout-min` may actually pay"*, which is exactly right and, on its
own, would have sent the next reader to raise a cap that was never the problem.

**The fix is one word:** `caffeinate -i <command>`. The remaining measurements
run under it.

### What this predicts about the original battery, and how to check it in one command

That battery started at **03:17** — unattended, overnight. If it ran on a Mac
that was allowed to idle-sleep, some of its ten losses are this artifact and not
corners. The signature is unmistakable and its own artifact already records it:

    python3 -c "import json;d=json.load(open('runs/20260806T031736-.../run.json'));\
    print([(k,v.get('solve_minutes'),v.get('return_status')) for k,v in ... if 'failed' in v])"

**A member that reports `Maximum_WallTime_Exceeded` with `solve_minutes` far
below `--solve-timeout-min` did not run out of time — it was asleep.** A genuine
corner burns its whole budget and hundreds of iterations; §14.5.7's pusher did
187 and then 474. The three cells here died at 68, 25 and 15 iterations.

**This matters directly for the full solve on the more powerful device.** If it
is a Mac and it is left alone, it will lose members the same way, and the
artifact will report them in the same words the battery used.

### The check has been run on the WSL battery, and it comes back CLEAN

The prediction above was applied to
`runs/20260807T061330-rcv2_endurance-vtail_sample_v1-7_rcv2` (WSL, 342.3 min,
2026-08-07). **Every one of its six losses burned its full budget**, so none of
them is this artifact:

| member | solved | budget | iterations |
|---|---|---|---|
| `wing_dihedral_form polyhedral2` | 33.3 | 30 | 209 |
| `winglet continuous_cant` | 32.3 | 30 | 317 |
| `multistart perturbed_1` | 33.3 | 30 | 206 |
| `re-solve mass_bump` | 32.3 | 30 | — |
| `flatness 1.76` | 22.3 | **20** | 206 |
| `flatness 1.7` | 22.3 | **20** | 205 |

Two things make this a clean read rather than a lucky one. The flatness pair
look short against 30 but are not: the sweep runs on `FLATNESS_TIMEOUT_MIN =
20.0`, so **the budget is per phase and the comparison has to use the right
one** — a check that assumed `--solve-timeout-min` for every member would have
called those two sleep artifacts. And the iteration counts are 205-317, against
the 68/25/15 of the cells that really were asleep, which is the second half of
§4's own signature.

It had to be checked rather than assumed, because the consequence of being wrong
is the same either way: chasing a cap that was never the problem.

> **AND THE ASSUMPTION WOULD HAVE BEEN WRONG. THE WSL BOX SUSPENDS TOO.**
>
> This section first read "WSL under WSLg does not idle-suspend the way the Mac
> did here". That is false, measured 2026-08-08 by closing the lid: two `uptime`
> readings imply boot times **26½ minutes apart**, which is impossible unless the
> VM's clock stopped. Wall clock advanced 3 h 31 m; uptime advanced 3 h 05 m.
>
>     boot implied at 21:23:58 (up 12:27) : 08:56:58
>     boot implied at 00:55:27 (up 15:32) : 09:23:27   <- 26m29s uncounted
>
> Nothing was running at the time, so nothing was lost. But **`caffeinate -i` has
> no equivalent here and the hazard is identical**: a battery left overnight with
> the lid shut will have its members charged for the suspension and will report
> `Maximum_WallTime_Exceeded` in exactly the words §4 is about. The
> `20260807T061330` battery escaped it only because it ran with the machine
> awake — which is luck, not a property of the platform.
>
> **Leave the lid open for any unattended run on this box**, or change the
> Windows power setting; there is no in-repo guard, and the artifact cannot tell
> a suspended member from a starved one on its own.

## 5. Stage B — what the caps are worth

| relaxation | objective | vs 105.818 | note |
|---|---|---|---|
| relaxation | objective | vs 105.818 | note |
|---|---|---|---|
| `span_cap` 2.0 → 2.2 m | **110.990** | **+5.172 min** | a BUILD decision, already settled at 2.0 |
| **`fineness_max` 8 → 9** | **106.895** | **+1.076 min** | lands exactly on the new ceiling |
| SM floor 0.08 → 0.05 | **106.669** | **+0.851 min** | lands exactly on the new floor |
| **boat-tail 1.8 → 1.5 d_eq** | **106.270** | **+0.452 min** | saturated — see below |
| `c_root` 0.275 → 0.300 | **fails** | | genuine corner, on the motor row |
| kit `full` → `core` | *re-measuring* | | slept through |

**The static-margin floor binds but is nearly worthless to relax**: giving up
0.03 of margin — over a third of the required 0.08 — buys 51 seconds.

> ### The most valuable lever here is a MODEL-VALIDITY BOUND, not a requirement
>
> `fineness_max = 8` is worth **more than giving up a third of the static
> margin**, and unlike the SM floor, the span cap or the chord cap it protects
> nothing about the aeroplane. It exists because the Hoerner form factor keeps
> falling to f ≈ 16 while the real minimum-drag band for a body of revolution is
> f ≈ 6–7, so past 8 the drag model is not trusted. The optimizer is buying
> 1.08 minutes by going somewhere the model cannot vouch for — which is what
> that row's own comment means by *"landing on it is a defect report, not an
> optimum"*. **Raising it is not a design decision available to the user; it is
> a request for a better fuselage drag model.**
>
> **It also does not mean a longer pod.** Given the extra allowance the
> optimizer made the pod *thinner*: d_eq 67.64 → 61.99 mm (−8.4%) against a
> length of 541 → 558 mm (+3.1%), for −14 g of AUW. Less wetted area, not more.

### Three things every one of these cells agrees on

Measured on the WSL box at `913d2bc`, one process per cell.

1. **The bay is 345.30 mm in all three, to the micron.** It is set by the parts
   list and nothing else moves it.
2. **The motor row stays EXACTLY binding in all three** (`usable_nose` slack
   ≤ 0.2 µm). No length these levers buy reaches the nose — the optimizer spends
   every millimetre of it on slenderness until the motor row stops it again. So
   **neither lever should be expected to unstick the failing members**, and
   whether they do is stage D, which is unmeasured.
3. **`boat_tail_1.5` never reached 1.5.** `pod_tail` landed on its own BOX lower
   bound of 100 mm, leaving the relaxed row 1.53 mm of slack and inactive. So
   +0.452 min is the *saturated* value of that lever — the whole of what
   relaxing the row can buy given the box — and any floor at or below
   1.523·d_eq returns the same number. Reported this way because "the price of
   1.8 → 1.5" would be a claim about a row that was not active at the answer.

## 6. What the converged rows do NOT license

**Not "the caps are fine."** They license "these six members are not cap-blocked
on the current tree." Two differences from the battery are unresolved:

1. **The battery ran on a tree that has since been reverted.** It started
   2026-08-06 03:17; the ordering-row rescale was reverted at 08:22 the same day
   (`1363ea8`). That rescale was solution-preserving and cost ~45% of solve time
   — on its own enough to push a converging member past a 30-minute budget,
   which is what it did to `winglet_study__continuous_cant`.
2. **The battery's studies run greedily**, so its `tail_conventional` carried the
   adopted prop and topology; these cells carry the declared baseline
   (`ancf_11x6`). Same label, different aeroplane. `solve.screen_discrete` ranks
   the prop catalogue with no NLP at all, so closing this is cheap — it is not
   closed yet.

Between them and §4, there are now **three** candidate explanations for the 69%,
and none of them is a cap.

## 7. Reproducing

`caffeinate -i` is a macOS command and is what §4 is about; on the WSL box it is
neither available nor needed. `drive` must have the machine to itself either way
— a cell peaks near 15 GB and so does a battery, and nothing enforces that, so
check `ps` first. (There is no `.runqueue/runlock` in this repo; the earlier
command line named one and could not run.)

    caffeinate -i uv run python tools/price_caps.py drive        # macOS
    uv run python tools/price_caps.py drive                      # WSL
    uv run python tools/price_caps.py cell --member tail_ttail --relax sm_floor_0.05

`report` reads `runs/_capprice/` (untracked, written by `drive`). The cells
committed with this study are under `docs/`, so reading THEM takes the override:

    PRICE_CAPS_OUT=docs/studies/rcv2_cap_pricing uv run python tools/price_caps.py report
