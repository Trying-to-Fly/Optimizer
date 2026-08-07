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

## 5. Stage B — what the caps are worth

| relaxation | objective | vs 105.818 | note |
|---|---|---|---|
| SM floor 0.08 → 0.05 | **106.669** | **+0.851 min** | lands exactly on the new floor |
| `c_root` 0.275 → 0.300 | *re-measuring* | | slept through |
| `span_cap` 2.0 → 2.2 | *re-measuring* | | slept through |
| kit `full` → `core` | *re-measuring* | | slept through |

The one clean number so far says the static-margin floor **binds but is nearly
worthless to relax**: giving up 0.03 of static margin — over a third of the
required 0.08 — buys 51 seconds of endurance.

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

    caffeinate -i .runqueue/runlock uv run python tools/price_caps.py drive
    uv run python tools/price_caps.py report
    caffeinate -i uv run python tools/price_caps.py cell --member tail_ttail --relax sm_floor_0.05
