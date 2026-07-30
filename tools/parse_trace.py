"""Summarise an IPOPT iteration log: is this scaling, degeneracy, or infeasibility?

    uv run python tools/parse_trace.py <ipopt.log> [more.log ...]

Reads the iteration table and reports the four things that tell them apart:

  inf_pr huge at iteration 0        -> constraint SCALING (divide rows by their
                                       own scale; see FINDINGS §14.5.1)
  inf_pr small, inf_du diverging    -> DEGENERATE active set, multipliers do not
                                       exist (tools/degeneracy.py names the rows)
  lg(mu) never falls, alpha_pr ~1e-5,
    double-digit backtracks         -> the same degeneracy, seen from the line search
  EXIT: Infeasible_Problem_Detected -> genuinely over-constrained

Capture a log with `verbose=True`; IPOPT writes to file descriptor 1 from C++,
so redirect with os.dup2 rather than reassigning sys.stdout.
"""
import re
import sys
from pathlib import Path

# iter may carry a suffix letter (r = restoration); lg(rg) is often a bare "-";
# ls may carry a trailing flag character.
# alpha_pr carries a trailing step-acceptance character with no space before it
# ("2.08e-01f  1"): f/h/H/k/n/R/w/s/t/r. That is what made the strict in-run
# regex match only the iteration-0 line.
ROW = re.compile(
    r"^\s*(\d+)([a-zA-Z]?)\s+"
    r"([-+.\deE]+)\s+([-+.\deE]+)\s+([-+.\deE]+)\s+([-+.\deE]+)\s+"
    r"([-+.\deE]+)\s+(-|[-+.\deE]+)\s+([-+.\deE]+)\s+([-+.\deE]+)[a-zA-Z]?\s+(\d+)"
)
HDR = ("iter", "objective", "inf_pr", "inf_du", "lg(mu)", "||d||",
       "lg(rg)", "alpha_du", "alpha_pr", "ls")


def f(x):
    try:
        return float(x)
    except ValueError:
        return float("nan")


for path in sys.argv[1:]:
    text = Path(path).read_text(errors="ignore")
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            g = m.groups()
            rows.append({"iter": int(g[0]), "flag": g[1], "obj": f(g[2]),
                         "inf_pr": f(g[3]), "inf_du": f(g[4]), "lg_mu": f(g[5]),
                         "d": f(g[6]), "lg_rg": g[7], "alpha_du": f(g[8]),
                         "alpha_pr": f(g[9]), "ls": int(g[10]), "raw": line.rstrip()})
    print(f"\n########## {Path(path).name}: {len(rows)} rows, {len(text)} bytes")
    for key in ("EXIT", "Number of Iterations", "restoration"):
        for line in text.splitlines():
            if key in line:
                print("   ", line.strip()[:110])
    if not rows:
        print("   NO ROWS PARSED — first 40 non-empty lines:")
        for line in [x for x in text.splitlines() if x.strip()][:40]:
            print("   |", line[:120])
        continue

    print("   " + "  ".join(f"{h:>11s}" for h in HDR))
    idx = sorted({0, 1, 2, 3, 5, 10, 20, 40, 60, 80, 100, 130, 160, 190, 220,
                  len(rows) - 4, len(rows) - 3, len(rows) - 2, len(rows) - 1}
                 & set(range(len(rows))))
    for i in idx:
        r = rows[i]
        print("   " + "  ".join(f"{v:>11}" for v in (
            f"{r['iter']}{r['flag']}", f"{r['obj']:.6e}", f"{r['inf_pr']:.2e}",
            f"{r['inf_du']:.2e}", f"{r['lg_mu']:.1f}", f"{r['d']:.2e}",
            r["lg_rg"], f"{r['alpha_du']:.2e}", f"{r['alpha_pr']:.2e}", r["ls"])))

    tail = rows[-60:]
    print(f"   restoration rows: {sum(1 for r in rows if r['flag'] == 'r')} of {len(rows)}")
    print(f"   lg(mu):  start {rows[0]['lg_mu']:.1f}  end {rows[-1]['lg_mu']:.1f}  "
          f"min {min(r['lg_mu'] for r in rows):.1f}")
    print(f"   inf_pr:  start {rows[0]['inf_pr']:.2e}  end {rows[-1]['inf_pr']:.2e}  "
          f"min {min(r['inf_pr'] for r in rows):.2e}")
    print(f"   inf_du:  start {rows[0]['inf_du']:.2e}  end {rows[-1]['inf_du']:.2e}  "
          f"min {min(r['inf_du'] for r in rows):.2e}")
    a = [r["alpha_pr"] for r in tail]
    print(f"   alpha_pr last {len(a)}: min {min(a):.1e} median "
          f"{sorted(a)[len(a)//2]:.1e} max {max(a):.1e}")
    print(f"   distinct objective values in last {len(tail)}: "
          f"{len({round(r['obj'], 10) for r in tail})}")
    print(f"   ls (backtracks) last {len(tail)}: max {max(r['ls'] for r in tail)}, "
          f"mean {sum(r['ls'] for r in tail) / len(tail):.1f}")
