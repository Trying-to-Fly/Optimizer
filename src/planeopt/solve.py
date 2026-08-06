"""Run orchestration — MODEL_DETAILS.md section 6; the single entry point.

M1 scope: fixed-design evaluation (the Phase 1 gate pipeline). geometry ->
mass/CG -> trimmed aero over a speed sweep -> propulsion -> mission objective,
plus stall, static margin, and diagnostic figures. No optimizer yet: the "best"
operating point comes from the sweep, which doubles as the report's power curve.
M2 replaces the sweep with the NLP.
"""

from __future__ import annotations

import datetime
import logging
import numbers
import time
from pathlib import Path

import numpy as np

import planeopt

from . import aero, fingerprint, geometry, massmodel, memory, propulsion
from .mission import OBJECTIVES
from .report import assemble, figures, geometry_export, manufacturing
from .report import html as report_html
from .types import AircraftDefinition, MissionSpec, RunResult

# Progress goes through logging, never print: the library stays silent by default
# (tests, GUI), and each front end attaches the handler it wants. A single solve
# is 5-6 minutes and a full battery runs for hours, so a client that shows nothing
# is indistinguishable from a hang.
log = logging.getLogger("planeopt")

G = 9.81
M1_STATUS = "M1: fixed-design evaluation (Phase 1 gate pipeline) — no optimizer"

#: Wall-clock ceiling for ONE member solve, minutes. A converging solve on this
#: model takes 4-10 minutes; the cap exists because a diverging one has no
#: natural end — the 2026-07-29 flatness sweep spent 172 minutes on a single
#: member before failing anyway, which is 43% of that run's wall clock spent
#: learning nothing. Generous enough (3-5x the normal solve) that hitting it is
#: itself the diagnosis, and recorded as `Maximum_WallTime_Exceeded` when it is.
SOLVE_TIMEOUT_MIN = 30.0
#: Iteration ceiling for one member solve (IPOPT's own `max_iter`).
SOLVE_MAX_ITER = 1000
#: How far outside the mission's static-margin window a reported SM may land and
#: still count as satisfying it. An optimizer holds this constraint ACTIVE, so
#: the comparison has to admit the solver's own convergence tolerance or it
#: reports every champion as out of range.
SM_ACTIVE_TOL = 1e-4


class RunPaused(RuntimeError):
    """A battery stopped cleanly at a member boundary, on request.

    Not an error: everything finished is on disk in the checkpoint directory,
    and re-running the same command resumes from there.
    """


def _jsonable(value):
    """Plain-Python copy of a solve result, so it survives a JSON round trip.

    Results carry numpy scalars and tuples (`clmax_ab_used`), which `json` would
    either refuse or stringify — and a checkpoint that reloads a float as the
    string "np.float64(1.23)" is worse than no checkpoint at all.
    """
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    return str(value)


class _SolveCache:
    """Per-member results on disk, so a battery can be stopped and continued.

    A battery is a few dozen INDEPENDENT solves spread over hours, which is what
    makes this tractable: each member's result is pure data, so finishing one is
    progress that never has to be repeated. Entries are keyed by
    (phase label, member key), which lines a resumed run up with the one it
    continues — the sequence is deterministic for a given aircraft and mission.

    **But the sequence lining up is not the same as the PHYSICS lining up.**
    (label, key) says nothing about the model that produced the number, so a
    resume after the model moved silently mixes two models into one artifact,
    every member of which converged. A battery was discarded for exactly that on
    2026-08-01 (FINDINGS section 18.7). Entries therefore live in a
    per-fingerprint subdirectory (`fingerprint.model_fingerprint`): a changed
    model starts a fresh set beside the old one, so a stale entry is not found
    rather than not trusted. Nothing is deleted and nothing has to be remembered.

    It deliberately does NOT try to checkpoint a solve in progress; see
    `optimize`'s docstring for why that is not possible.
    """

    def __init__(self, directory: Path, fingerprint: str):
        self.root = Path(directory)
        self.fingerprint = fingerprint
        self.dir = self.root / fingerprint
        self.dir.mkdir(parents=True, exist_ok=True)
        #: Members served from disk this run, per phase label. A fully resumed
        #: phase otherwise reports 0.0 minutes and reads as a phase that was
        #: SKIPPED — which is how the 2026-08-05 run's multistart and flatness
        #: sweep looked in the artifact, when in fact both had been solved in
        #: full the evening before. The distinction matters to anyone deciding
        #: whether a "fresh" battery actually re-searched anything.
        self.resumed: dict[str, int] = {}
        self._report_supersession()

    def _report_supersession(self) -> None:
        """Say, once, that older checkpoint sets are being passed over.

        Otherwise the only visible symptom of a model change is that a resume
        re-solves everything, which reads as a bug in the resume rather than as
        the guard doing its job.
        """
        others = sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and p.name != self.fingerprint
        )
        # Entries written before this guard existed sit loose in the parent.
        legacy = any(p.suffix == ".json" for p in self.root.iterdir() if p.is_file())
        if legacy:
            others.append("(unfingerprinted, pre-2026-08-04)")
        if others:
            log.info(
                "checkpoint set %s is new; %s on disk %s a different model and "
                "will not be resumed from (kept, not deleted)",
                self.fingerprint, ", ".join(others),
                "carries" if len(others) == 1 else "carry",
            )

    def _path(self, label: str, key) -> Path:
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in f"{label}__{key}")
        return self.dir / f"{safe}.json"

    def get(self, label: str, key):
        path = self._path(label, key)
        if not path.is_file():
            return None
        try:
            import json

            entry = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt entry just means "re-solve"
            log.warning("checkpoint %s is unreadable; re-solving that member", path.name)
            return None
        self.resumed[label] = self.resumed.get(label, 0) + 1
        return entry

    def put(self, label: str, key, result: dict) -> None:
        import json

        path = self._path(label, key)
        try:
            # write-then-rename: a run killed mid-write must not leave a
            # half-file that the next run trusts
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps(_jsonable(result), indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:  # noqa: BLE001 — checkpointing must never kill a run
            log.warning("could not checkpoint %s/%s: %s", label, key, e)


class SolveFailure(RuntimeError):
    """A member solve that did not converge, carrying the solver's own verdict.

    CasADi's assertion text ends with `return_status is '...'` — the single
    piece of information a reader needs — so truncating that message for a log
    line drops exactly the diagnosis and keeps the boilerplate. The status is
    therefore read from the solver's stats and put first.

    `Infeasible_Problem_Detected` (over-constrained corner), `Restoration_Failed`
    (usually a NaN or a badly scaled constraint) and `Maximum_WallTime_Exceeded`
    (hit the guard above) call for completely different fixes, and until now the
    run artifact could not tell them apart.
    """

    def __init__(self, opti, exc: BaseException, labels: dict[int, str] | None = None):
        try:
            stats = opti.debug.stats()
        except Exception:  # pragma: no cover — stats missing before the first iterate
            stats = {}
        self.return_status = str(stats.get("return_status", "unknown"))
        self.iter_count = stats.get("iter_count")
        self.detail = str(exc)
        self.violations = _worst_violations(opti, labels or {})
        iters = "" if self.iter_count is None else f" after {self.iter_count} iterations"
        worst = f"; closest miss {self.violations[0]['what']}" if self.violations else ""
        super().__init__(f"{self.return_status}{iters}{worst}")


def _worst_violations(opti, labels: dict[int, str], top: int = 5) -> list[dict]:
    """Which constraints the last iterate could not satisfy, worst first.

    A status alone says the solve failed; this says what it failed ON, which is
    the difference between "the solver is broken" and "you asked for an aircraft
    that does not exist". Both of the 2026-07-30 chronic failures turned out to
    be the latter, and it took a bespoke script to find out — so the run now
    answers it itself.

    Diagnostics must never turn a failed solve into a crashed one, so the whole
    thing is best-effort.
    """
    try:
        import casadi as cas

        x, g = opti.x, opti.g
        if g.shape[0] == 0:
            return []
        xs = opti.debug.value(x)
        gv = np.array(cas.Function("g", [x], [g])(xs)).ravel()
        lbg = np.array(opti.debug.value(opti.lbg)).ravel()
        ubg = np.array(opti.debug.value(opti.ubg)).ravel()
        # how far outside its own bounds each row sits (0 when satisfied)
        below = np.where(np.isfinite(lbg), lbg - gv, -np.inf)
        above = np.where(np.isfinite(ubg), gv - ubg, -np.inf)
        viol = np.maximum(np.maximum(below, above), 0.0)
        viol = np.where(np.isfinite(viol), viol, 0.0)
        rows = [r for r in np.argsort(-viol)[:top] if viol[r] > 1e-8]
        return [
            {
                "row": int(r),
                "by": float(viol[r]),
                "value": float(gv[r]),
                "what": labels.get(int(r), f"g[{int(r)}]"),
            }
            for r in rows
        ]
    except Exception:  # noqa: BLE001 — never mask the real failure
        return []


class _ConstraintLabels:
    """Records which source line produced each row of `opti.g`, while building.

    CasADi numbers constraint rows; a person needs "the static-margin floor".
    Wrapping `subject_to` for the duration of the build is the only way to keep
    that mapping, and it costs one stack walk per constraint against a solve
    measured in minutes. Used only to make a FAILURE readable.

    The wrapper is bound to the INSTANCE, not the class: an exception during the
    build then cannot leave a global patch behind to corrupt every later solve
    in the process, and two Opti stacks alive at once cannot see each other's.
    """

    def __init__(self, opti):
        import traceback

        self.spans: list[tuple[int, int, str]] = []
        real = opti.subject_to  # already bound to this instance
        spans = self.spans

        def traced(constraint, *a, **kw):
            before = opti.g.shape[0]
            out = real(constraint, *a, **kw)
            added = opti.g.shape[0] - before
            if added > 0:
                frame = next(
                    (f for f in reversed(traceback.extract_stack()[:-1])
                     if "aerosandbox" not in f.filename),
                    None,
                )
                where = (
                    f"{Path(frame.filename).name}:{frame.lineno} {(frame.line or '').strip()}"
                    if frame is not None else "?"
                )
                spans.append((before, added, where[:120]))
            return out

        opti.subject_to = traced
        self._opti = opti

    def stop(self) -> None:
        """Hand the Opti back its own method; safe to call more than once."""
        self._opti.__dict__.pop("subject_to", None)

    def as_dict(self) -> dict[int, str]:
        return {r: src for start, n, src in self.spans for r in range(start, start + n)}


#: A variable counts as sitting ON a bound within this fraction of its own box
#: width. IPOPT converges onto a bound rather than to it (the 2026-07-31
#: champion's span is 2.0000000199 against a 2.0 m cap), so an exact comparison
#: would report nothing; 1e-6 of the box absorbs that and nothing wider.
BOUND_ACTIVE_TOL = 1e-6


class _DeclaredBounds:
    """Records the box each design variable is declared with, while building.

    Bounds live in the AIRCRAFT's `design_variables`, so the framework otherwise
    has no idea what they are — which is why "the champion is pinned against its
    span cap, its chord cap, its control-surface fraction and five more" was
    something a person had to reconstruct by hand against the aircraft file
    (HANDOFF issue 0b: the 2026-07-31 champion sat on EIGHT bounds, of which
    three were ever discussed). An active bound is the design asking for
    something it is not allowed to have; naming them costs one dict per
    variable, and NOT naming them cost a session of looking at the wrong three.

    Same discipline as _ConstraintLabels: the patch is bound to the INSTANCE, so
    a build that raises cannot leave a global patch behind, and two live Opti
    stacks cannot see each other's variables.
    """

    def __init__(self, opti):
        import inspect

        real = opti.variable  # already bound to this instance
        sig = inspect.signature(real)
        self.by_id: dict[int, tuple[float | None, float | None]] = {}
        by_id = self.by_id

        def traced(*a, **kw):
            var = real(*a, **kw)
            bound = sig.bind(*a, **kw)
            bound.apply_defaults()
            by_id[id(var)] = (
                bound.arguments.get("lower_bound"),
                bound.arguments.get("upper_bound"),
            )
            return var

        opti.variable = traced
        self._opti = opti

    def stop(self) -> None:
        """Hand the Opti back its own method; safe to call more than once."""
        self._opti.__dict__.pop("variable", None)

    def boxes(self, dv: dict) -> dict[str, list]:
        """The declared box per design variable, `{name: [lo, hi]}`.

        Recorded alongside the solution because a bound is only readable next to
        the value it bounds — and because a phase that needs to stay inside the
        box (the flatness sweep fixes `span`, which must land inside its own
        declared range or IPOPT returns `Invalid_Problem_Definition`) otherwise
        has no way to ask what the range is.
        """
        out = {}
        for name, var in dv.items():
            lo, hi = self.by_id.get(id(var), (None, None))
            out[name] = [
                None if lo is None or not np.isscalar(lo) else float(lo),
                None if hi is None or not np.isscalar(hi) else float(hi),
            ]
        return out

    def active(self, dv: dict, sol) -> list[dict]:
        """Which design variables the solution sits on, worst-first by margin.

        Reported rather than judged: an active bound is not a defect, and moving
        one is not automatically worth anything — `c_root` was pinned in every
        solve this project ever ran and was worth 14 seconds when finally
        released (FINDINGS section 15). It is a WORK LIST, and the point is that
        it should not have to be assembled by hand.
        """
        out = []
        for name, var in dv.items():
            lo, hi = self.by_id.get(id(var), (None, None))
            try:
                value = float(sol(var))
            except (TypeError, RuntimeError):  # vector variable, or not in this solve
                continue
            for which, bound in (("lower", lo), ("upper", hi)):
                if bound is None or not np.isscalar(bound):
                    continue
                width = (hi - lo) if (lo is not None and hi is not None and hi > lo) else 1.0
                if abs(value - float(bound)) <= BOUND_ACTIVE_TOL * width:
                    out.append({
                        "variable": name, "value": value,
                        "bound": float(bound), "at": which,
                        "box": [None if lo is None else float(lo),
                                None if hi is None else float(hi)],
                    })
        return sorted(out, key=lambda e: e["variable"])


def _failure_record(exc: BaseException) -> dict:
    """The dict a failed job contributes to run.json."""
    rec = {"failed": str(exc)[:280]}
    if isinstance(exc, SolveFailure):
        rec["return_status"] = exc.return_status
        rec["iter_count"] = exc.iter_count
        if exc.violations:
            rec["violations"] = exc.violations
        if exc.return_status == "unknown":
            # no stats to read — the solver did not get far enough to have a
            # verdict, so the raw exception text is all there is. Keep it.
            rec["detail"] = exc.detail[:400]
    return rec


#: What a batch member's failure carries forward into the study/battery entry.
#: Every summariser projects a solve result down to a few fields, and each one
#: used to drop everything but the message.
_FAILURE_FIELDS = (
    "failed", "return_status", "iter_count", "violations", "detail", "solve_minutes",
)


def _failed_entry(r: dict) -> dict:
    return {k: r[k] for k in _FAILURE_FIELDS if k in r}


def v_min_price(airworthy: list[dict], best: dict, v_min_ms: float, sign: int) -> dict | None:
    """What the minimum-speed requirement is costing, or None if it costs nothing.

    `airworthy` is every trimmed sweep point that clears stall, the advance-ratio
    cap and the deflection limit — i.e. legal but for `v_min`. If the best of
    those is slower than `v_min`, the requirement is what is holding the
    objective back and the difference is its price.

    Pure arithmetic over the sweep so it is testable without an aero run.
    """
    if not airworthy:
        return None
    unconstrained = max(airworthy, key=lambda s: sign * s.get("objective_value", -np.inf))
    if unconstrained["V_ms"] >= v_min_ms - 1e-9:
        return None
    a, b = unconstrained.get("objective_value"), best.get("objective_value")
    return {
        "unconstrained_best_V_ms": unconstrained["V_ms"],
        "unconstrained_objective": a,
        "objective_at_v_min": b,
        "cost_of_v_min": None if a is None or b is None else abs(a - b),
    }


def no_survivors_error(keys: list[str], results: list[dict]) -> RuntimeError:
    """The error a multistart with no surviving member should raise.

    `run` has answered this properly since M1 — *"no feasible operating point
    anywhere in the sweep... Causes: ..."* — on the stated grounds that a bare
    `max() iterable argument is empty` tells the reader nothing and is exactly
    where a broken install surfaces. `optimize` had the identical hole and
    nobody had fallen into it, because until `--max-iter` existed no battery
    ever had EVERY member fail. The first `--max-iter 3` run ever attempted
    crashed on precisely that `max()`, after paying for every solve, with no
    artifact written (2026-08-06, FINDINGS §27).

    Grouped by RETURN STATUS because a multistart is many attempts at one
    problem, so the way they all failed is the diagnosis: every member
    `Infeasible_Problem_Detected` is an over-constrained aircraft, every member
    `Maximum_WallTime_Exceeded` is a cap to raise, and a mixture is a badly
    scaled model. Three different fixes, and a flattened message picks none.

    Returns the exception rather than raising it, so the caller's `raise` is
    visible at the site that decided the run is over.
    """
    by_status: dict[str, list[str]] = {}
    for key, r in zip(keys, results, strict=False):
        by_status.setdefault(str(r.get("return_status", "unknown")), []).append(key)
    detail = "; ".join(
        f"{status} [{', '.join(keys_)}]" for status, keys_ in sorted(by_status.items())
    )
    worst = next(
        (r["violations"][0]["what"] for r in results if r.get("violations")), None
    )
    return RuntimeError(
        f"every one of the {len(results)} multistart members failed to solve, so "
        f"there is no champion to build a run around. Causes: {detail}."
        + (f" Closest miss on any member: {worst}." if worst else "")
    )


def airworthiness_price(
    feasible: list[dict], best: dict, rules: dict, v_min_ms: float, sign: int
) -> dict | None:
    """What the AIRWORTHINESS filters cost the headline number, or None.

    `v_min_price` is the same question asked of the one requirement whose
    exclusions live BELOW the speed floor. Everything else that removes a speed
    point — the gust margin, the propeller advance-ratio cap, the trim-throw
    limit — removes it from `airworthy` before that function is ever called, so
    a design held back by one of those reported a headline with nothing at all
    saying what set it.

    Not hypothetical. The first `vtail_rcv2` evaluation (2026-08-06) reported
    53.8 min at 16.5 m/s — its FASTEST swept speed, for an endurance aeroplane —
    because the spec design is nose-heavy enough to need more than its 6.53 deg
    of trim throw at every slower speed. Twelve of thirteen trimmed points were
    dropped, the peak among them was 71.2 min at 12.0 m/s, and the artifact's
    own `trim_deflection_deg` read -6.29 deg: comfortably inside the cap,
    because it is the deflection of the ONE point the cap admitted. Every number
    in that run was right and the run as a whole was not readable.

    `rules` maps a filter name to a predicate on a sweep point, and is the SAME
    dict the filter itself is built from, so a rule cannot be priced here and
    quietly not applied there. Returns None when the reported best already IS
    the peak — a healthy run carries no diagnostic rather than an empty one.
    """
    at_or_above = [s for s in feasible if s["V_ms"] >= v_min_ms - 1e-9]
    if not at_or_above:
        return None
    peak = max(at_or_above, key=lambda s: sign * s.get("objective_value", -np.inf))
    a, b = peak.get("objective_value"), best.get("objective_value")
    # `sign *` and not `abs`: a peak that is WORSE than the reported best is not
    # a price, it is the filters having cost nothing.
    if a is None or b is None or sign * (a - b) <= 1e-9:
        return None
    return {
        "unfiltered_best_V_ms": peak["V_ms"],
        "unfiltered_objective": a,
        "reported_objective": b,
        "cost_of_airworthiness": abs(a - b),
        "peak_excluded_by": sorted(n for n, ok in rules.items() if not ok(peak)),
        # Per rule, every speed it removed — the count is the difference between
        # "one awkward point dropped out" and "this filter chose the answer".
        "excluded_by_rule": {
            n: [s["V_ms"] for s in at_or_above if not ok(s)]
            for n, ok in rules.items()
            if any(not ok(s) for s in at_or_above)
        },
    }


def effective_design_vector(aircraft, dv: dict | None) -> dict:
    """The COMPLETE design vector a run was evaluated at, defaults included —
    or `{}` when the run had no design vector at all.

    A partial `dv` is merged over the aircraft's `DV_DEFAULTS`, because the
    artifact must carry the whole vector rather than a diff: a diff leaves a
    reader to go and find defaults in a Python file that has since changed,
    which is the same trap as recording a span and expecting them to recover
    taper from it.

    **`dv=None` returns `{}`, and that is not "unrecorded".** It is the
    aircraft's own convention (`aircraft.geometry(dv=None)` -> "the fixed v1.2
    spec design; else the parametric architecture"), and the two are materially
    DIFFERENT aeroplanes: on the sample aircraft the spec geometry and the
    parametric point at `DV_DEFAULTS` differ by 7% in wing area, 3.5% in
    projected span and 7% in mean chord. Recording `DV_DEFAULTS` for a
    spec-design run would therefore be worse than recording nothing — it would
    be an authoritative-looking vector that rebuilds an aeroplane the run never
    evaluated. `{}` round-trips correctly, because `geometry(recorded or None)`
    is `geometry(None)`.

    Floats because `json` refuses numpy scalars, and an aircraft is free to
    declare its defaults with them. The test is `numbers.Real` and NOT
    `isinstance(v, (int, float))`: `np.float64` happens to subclass `float` so
    the naive check passes it, while **`np.int64` subclasses neither** and would
    sail through uncoerced to fail at write time — after the solving was done.
    `bool` is excluded explicitly because it IS a `numbers.Real`, and recording
    a discrete flag as 1.0 would rebuild the aircraft with a float where it
    declared a switch. (`np.bool_` needs no exclusion: it is not a Real.)
    """
    if dv is None:
        return {}
    merged = (getattr(aircraft, "DV_DEFAULTS", None) or {}) | dv
    return {
        k: (float(v) if isinstance(v, numbers.Real) and not isinstance(v, bool) else v)
        for k, v in merged.items()
    }


def objective_is_mesh_trustworthy(aircraft, r: dict) -> tuple[bool, dict | None]:
    """Is this solve's objective the aeroplane's, or the panel count's?

    The cheap half of `aero.mesh_convergence_check` — drag at one operating
    point, two lifting-line runs, well under a second — asked of an ARBITRARY
    solve rather than only of the final champion.

    It exists because this project's expensive failures are all selection-time
    ones found late. On 2026-08-01 a solve reported an L/D of 889 because at
    four panels per section a high-cant winglet contributed about -0.93 N
    (FINDINGS §18); the winglet cross-check was separately measuring its own
    mesh; and the in-loop model made thrust and a solve went looking for it.
    In every case the model was untrustworthy WHILE the studies were choosing
    the design, and nothing said so until the run was over.

    Returns (ok, check). `check` is None when the solve carries too little to
    ask the question — a failed member, say — and callers should treat an
    unanswerable question as trustworthy rather than reject on ignorance.
    """
    needed = ("V_ms", "alpha_deg", "deflection_deg", "x_cg_m", "dv")
    if any(r.get(k) is None for k in needed):
        return True, None
    try:
        check = aero.mesh_convergence_check(
            aircraft.geometry(r["dv"]), r["V_ms"], r["alpha_deg"],
            r["deflection_deg"], r["x_cg_m"],
            control_name=getattr(aircraft, "pitch_control_name", "ruddervator"),
        )
    except Exception as e:  # noqa: BLE001 — a guard must not cost the run
        log.warning("mesh trustworthiness check failed, not blocking: %s: %s",
                    type(e).__name__, e)
        return True, None
    return bool(check["converged"]), check


def sm_sign_flip(sm: dict) -> dict | None:
    """The worst locally-UNSTABLE alpha inside a positive margin's own window.

    `aero.static_margin` reports a least-squares slope over `SM_ALPHA_OFFSETS`
    and returns the per-alpha local slopes alongside it. A regression through
    points whose slope changes sign returns a confident positive margin for an
    aeroplane that is not positively stable at its own trim point. Returns the
    most negative local slope when that has happened, else None.
    """
    if sm.get("static_margin") is None or sm["static_margin"] <= 0:
        return None
    negative = [
        p for p in (sm.get("sm_local_slopes") or [])
        if p.get("sm_local") is not None and p["sm_local"] < 0
    ]
    return min(negative, key=lambda p: p["sm_local"]) if negative else None


def _is_trim_failure(e: BaseException) -> bool:
    """Did this sweep point drop out because TRIM would not converge?

    `aero.trim` is the only thing that raises with this prefix, and it does so
    after exhausting a seeded start plus five spread starts — so the message is
    about the root-find, not about the aeroplane. Matching on the prefix keeps
    the classification at the one place that owns the wording.
    """
    return str(e).startswith("trim failed at V=")


def run(
    aircraft: AircraftDefinition,
    mission: MissionSpec,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    v_sweep: tuple[float, float, float] | None = None,
    dv: dict | None = None,
    trim_guess: tuple[float, float] | None = None,
) -> tuple[RunResult, Path]:
    objective = OBJECTIVES[mission.objective]
    # The sweep window is the aircraft's speed envelope, so the aircraft may
    # declare it. A loiter plane and a speed plane do not overlap much: sweeping
    # 8-17 m/s over an airframe that stalls at 12.4 yields three usable points
    # and an empty power curve.
    if v_sweep is None:
        v_sweep = getattr(aircraft, "speed_sweep_ms", (8.0, 17.0, 0.5))
    log.info(
        "evaluating %s / %s over %d speed points",
        getattr(aircraft, "name", type(aircraft).__name__), mission.name,
        len(np.arange(*v_sweep)),
    )
    pt = aircraft.powertrain()
    bodies = aircraft.parasite_bodies(dv)
    pitch_control = getattr(aircraft, "pitch_control_name", "ruddervator")

    airplane = aircraft.geometry(dv)
    components, printed_breakdown = massmodel.build(aircraft, airplane, dv)
    mass_totals = massmodel.totals(components)
    auw, x_cg = mass_totals["auw_kg"], mass_totals["x_cg_m"]
    weight_n = auw * G

    # Optional hook: an aircraft that carries a per-part equipment manifest
    # (planeopt.equipment) reports it here — placements, group totals, the
    # requirements this model does not check, and the max-weight closure check.
    # Aircraft without the hook are unaffected; the block is simply absent.
    equipment_block = None
    eq_hook = getattr(aircraft, "equipment_report", None)
    if eq_hook is not None:
        try:
            eq_names = {e.name for e in aircraft.fixed_equipment(dv)}
            other = [c for c in components if c.name not in eq_names]
            equipment_block = eq_hook(dv, other=other)
        except Exception as e:  # noqa: BLE001 — reporting must never sink a run
            equipment_block = {"failed": f"{type(e).__name__}: {e}"[:200]}
            log.warning("equipment report failed: %s", equipment_block["failed"])

    # --- speed sweep: trim + power at each V ---
    # Continuation: each point seeds the next. Trim is a stiff root-find, and a
    # fixed starting guess only works while the sweep stays near it — marching
    # the solution along the sweep is what makes a wide speed range converge.
    sweep = []
    # Start from the caller's operating point when there is one — re-evaluating an
    # optimizer champion should begin where the optimizer left off, not at a
    # generic loiter guess several tens of degrees away.
    guess = trim_guess
    for V in np.arange(*v_sweep):
        try:
            t = aero.trim(
                airplane, float(V), weight_n, x_cg, bodies,
                control_name=pitch_control, guess=guess,
            )
            guess = (t["alpha_deg"], t["deflection_deg"])
            p = propulsion.solve(float(V), t["drag_n"], pt)
        except (RuntimeError, ValueError) as e:
            # `infeasible` stays the key every consumer excludes on, but WHY a
            # point dropped out is not one question. A propulsion chain that
            # cannot close at this speed is a statement about the aeroplane; a
            # 2-D root-find that ran out of progress from six different starts
            # is a statement about the SOLVER, and recording the second as
            # "infeasible" claims something the run did not establish. The
            # 2026-08-05 artifact reported V = 8.0 m/s infeasible on the
            # strength of "the iteration is not making good progress" — a
            # message about IPOPT's step, at a speed only 0.28 m/s above the
            # computed stall, where a trimmed solution may well exist.
            cause = "trim_not_converged" if _is_trim_failure(e) else "propulsion"
            log.debug("V = %.1f m/s dropped (%s): %s", float(V), cause, e)
            sweep.append({"V_ms": float(V), "infeasible": str(e), "cause": cause})
            continue
        point = {**t, **p}
        if objective.evaluator is not None:
            point["objective_value"] = objective.evaluator(float(V), p["P_elec_w"], mission, pt)
        sweep.append(point)

    # --- stall: critical-section method (also feeds the gust-margin filter) ---
    clmax_ab = aero.clmax_log_fit(airplane.wings[0].xsecs[0].airfoil)
    stall = aero.critical_stall_speed(airplane, weight_n, clmax_ab)
    re_s = 1.225 * stall["v_stall_ms"] * airplane.c_ref / 1.81e-5
    stall["cl_max_3d"] = 0.9 * (clmax_ab[0] + clmax_ab[1] * np.log(re_s))

    feasible = [s for s in sweep if "infeasible" not in s]
    # same feasibility rules as the NLP: wind floor, gust margin, and the prop
    # advance-ratio cap (beyond 95% of the fitted table the CT->0 tail of the
    # polynomial fit is not trustworthy)
    j_cap = 0.95 * propulsion.PropTable(pt.prop.proxy_table).j_max
    # throw-limit policy may be a plain number or a callable of the design vector
    # (hinge fraction free -> the degree cap depends on the control chord)
    defl_cap = getattr(aircraft, "trim_deflection_limit_deg", None)
    if callable(defl_cap):
        defl_cap = float(defl_cap(dv))
    # Named rather than inlined, so `airworthiness_price` prices exactly the
    # predicates the filter applies. A rule that could be priced in one place
    # and applied in another is how a filter comes to choose an answer without
    # the artifact being able to say which one did.
    airworthiness_rules = {
        "gust_margin": lambda s: s["CL"] <= 0.7 * stall["cl_max_3d"] + 1e-6,
        "advance_ratio": lambda s: s["J"] <= j_cap + 1e-6,
        "trim_throw": lambda s: (
            defl_cap is None or abs(s["deflection_deg"]) <= defl_cap + 1e-3
        ),
    }

    def _legal_but_for_v_min(s: dict) -> bool:
        return all(ok(s) for ok in airworthiness_rules.values())

    airworthy = [s for s in feasible if _legal_but_for_v_min(s)]
    legal = [s for s in airworthy if s["V_ms"] >= mission.v_min_ms - 1e-9]
    candidates = legal if legal else feasible
    if not candidates:
        # Every point failed to trim or to close the propulsion chain. Report the
        # distinct causes: bare "max() iterable argument is empty" tells the user
        # nothing, and this is exactly where a broken install surfaces.
        reasons: dict[str, list[float]] = {}
        for s in sweep:
            reasons.setdefault(s.get("infeasible", "unknown"), []).append(s["V_ms"])
        detail = "; ".join(
            f"{reason} [V = {', '.join(f'{v:.1f}' for v in speeds[:3])}"
            f"{', ...' if len(speeds) > 3 else ''} m/s]"
            for reason, speeds in reasons.items()
        )
        raise RuntimeError(
            f"no feasible operating point anywhere in the {len(sweep)}-point speed "
            f"sweep, so there is nothing to report. Causes: {detail}"
        )
    sign = 1 if objective.direction == "maximize" else -1
    best = max(candidates, key=lambda s: sign * s.get("objective_value", -np.inf))
    # evaluate dCm/dCL at the trim alpha — LiftingLine's derivative is
    # alpha-dependent, so a fixed reference alpha disagrees with the NLP
    sm = aero.static_margin(
        airplane, best["V_ms"], x_cg, airplane.c_ref, alpha0=best["alpha_deg"], bodies=bodies
    )

    # --- what the headline number is actually limited BY ---------------------
    # A reported optimum sitting on `v_min` is not the same claim as one sitting
    # at an interior peak, and the artifact could not tell them apart: on
    # 2026-08-05 the champion read 142.09 min at 9.5 m/s while the sweep's own
    # peak was 143.01 min at 9.0, excluded by the minimum-speed requirement.
    # Nothing was wrong — but "the best this aeroplane can do" and "the best it
    # may do at or above 9.5 m/s" are different sentences, and only the second
    # was true. Priced here so the requirement can be argued with.
    vmin_price = v_min_price(airworthy, best, mission.v_min_ms, sign)
    # ... and the same question asked of the filters that run BEFORE `airworthy`
    # exists, which is where the first rcv2 evaluation lost its headline.
    air_price = airworthiness_price(
        feasible, best, airworthiness_rules, mission.v_min_ms, sign
    )

    # --- sweep points that dropped out, and on whose authority ---------------
    dropped = [s for s in sweep if "infeasible" in s]
    unproven = [s for s in dropped if s.get("cause") == "trim_not_converged"]

    # --- does the static margin keep its sign across the window it is read on?
    # The reported SM is a REGRESSION over SM_ALPHA_OFFSETS (aero.static_margin).
    # A regression through points whose local slope changes sign returns a
    # confident positive number for an aeroplane that is not positively stable
    # AT ITS OWN TRIM POINT — which is the 2026-08-05 champion: SM 0.0800 on its
    # floor, local slopes +0.187, +0.138, then -0.022 at the trim alpha. That is
    # a known fidelity limit of this SM model (FINDINGS — the dominant one), but
    # a known limit that nothing announces is indistinguishable from a clean
    # result to everyone downstream of it.
    worst_unstable = sm_sign_flip(sm)
    sm_sign_consistent = worst_unstable is None

    result = RunResult(
        aircraft=aircraft.name,
        mission=mission.name,
        objective=objective.name,
        status=M1_STATUS,
        created=datetime.datetime.now().isoformat(timespec="seconds"),
        design_vector=effective_design_vector(aircraft, dv),
        geometry=geometry.summarize(airplane),
        masses={
            # Mass AND station. The station was always in the model — a PointMass
            # is a (mass, station) pair and the CG is computed from it — and until
            # 2026-08-05 the artifact threw half of it away, so "where does the
            # receiver go" had no answer anywhere in a run directory even though
            # the solver had one. Millimetres because that is the unit a builder
            # measures in and the unit the source BOMs are written in.
            "components": {
                c.name: {
                    "mass_kg": round(float(c.mass_kg), 4),
                    "station_mm": round(float(c.x_m) * 1000, 1),
                }
                for c in components
            },
            "printed_breakdown": {
                k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                for k, v in printed_breakdown.items()
            },
            "auw_kg": float(auw),
            "x_cg_m": float(x_cg),
            "wing_loading_g_dm2": float(auw * 1000 / (airplane.s_ref * 100)),
            "equipment": equipment_block,
        },
        performance={
            "objective_units": objective.units,
            "best": best,
            "usable_energy_wh": pt.battery.usable_energy_wh,
            "watts_per_kg": float(best["P_elec_w"] / auw),
            "wh_per_km_airspeed": float(
                (best["P_elec_w"] + pt.avionics_power_w) / (3.6 * best["V_ms"])
            ),
            "sweep": sweep,
        },
        constraints={
            "v_min_ms": mission.v_min_ms,
            "v_min_active": bool(abs(best["V_ms"] - mission.v_min_ms) < 0.26),
            "v_stall_max_ms": mission.v_stall_max_ms,
            "v_stall_ms": stall["v_stall_ms"],
            "stall_ok": (mission.v_stall_max_ms is None)
            or (stall["v_stall_ms"] <= mission.v_stall_max_ms * 1.01),  # 1% tol: active != violated
            "static_margin": float(sm["static_margin"]),
            # recorded, not just checked: the build document derives the allowable
            # CG window from this and cannot do so from the run artifact otherwise
            "static_margin_range": [float(x) for x in mission.static_margin_range],
            # Tolerance, for the same reason stall_ok has one: the NLP drives
            # this constraint ACTIVE, so an exact comparison against the bound
            # reports every optimized design as violating it — IPOPT converges
            # to 0.07999999 against a 0.08 floor and is entitled to. The
            # tolerance is deliberately tight (1e-4, one part in 800 of this
            # project's SM window): it absorbs solver and round-off noise and
            # nothing else, so a design that genuinely misses its floor still
            # says so.
            "sm_in_range": bool(
                mission.static_margin_range[0] - SM_ACTIVE_TOL
                <= sm["static_margin"]
                <= mission.static_margin_range[1] + SM_ACTIVE_TOL
            ),
            "trim_deflection_deg": best["deflection_deg"],
            # Renders as pass/FAIL beside the other constraint checks: a margin
            # that changes sign inside its own window is not a passing margin.
            "sm_sign_consistent": sm_sign_consistent,
        },
        diagnostics={
            # Which of the two aeroplanes an aircraft can build this was, stated
            # rather than inferred from an empty design_vector (see
            # RunResult.design_vector): `dv=None` is the fixed spec geometry and
            # is NOT the parametric family evaluated at its defaults.
            "design_source": "parametric" if dv is not None else "spec",
            "wind_mode": objective.wind_mode,
            # None when v_min is not what is holding the objective back.
            "v_min_price": vmin_price,
            # ... and None when the airworthiness filters are not either.
            "airworthiness_price": air_price,
            "stall_detail": stall,
            "neutral_point_m": sm["x_np_m"],
            "sm_local_slopes": sm.get("sm_local_slopes"),
            "J_vs_peak": {"J_cruise": best["J"], "J_peak_eta": best["J_peak_eta"]},
            "uncalibrated_construction": [
                k for k, v in printed_breakdown.items() if not v["calibrated"]
            ],
            "sweep_dropped": {
                "total": len(dropped),
                "trim_not_converged": [s["V_ms"] for s in unproven],
                "propulsion": [
                    s["V_ms"] for s in dropped if s.get("cause") == "propulsion"
                ],
            },
        },
        notes=[
            "Stall via wing-level CLmax knockdown; critical-section method arrives at M2/M3.",
            "Smooth polars only; tripped-polar dual evaluation arrives at M2.",
            "Propulsion chain is uncalibrated (no measurement path) — rankings over absolutes.",
        ],
    )

    if vmin_price is not None:
        cost = vmin_price["cost_of_v_min"]
        result.notes.append(
            f"THE OBJECTIVE IS LIMITED BY v_min, NOT BY THE AIRFRAME: the best "
            f"legal point is {best['V_ms']:.2f} m/s, and the sweep's own optimum "
            f"is {vmin_price['unconstrained_best_V_ms']:.2f} m/s"
            + (f", worth {cost:.2f} {objective.units} more" if cost is not None else "")
            + f". Relaxing the {mission.v_min_ms:.2f} m/s minimum-speed "
            "requirement, not the aircraft, is what buys that back."
        )
    if air_price is not None:
        by = ", ".join(air_price["peak_excluded_by"]) or "an airworthiness rule"
        counts = ", ".join(
            f"{name} dropped {len(vs)}" for name, vs in air_price["excluded_by_rule"].items()
        )
        result.notes.append(
            f"THE HEADLINE NUMBER IS SET BY AN AIRWORTHINESS FILTER, NOT BY THE "
            f"AEROPLANE'S BEST POINT: the sweep peaks at "
            f"{air_price['unfiltered_objective']:.2f} {objective.units} at "
            f"{air_price['unfiltered_best_V_ms']:.2f} m/s, and that point is "
            f"excluded by {by}. What is reported is "
            f"{air_price['reported_objective']:.2f} {objective.units} at "
            f"{best['V_ms']:.2f} m/s — {air_price['cost_of_airworthiness']:.2f} "
            f"{objective.units} less ({counts} of "
            f"{len([s for s in feasible if s['V_ms'] >= mission.v_min_ms - 1e-9])} "
            "trimmed points at or above v_min). Read the reported trim deflection, "
            "advance ratio and CL as properties of the ONE point that survived the "
            "filters, not as evidence the design is comfortably inside them."
        )
    if unproven:
        speeds = ", ".join(f"{s['V_ms']:.1f}" for s in unproven)
        result.notes.append(
            f"NOT PROVEN INFEASIBLE — trim did not converge at V = {speeds} m/s "
            "(the 2-D root-find ran out of progress from every start it was "
            "given). These points are excluded from the sweep because there is "
            "no operating point to report, not because none exists; read them as "
            "unknown rather than as a limit of the aeroplane."
        )
    if not sm_sign_consistent:
        worst = worst_unstable
        log.warning(
            "static margin changes sign inside its own regression window: "
            "reported %.4f, but the local slope at alpha = %.2f deg is %.4f",
            sm["static_margin"], worst["alpha"], worst["sm_local"],
        )
        result.notes.append(
            f"STATIC MARGIN CHANGES SIGN INSIDE ITS OWN WINDOW: the reported "
            f"{sm['static_margin']:.4f} is a least-squares slope over "
            f"{list(aero.SM_ALPHA_OFFSETS)} deg about trim, but the LOCAL "
            f"dCm/dCL at alpha = {worst['alpha']:.2f} deg is "
            f"{worst['sm_local']:+.4f} — the aircraft is not positively stable "
            "there on this model. Cm(alpha) nonlinearity is the known dominant "
            "fidelity limit of this SM estimator (FINDINGS); treat the margin as "
            "an average, and do not fly the CG on the strength of it alone."
        )

    run_dir = assemble.write_run_dir(result, runs_root, input_files or [])
    log.info("writing artifacts to %s", run_dir)
    figures.power_curves(sweep, mission, objective, run_dir / "figures")
    figures.stall_spanwise(stall, run_dir / "figures")
    planes = {"current": airplane}
    if dv is not None:
        planes = {"baseline (defaults)": aircraft.geometry(None), "optimized": airplane}
    figures.planform_compare(planes, run_dir / "figures")
    # viz twin: attach the fuselage loft(s) for the 3D artifacts only — the aero
    # airplane stays wings-only (LL would double-count fuselage drag, section 7)
    viz_plane = airplane
    if hasattr(aircraft, "fuselage_lofts"):
        import aerosandbox as asb

        lofts = aircraft.fuselage_lofts(dv)
        if lofts:
            viz_plane = asb.Airplane(
                name=airplane.name, wings=airplane.wings, fuselages=lofts,
                s_ref=airplane.s_ref, c_ref=airplane.c_ref, b_ref=airplane.b_ref,
            )
    figures.three_view(viz_plane, run_dir / "figures")
    figures.interactive_3d(viz_plane, run_dir)
    # Buildable geometry: the loft definition and the placed 3D curves. A report
    # tells you whether the design is good; these tell you how to cut it, and
    # they come from the same airplane object that was analysed.
    geometry_export.write(airplane, run_dir)
    # Build document: the same geometry again, but answering "what do I cut and
    # what must I hit" — spars, hinges, edge polylines and the CG window.
    manufacturing.write(result, airplane, aircraft, run_dir)
    (run_dir / "report.html").write_text(report_html.render(result, run_dir), encoding="utf-8")
    return result, run_dir


# --------------------------------------------------------------------------- M2

M2_STATUS = "M3: full-vehicle optimization (wing + tail + balance + spars + trim) + numeric re-evaluation"


#: What `--warm-start` has to ask IPOPT for, beyond seeding `inits`.
#:
#: Seeding primal values alone was measured as a WASH on this model, and the
#: reason is in the champion: it sits on eight declared bounds. IPOPT's default
#: `bound_push`/`bound_frac` of 0.01 shove any starting point 1% of each range
#: away from its bounds, and `mu_init` 0.1 starts the barrier far from the
#: boundary as well — so a seed whose whole value is that it already sits ON
#: those bounds gets pushed off them before the first iteration, and the solver
#: walks back. These are the options that make the seed actually be the starting
#: point (IPOPT honours the `warm_start_*` family only when
#: `warm_start_init_point` is on).
#:
#: **Measured 2026-07-31, and it still does not pay.** Same aircraft, same
#: mission, seeded with the previous champion's own design vector — the most
#: favourable case there is, since the seed IS the answer:
#:
#:     cold                                  5.35 min
#:     warm, seed only                       6.78 min   (+27%)
#:     warm, seed + these options            5.58 min   (+4%)
#:
#: All three return 120.12168 min to eight significant figures, so the seed is
#: not changing WHERE it lands, only how long it takes to get there — and it
#: does not get there faster. The fix is real (it recovers most of the loss the
#: seed-only path was causing) and the honest conclusion is still: do not reach
#: for `--warm-start` expecting speed. `_solve_nlp` logs that when it is used.
#:
#: Why it cannot do better: only the primal point is seeded, because a run
#: artifact records `dv` and not IPOPT's multipliers. An interior-point method
#: restarted without duals has to rebuild them, and on a problem sitting on
#: eight active bounds that is most of the work.
WARM_START_OPTIONS = {
    "ipopt.warm_start_init_point": "yes",
    "ipopt.warm_start_bound_push": 1e-6,
    "ipopt.warm_start_bound_frac": 1e-6,
    "ipopt.warm_start_slack_bound_push": 1e-6,
    "ipopt.warm_start_slack_bound_frac": 1e-6,
    "ipopt.warm_start_mult_bound_push": 1e-6,
    "ipopt.mu_init": 1e-4,
}


#: What IPOPT's own iteration log is read for, and what those numbers are called
#: in the frame. All of it comes from `opti.debug.stats()` INSIDE the callback,
#: which is a dict lookup — no CasADi function is built and the ~14.5 GB graph
#: is never touched. Measured at 0.08 ms per call on a toy problem.
#:
#: `obj` is renamed on the way out because it is NOT the reported objective: it
#: is whatever `Objective.nlp_expression` handed the solver, which for endurance
#: is a monotone surrogate rather than minutes (FINDINGS section 14.5.5). A live
#: view that labelled it "objective" would be showing a number that does not
#: match the one the run finally reports.
_IPOPT_ITERATION_FIELDS = {
    "obj": "ipopt_objective",
    "inf_pr": "inf_pr",
    "inf_du": "inf_du",
    "mu": "mu",
}


def _live_frame_callback(opti, frames, dv: dict, state: dict):
    """An `Opti` callback that writes one live frame per IPOPT iterate, or None.

    Two measurements decided the shape of this (2026-08-05, `docs/
    LIVE_VIEWER_PLAN.md` section 1):

    - Reading the design vector back is cheap, but only if it is read as ONE
      stacked expression. `opti.debug.value` builds a CasADi Function per call,
      so 37 separate calls per iterate is 37 graph traversals; one `vertcat` of
      leaf variables is 0.12 ms, against iterations that take ~1.5 s on this
      model.
    - Everything ELSE worth showing is free. `opti.debug.stats()` works during
      the solve and already carries IPOPT's own objective, primal and dual
      infeasibility and barrier parameter. Watching `inf_pr` fall is half the
      debugging value and it costs a dict lookup, where evaluating `opti.f`
      would mean building a function over the whole NLP graph.

    **This must never raise.** It runs inside IPOPT's iteration loop, so an
    exception here is an aborted solve rather than a missing picture. The
    writer's own latch covers the frame-building half; this wrapper covers the
    reading half.
    """
    import casadi as cas

    try:
        # Scalars only. `dv` is whatever the AIRCRAFT declared, so a vector
        # variable is possible in principle, and splitting one back out by name
        # is not worth doing for a picture. Building the callback is inside the
        # guard as well: "frames can never fail a solve" has to hold before the
        # first iterate, not only during one.
        scalars = [(k, v) for k, v in dv.items() if getattr(v, "numel", lambda: 1)() == 1]
        if not scalars:
            return None
        names = [k for k, _ in scalars] + list(state)
        stacked = cas.vertcat(*[v for _, v in scalars], *state.values())
    except Exception as e:  # noqa: BLE001
        frames.writer.fail(e)
        return None

    def callback(iteration: int) -> None:
        try:
            values = np.asarray(opti.debug.value(stacked)).ravel()
            read = dict(zip(names, (float(v) for v in values)))
            try:
                iterations = (opti.debug.stats() or {}).get("iterations") or {}
            except Exception:  # noqa: BLE001 — stats are a bonus, not the frame
                iterations = {}
            measured = {
                out: float(iterations[key][-1])
                for key, out in _IPOPT_ITERATION_FIELDS.items()
                if iterations.get(key)
            }
            frames.iterate(
                iteration,
                {k: read[k] for k, _ in scalars},
                {k: read[k] for k in state},
                measured,
            )
        except Exception as e:  # noqa: BLE001 — a picture must not abort a solve
            frames.writer.fail(e)

    return callback


def _solve_nlp(
    aircraft,
    mission,
    inits: dict | None = None,
    fixed: dict | None = None,
    extra_mass_kg: float = 0.0,
    printed_scale: float = 1.0,
    eta_scale: float = 1.0,
    timeout_min: float = SOLVE_TIMEOUT_MIN,
    max_iter: int = SOLVE_MAX_ITER,
    warm_start: bool = False,
    frames=None,
) -> dict:
    """One NLP solve. Returns the champion design + state, all numeric.

    M2 scope note: lift=weight and thrust=drag are enforced; pitch-moment trim and
    static margin join at M3 (tail is fixed here). Objective from the mission
    registry evaluator, built symbolically.

    `frames` is a `liveframe._Member`, or None. When present, every IPOPT
    iterate writes a geometry frame for the live viewer (M5.4) — see
    `_live_frame_callback` for what that costs and why it is safe.
    """
    import aerosandbox as asb

    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()

    opti = asb.Opti()
    # Record which source line each constraint row comes from, so that if this
    # solve fails the artifact can name the constraint it could not satisfy
    # rather than a row index (_ConstraintLabels).
    labels = _ConstraintLabels(opti)
    # Record the aircraft's declared box while it is being declared — the only
    # moment the framework can see it (_DeclaredBounds).
    declared = _DeclaredBounds(opti)
    try:
        dv = aircraft.design_variables(opti, inits)
    finally:
        declared.stop()
    bodies = aircraft.parasite_bodies(dv)  # may be symbolic (fuselage loft)
    # Operating-point box bounds. These are numerical brackets, not physics —
    # the physics is in the constraints below — but a bracket sized for a loiter
    # plane silently caps a speed design (V at 25 m/s, elevator at 15 deg). The
    # aircraft may therefore declare its own envelope; the defaults are the
    # values every M0-M4.8 run used, so declared-free aircraft are unaffected.
    envelope = getattr(aircraft, "operating_bounds", None) or {}
    v_lo, v_hi = envelope.get("V_ms", (6.0, 25.0))
    a_lo, a_hi = envelope.get("alpha_deg", (-2.0, 10.0))
    d_lo, d_hi = envelope.get("deflection_deg", (-15.0, 15.0))
    n_lo, n_hi = envelope.get("prop_rev_s", (20.0, 200.0))
    V = opti.variable(
        init_guess=(inits or {}).get("V", 11.0), lower_bound=v_lo, upper_bound=v_hi
    )
    alpha = opti.variable(init_guess=4.0, lower_bound=a_lo, upper_bound=a_hi)
    defl = opti.variable(init_guess=0.0, lower_bound=d_lo, upper_bound=d_hi)
    n = opti.variable(init_guess=65.0, lower_bound=n_lo, upper_bound=n_hi)

    for k, val in (fixed or {}).items():
        opti.subject_to(dv[k] == val)

    airplane = aircraft.geometry(dv)
    components, _ = massmodel.build(aircraft, airplane, dv, printed_scale=printed_scale)
    totals = massmodel.totals(components)
    auw = totals["auw_kg"] + extra_mass_kg
    x_cg = totals["x_cg_m"]
    weight_n = auw * G

    # cruise point: trimmed (explicit deflection of the aircraft-declared pitch
    # surface — "ruddervator", "elevator", ... — Cm about produced CG)
    pitch_control = getattr(aircraft, "pitch_control_name", "ruddervator")
    plane_defl = airplane.with_control_deflections({pitch_control: defl})
    aero_run = asb.LiftingLine(
        airplane=plane_defl,
        op_point=asb.OperatingPoint(velocity=V, alpha=alpha),
        xyz_ref=[x_cg, 0, 0],
        # NOT the AeroSandbox default — see aero.LL_VORTEX_CORE_RADIUS. At 1e-8
        # this model returns negative drag on a strongly canted winglet, and the
        # optimizer finds it.
        vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS,
    ).run()
    q = 0.5 * 1.225 * V**2
    s_ref = airplane.s_ref
    drag = aero_run["D"] + q * s_ref * aero.body_cd0(bodies, V, s_ref)

    pr = propulsion.chain(V, n, pt)
    opti.subject_to(aero_run["L"] == weight_n)
    opti.subject_to(aero_run["Cm"] == 0)  # pitch trim
    opti.subject_to(pr["thrust_n"] == drag)
    opti.subject_to(pr["J"] < 0.95 * pr["j_max"])  # stay on the fitted table

    # static margin about the produced CG: regression slope over the shared
    # alpha window (LL's local Cm derivative is noisy — FINDINGS.md), plus the
    # Munk fuselage destabilizing term converted to CL-space via the lift slope.
    # The estimator itself lives in aero, so the numeric re-evaluation below
    # measures the same quantity this constraint holds (aero.SM_ALPHA_OFFSETS).
    offs = aero.SM_ALPHA_OFFSETS
    sm_runs = [
        asb.LiftingLine(
            airplane=airplane,
            op_point=asb.OperatingPoint(velocity=V, alpha=alpha + o),
            xyz_ref=[x_cg, 0, 0],
            vortex_core_radius=aero.LL_VORTEX_CORE_RADIUS,
        ).run()
        for o in offs
    ]
    sm = aero.static_margin_from_polar(
        [r["CL"] for r in sm_runs], [r["Cm"] for r in sm_runs],
        list(offs), bodies, s_ref, airplane.c_ref,
    )
    opti.subject_to(sm >= mission.static_margin_range[0])
    opti.subject_to(sm <= mission.static_margin_range[1])

    # stall: critical-section method (Schrenk loading + local clmax(Re) fit),
    # evaluated at the mission stall-speed limit — MODEL_DETAILS 3.4
    clmax_ab = aero.clmax_log_fit(airplane.wings[0].xsecs[0].airfoil)
    if mission.v_stall_max_ms is not None:
        v_s = mission.v_stall_max_ms
        cl_stall = 2 * weight_n / (1.225 * v_s**2 * s_ref)
        stations = aero.wing_stations(airplane.wings[0])
        ratios = aero.critical_section_ratios(
            stations, s_ref, airplane.b_ref, cl_stall, v_s, clmax_ab
        )
        opti.subject_to(aero.smooth_max(ratios) <= 1.0)
    # gust margin (MODEL_DETAILS section 4), wing-level clmax from the same fit.
    # c_ref (area / material span), NOT s_ref/b_ref: b_ref is projected span, and
    # via that route extra dihedral would inflate the modeled chord Re and game
    # the gust constraint.
    c_mean = airplane.c_ref
    re_cruise = 1.225 * V * c_mean / 1.81e-5
    clmax_wing = 0.9 * (clmax_ab[0] + clmax_ab[1] * np.log(re_cruise))
    opti.subject_to(aero_run["CL"] <= 0.7 * clmax_wing)
    if objective.wind_mode == "constraint":
        opti.subject_to(V >= mission.v_min_ms)
    if mission.ballast_max_kg is not None and "ballast_kg" in dv:
        opti.subject_to(dv["ballast_kg"] <= mission.ballast_max_kg)
    # MODEL-VALIDITY ceiling on lift-to-drag, declared by the aircraft. Not a
    # design preference and not a prediction — the same posture as
    # speed_sample's `aspect_ratio_min`: past some L/D the number this model
    # reports is not aerodynamics any more, and an optimizer that reaches it has
    # found a hole rather than an aeroplane. On 2026-08-01 two solves rode a
    # lifting-line artefact to an L/D of 889 and the powertrain's idle-power
    # ceiling (FINDINGS §18); `aero.LL_VORTEX_CORE_RADIUS` fixed that particular
    # hole, and this refuses the NEXT one up front instead of after the battery.
    ld_max = getattr(aircraft, "lift_to_drag_max", None)
    if ld_max is not None:
        # Written as a DRAG FLOOR (drag >= W / ld_max), not as `L/drag <= ld_max`.
        # The natural form is satisfied by negative drag — a negative number is
        # comfortably below any ceiling — which would have let the exact iterate
        # this constraint exists to refuse walk straight through it. Against the
        # WEIGHT rather than the lift, because lift is only equal to weight at a
        # converged point and may be anything on the way there, while weight is a
        # sum of positive masses at every iterate. Dimensionless, like every other
        # row here (FINDINGS §14.5).
        opti.subject_to(drag * ld_max / weight_n >= 1.0)
    aircraft.geometry_constraints(opti, dv, V, deflection_deg=defl)
    aircraft.structure_constraints(opti, dv, weight_n)

    # --- powertrain envelope (MODEL_DETAILS section 2.5) ---
    # Real limits, not preferences: the motor cannot be fed more than the pack
    # holds (terminal voltage <= pack voltage IS throttle <= 100%), and current
    # must stay inside the rating this objective is allowed to use. Both are
    # slack by orders of magnitude at a loiter point and both bind on a speed
    # objective — without them "maximize speed" is bounded only by where the
    # prop fit runs out, which is an artefact rather than an airplane.
    opti.subject_to(pr["voltage"] <= pt.battery.v_nominal)
    current_cap = (
        pt.motor.max_current_a
        if objective.current_limit == "burst"
        else pt.esc_continuous_current_a
    )
    opti.subject_to(pr["current_a"] <= current_cap)
    # Declared placard speed: flutter and divergence are beyond this model, so a
    # speed objective is capped by a number the aircraft declares rather than by
    # a prediction the model cannot make (MODEL_DETAILS section 2.5).
    placard = getattr(aircraft, "placard_speed_ms", None)
    if placard is not None:
        opti.subject_to(V <= float(placard))

    p_bus_eff = pr["p_bus_w"] / eta_scale  # eta_scale: chain-efficiency re-solves
    # Two expressions, deliberately: `obj_expr` is what gets REPORTED, in the
    # objective's own units, and is read back from the solution below. What the
    # solver minimizes may be a better-behaved monotone equivalent — endurance's
    # reported form is a quotient with a pole inside the variable box
    # (mission.Objective.nlp_surrogate, FINDINGS §14.5.5).
    obj_expr = objective.evaluator(V, p_bus_eff, mission, pt)
    opti.minimize(objective.nlp_expression(V, p_bus_eff, mission, pt))

    # detect_simple_bounds: hand the plain variable bounds to IPOPT as BOUNDS
    # rather than as ordinary constraint rows. Without it the box lives in `g`,
    # which an interior-point method is free to violate on the way to a
    # solution — so the model gets evaluated at negative chords and negative
    # boom lengths, and the resulting NaN is a solver failure rather than a
    # rejected point. It also drops 2 rows per design variable from the
    # Jacobian.
    labels.stop()

    #: Was the iteration ceiling lowered on purpose? A run at the default 1000
    #: that exhausts it has genuinely failed; one at 3 has done exactly what was
    #: asked. The two want opposite treatment and only this tells them apart.
    truncated = max_iter < SOLVE_MAX_ITER

    def _pack(value) -> dict:
        """The member result, read through `value` — the converged solution or,
        for a truncated run, `opti.debug.value` on the last iterate.

        One function so the two paths cannot drift into reporting different
        fields, which would make a capped smoke run exercise a writer that the
        real run never uses.
        """
        return {
            "dv": {k: float(value(v)) for k, v in dv.items()},
            # the variables this solution is PINNED against, and the box they
            # were declared in — see _DeclaredBounds
            "active_bounds": declared.active(dv, value),
            "dv_bounds": declared.boxes(dv),
            "V_ms": float(value(V)),
            "alpha_deg": float(value(alpha)),
            "deflection_deg": float(value(defl)),
            "rpm": float(value(n)) * 60,
            "objective_value": float(value(obj_expr)),
            "auw_kg": float(value(auw)),
            "x_cg_m": float(value(x_cg)),
            "static_margin": float(value(sm)),
            "P_elec_w": float(value(p_bus_eff)),
            "motor_voltage": float(value(pr["voltage"])),
            "motor_current_a": float(value(pr["current_a"])),
            "throttle_frac": float(value(pr["voltage"])) / pt.battery.v_nominal,
            "current_cap_a": current_cap,
            "placard_speed_ms": float(placard) if placard is not None else None,
            "drag_n": float(value(drag)),
            "J": float(value(pr["J"])),
            "clmax_ab_used": clmax_ab,
        }

    options = {"ipopt.max_wall_time": 60.0 * timeout_min}
    if warm_start:
        options |= WARM_START_OPTIONS
    callback = None
    if frames is not None:
        callback = _live_frame_callback(
            opti, frames, dv,
            {"V_ms": V, "alpha_deg": alpha, "deflection_deg": defl, "prop_rev_s": n},
        )
    try:
        sol = opti.solve(
            verbose=False,
            max_iter=max_iter,
            detect_simple_bounds=True,
            callback=callback,
            # WALL time, not CPU time. AeroSandbox's own `max_runtime` maps to
            # IPOPT's `max_cpu_time`, which is the wrong unit for this guard: a
            # solve peaks near 14.5 GB on a 25 GB machine, and the case worth
            # bailing out of is exactly the one where it starts swapping and CPU
            # time falls behind the clock. What is being protected is the run's
            # wall clock, so that is what gets capped.
            options=options,
        )
    except RuntimeError as e:
        failure = SolveFailure(opti, e, labels.as_dict())
        # A DELIBERATELY truncated solve is not a failed one. `--max-iter 3`
        # exists to run the whole pipeline cheaply (FINDINGS §24.2), and every
        # member of such a run ends on `Maximum_Iterations_Exceeded` by
        # construction — so treating that as a failure made the flag crash the
        # very pipeline it was added to exercise: all members "failed", `ok` was
        # empty, and `optimize` died on `max() iterable argument is empty` after
        # 2.5 minutes with no artifact (2026-08-06, FINDINGS §27).
        #
        # The last iterate is a real point in the box — IPOPT keeps the design
        # variables inside their bounds — and `opti.debug` reads it with the
        # same accessor `sol` provides. It is NOT feasible, so it is marked, and
        # the run already shouts "THIS RUN IS NOT AN OPTIMIZATION." at notes[0].
        #
        # Guarded three ways, because harvesting the wrong thing here would put
        # a garbage champion into a run that looks complete: only when the cap
        # was lowered on purpose, only for the iteration status (a restoration
        # failure or an infeasible corner has nothing worth keeping), and only
        # if every harvested number is finite.
        if truncated and failure.return_status == "Maximum_Iterations_Exceeded":
            try:
                out = _pack(opti.debug.value)
            except (RuntimeError, TypeError, ValueError):
                raise failure from None
            if all(np.isfinite(v) for v in out["dv"].values()) and np.isfinite(
                out["objective_value"]
            ):
                out |= {
                    "return_status": failure.return_status,
                    "iter_count": failure.iter_count,
                    "iteration_truncated": True,
                    "converged": False,
                }
                return out
        raise failure from None
    return _pack(sol)


def _solve_worker(conn, aircraft, mission, kw, live=None):  # pragma: no cover — child process
    t0 = time.monotonic()
    # The WORKER writes its own frames, both iterate and candidate — not the
    # parent. The parent cannot write the candidate one correctly: `prep`/
    # `restore` bracket the launch, so by the time a child's result comes back
    # the parent's aircraft object has been restored to the baseline and would
    # draw a different aeroplane under this member's name. The child forked with
    # the member's attributes already applied and keeps them for its whole life.
    member = None
    if live is not None:
        from .liveframe import FrameWriter

        live_dir, label, key, index, total = live
        member = FrameWriter(live_dir, aircraft).member(label, key, index, total)
    try:
        r = _solve_nlp(aircraft, mission, frames=member, **kw)
    except Exception as e:
        r = _failure_record(e)
    r["solve_minutes"] = round((time.monotonic() - t0) / 60.0, 2)
    # A forked worker is the only place a genuine per-solve peak can be read:
    # this process did exactly one solve, so its high-water mark IS that solve's.
    # It is what the next run's memory budget divides by (memory.py).
    r["peak_rss_gb"] = memory.peak_rss_gb()
    if member is not None:
        member.candidate(r)
    conn.send(r)
    conn.close()


def parallel_available() -> bool:
    """Whether concurrent solves are possible on this platform.

    Workers inherit the aircraft/mission objects across the fork instead of
    pickling them — those objects carry bound methods and CasADi state and are
    not picklable, so `spawn` (the only start method on Windows) cannot serve
    them. Concurrency is therefore POSIX-only; every other feature is portable.
    """
    import multiprocessing as mp

    return "fork" in mp.get_all_start_methods()


def check_parallel(parallel: int) -> None:
    """Reject an impossible width up front, not after the first batch.

    Two ways a width can be impossible, and both are worth catching here rather
    than hours in: no `fork` at all (Windows), or a macOS process whose
    Accelerate BLAS was already multi-threaded when the fork happened. The
    second is the nastier one — it does not refuse, it segfaults every worker,
    and `_solve_many` can only see that the child died without reporting, which
    it attributes to the OOM killer (`planeopt._make_fork_safe_on_macos`).
    """
    if parallel > 1 and not parallel_available():
        raise RuntimeError(
            f"parallel={parallel} needs the 'fork' start method, which this platform "
            "(Windows) does not have — the aircraft definition cannot be pickled for "
            "a spawned worker. Run with parallel=1; solves then run one at a time."
        )
    if parallel > 1 and planeopt._FORK_SAFE_MACOS is False:
        raise RuntimeError(
            f"parallel={parallel} is unsafe in this process: NumPy was imported before "
            "planeopt, so Apple's Accelerate BLAS had already started its dispatch "
            "pool and VECLIB_MAXIMUM_THREADS=1 came too late to stop it. Forked "
            "workers would segfault on their first matrix multiply, and would be "
            "reported as 'worker died before reporting (OOM?)' — a memory problem "
            "this is not. Either import planeopt before NumPy, or set "
            "VECLIB_MAXIMUM_THREADS=1 in the environment before launching. Run with "
            "parallel=1 to solve one at a time."
        )


def _log_result(label: str, key, done: int, total: int, result: dict) -> None:
    # THIS solve's minutes, not the batch's elapsed time: a sequential batch
    # reported cumulative time against every member, which reads as though each
    # one got slower than the last.
    mins = result.get("solve_minutes") or 0.0
    peak = result.get("peak_rss_gb") or 0.0
    ram = f", peak {peak:.1f} GB" if peak else ""
    if "failed" in result:
        log.info("  %s [%d/%d] %s: FAILED — %s (%.1f min%s)",
                 label, done, total, key, result["failed"], mins, ram)
    else:
        log.info("  %s [%d/%d] %s: objective %.4g (%.1f min%s)",
                 label, done, total, key, result["objective_value"], mins, ram)


def screen_discrete(
    aircraft, mission, attr: str, candidates: list, incumbent: dict,
    top_n: int, shadow_per_g: float | None = None,
) -> dict:
    """Rank `candidates` without solving anything (M5.3, EXECUTION_PLAN §6).

    A discrete study costs one full NLP re-solve per candidate, which is why the
    prop study priced 3 of 443 shipped tables and adopted one that screened
    119th of 441 (FINDINGS §12). The fix is not a longer shortlist, it is a
    cheaper first pass: hold the champion's AIRFRAME and operating point fixed,
    re-solve only the powertrain for each candidate (`propulsion.solve`, seconds,
    no NLP), and hand the full optimizer just the top `top_n`.

    **Opt-in per attribute, because the screen is only valid where the attribute
    changes nothing the airframe solve fixed.** An aircraft declares
    `discrete_screen = {attr: top_n}` and is asserting exactly that — true of a
    propeller, false of a tail type. The framework cannot detect it: it would
    have to know what an attribute means.

    Two effects are priced, and they pull opposite ways:

    - **Powertrain**, through the objective's own evaluator at the incumbent's
      (V, thrust). This is what a bigger or coarser prop buys.
    - **Mass**, through `fixed_equipment` and the run's OWN measured shadow
      price (minutes per gram). Without it the screen is systematically biased
      toward big propellers, because a 14 in disc arrives weightless — the exact
      defect that kept the diameter cap at 11 in until 2026-07-30.

    What it still cannot see is re-optimization: a candidate that would repay its
    mass by reshaping the wing looks worse here than it is. So this is a
    SHORTLISTER and never a verdict — the returned candidates are re-solved in
    full, and the incumbent is always among them by construction.
    """
    from . import propulsion

    objective = OBJECTIVES[mission.objective]
    sign = 1 if objective.direction == "maximize" else -1
    V, thrust = incumbent["V_ms"], incumbent["drag_n"]
    dv = incumbent.get("dv")

    def equipment_mass_kg() -> float:
        try:
            return sum(e.mass_kg for e in aircraft.fixed_equipment(dv))
        except Exception:  # noqa: BLE001 — a screen must never sink a run
            return 0.0

    original = getattr(aircraft, attr)
    base_mass = equipment_mass_kg()
    ranked, failed = [], {}
    try:
        for cand in candidates:
            setattr(aircraft, attr, cand)
            try:
                pt = aircraft.powertrain()
                pr = propulsion.solve(V, thrust, pt)
                value = objective.evaluator(V, pr["P_elec_w"], mission, pt)
                dm_g = (equipment_mass_kg() - base_mass) * 1000.0
                penalty = (shadow_per_g or 0.0) * dm_g
                ranked.append({
                    "candidate": cand,
                    "screened_objective": float(value + penalty),
                    "powertrain_only": float(value),
                    "mass_delta_g": float(dm_g),
                })
            except (ValueError, FileNotFoundError, KeyError) as e:
                # A prop too fine or too coarse for this design at this speed is
                # a legitimate screen result, not an error: it is how the screen
                # says "not this one".
                failed[cand] = str(e)[:160]
    finally:
        setattr(aircraft, attr, original)

    ranked.sort(key=lambda r: -sign * r["screened_objective"])
    return {
        "ranking": ranked,
        "unreachable": failed,
        "shortlist": [r["candidate"] for r in ranked[:top_n]],
        "shadow_price_obj_per_gram": shadow_per_g,
        "note": "airframe held fixed at the incumbent; mass priced at the run's "
                "own shadow price; top candidates are re-solved in full",
    }


class _PeakTracker:
    """Largest per-solve RSS peak seen so far, in GB.

    Process-global on purpose: the thing it tracks (the kernel's RSS high-water
    mark) is process-global too. It exists because the in-process path now
    RESETS that mark between solves to get honest per-solve numbers — which
    means the run-level peak can no longer be read off the process at the end,
    since the mark then only reflects the last solve.
    """

    def __init__(self) -> None:
        self.gb = 0.0

    def reset(self) -> None:
        self.gb = 0.0

    def observe(self, gb: float | None) -> None:
        self.gb = max(self.gb, gb or 0.0)


RUN_PEAK = _PeakTracker()


def _solve_many(
    aircraft, mission, jobs, parallel: int = 1, prep=None, restore=None,
    label: str = "solve", timeout_min: float = SOLVE_TIMEOUT_MIN,
    max_iter: int = SOLVE_MAX_ITER,
    cache: "_SolveCache | None" = None, pause_file: Path | None = None,
    live=None,
) -> dict:
    """Run independent _solve_nlp jobs, `parallel` at a time.

    jobs: [(key, kwargs)] -> {key: result | {"failed": ...}}. prep(key)/restore()
    bracket each launch so per-candidate aircraft attrs (discrete studies,
    winglet toggles) are seen by that job only — with parallel > 1 the forked
    child snapshots them at launch. parallel=1 is the historical in-process
    path and the only safe mode under a ~15 GB WSL cap (each solve peaks
    ~14.5 GB — measured 2026-08-05); 2-wide needs the 26 GB .wslconfig active.
    A job failure never kills the batch. `label` names the batch in the
    progress log.

    `cache` makes each finished member durable, so a stopped run continues
    rather than restarting; `pause_file`, if it exists when a member finishes,
    stops the battery cleanly at that boundary (RunPaused). Member boundaries
    are the only place a pause can free memory — see `optimize`.

    `live` is a `liveframe.FrameWriter` or None: the M5.4 viewer's data source.
    Frames are a VIEW of the run and never a part of it — the writer disables
    itself on its first error and the batch does not notice.
    """
    check_parallel(parallel)
    results = {}
    jobs = [(key, {"timeout_min": timeout_min, "max_iter": max_iter, **kw})
            for key, kw in jobs]
    total = len(jobs)
    log.info("%s: %d solve(s), %d-wide", label, total, max(1, parallel))
    if parallel <= 1:
        for key, kw in jobs:
            done = cache.get(label, key) if cache is not None else None
            if done is not None:
                results[key] = done
                log.info("  %s [%d/%d] %s: from checkpoint", label, len(results), total, key)
                # No live frame for a resumed member, deliberately. `prep` has
                # not run, so the aircraft is not carrying this member's discrete
                # configuration and any frame drawn now would be a picture of a
                # different aeroplane. Nothing is lost: frames survive a pause in
                # the live directory exactly as checkpoints do, so the run that
                # solved this member already recorded it.
                continue
            if prep is not None:
                prep(key)
            # In-process, the RSS high-water mark only ever rises, so without a
            # reset every member inherits the largest solve that ran before it
            # (memory.reset_peak_rss — this is what made the 2026-07-31 winglet
            # solves look 2.7 GB heavier than the rest of the run when they are
            # the lightest in it). Where the reset is unavailable the number
            # keeps its old watermark meaning and SAYS so.
            per_solve_peak = memory.reset_peak_rss()
            t_job = time.monotonic()
            member = (
                live.member(label, key, len(results) + 1, total)
                if live is not None else None
            )
            try:
                try:
                    results[key] = _solve_nlp(aircraft, mission, frames=member, **kw)
                except RuntimeError as e:
                    results[key] = _failure_record(e)
                # Timed before the candidate frame, which runs its own lifting
                # line: a picture of the solve must not be charged to the solve.
                results[key]["solve_minutes"] = round((time.monotonic() - t_job) / 60.0, 2)
                # ... and written BEFORE `restore`, because a discrete study's
                # member carries its own attribute value (a prop, a tail type)
                # and `restore` puts the baseline back — a frame drawn afterwards
                # would show a different aeroplane under this member's name.
                if member is not None:
                    member.candidate(results[key])
            finally:
                if restore is not None:
                    restore()
            results[key]["peak_rss_gb"] = memory.peak_rss_gb()
            RUN_PEAK.observe(results[key]["peak_rss_gb"])
            if not per_solve_peak:
                results[key]["peak_rss_is_batch_watermark"] = True
            _log_result(label, key, len(results), total, results[key])
            if cache is not None:
                cache.put(label, key, results[key])
            if pause_file is not None and Path(pause_file).exists():
                raise RunPaused(
                    f"paused after {label}/{key} — {len(results)} of {total} members "
                    f"of this phase are checkpointed"
                )
        return results

    import multiprocessing as mp
    from multiprocessing.connection import wait as conn_wait

    ctx = mp.get_context("fork")  # children inherit aircraft/mission — no pickling
    pending = list(jobs)
    running = {}  # receiving pipe end -> (key, process)
    while pending or running:
        while pending and len(running) < parallel:
            key, kw = pending.pop(0)
            done = cache.get(label, key) if cache is not None else None
            if done is not None:
                results[key] = done
                log.info("  %s [%d/%d] %s: from checkpoint", label, len(results), total, key)
                continue
            rx, tx = ctx.Pipe(duplex=False)
            if prep is not None:
                prep(key)
            # Members are tagged into every frame filename, so concurrent
            # workers sharing a directory cannot overwrite each other. What they
            # DO share is the sequence counter, which each initialises from the
            # directory at fork time — so in forked mode the global ordering
            # between members is coarse (frames interleave by iteration rather
            # than by wall clock). Within a member it stays exact, which is what
            # the timelapse needs.
            live_spec = (
                (live.dir, label, key, len(results) + len(running) + 1, total)
                if live is not None else None
            )
            proc = ctx.Process(
                target=_solve_worker, args=(tx, aircraft, mission, kw, live_spec)
            )
            proc.start()
            tx.close()
            if restore is not None:
                restore()
            running[rx] = (key, proc)
        for rx in conn_wait(list(running)):
            key, proc = running.pop(rx)
            try:
                results[key] = rx.recv()
            except EOFError:  # child died without reporting — OOM killer, most likely
                results[key] = {"failed": "worker died before reporting (OOM?)"}
            proc.join()
            rx.close()
            # a forked worker did exactly one solve, so its mark IS that solve's
            RUN_PEAK.observe(results[key].get("peak_rss_gb"))
            _log_result(label, key, len(results), total, results[key])
            if cache is not None:
                cache.put(label, key, results[key])
        # A pause waits for the whole in-flight group: killing a running child
        # would throw away a solve that is minutes from finishing.
        if pause_file is not None and Path(pause_file).exists() and not running:
            raise RunPaused(
                f"paused during {label} — {len(results)} of {total} members "
                f"of this phase are checkpointed"
            )
    return results


#: What the sweep records against a span it never attempted, and against a span
#: the solver certified holds no aircraft. Read by the report and by anyone
#: asking why a span has no objective value.
SKIPPED_STATUS = "Skipped_Below_Infeasible_Span"
PROVEN_INFEASIBLE_STATUS = "Infeasible_Problem_Detected"

#: Wall-clock ceiling for ONE FLATNESS MEMBER, minutes — well below
#: `SOLVE_TIMEOUT_MIN`, because a span perturbation that is going to converge on
#: this model converges quickly. Every converged flatness member on record, both
#: runs and both chord caps, took **4.6 to 6.0 minutes** (6 of them); the ones
#: that fail run to whatever ceiling they are given, 87-88 iterations without
#: closing. 20 minutes is over 3x the slowest flatness convergence.
#:
#: And more clock is measured, three separate times, to buy nothing on a member
#: that is not converging: pusher at 25 vs 60 minutes reached the same `inf_pr`
#: plateau (FINDINGS §14.5.7), and a feasibility-only solve at span 1.8 m reached
#: no verdict at either 5 or 20 minutes (2026-07-31, 42 then 157 iterations).
#:
#: SCOPED TO FLATNESS DELIBERATELY, and the scope is load-bearing. An earlier
#: version of this comment claimed no solve on this model lands between 5.3 and
#: 30 minutes. **That was false when written** — it came from a survey that
#: listed multistart, flatness, the battery, the prop candidates and the champion
#: and simply missed the tail-type studies, which are the slowest converging
#: solves here: `conventional` took 10.6 min at the 245 mm cap and **21.5 min**
#: at 275 mm. So this model CAN converge well past 12 minutes, and the reason
#: that does not sink this cap is that a tail-topology swap is a different
#: problem from a span perturbation — not that slow convergence never happens.
#:
#: The exposure that remains: a genuinely slow flatness member would be recorded
#: as `Maximum_WallTime_Exceeded` and its span silently lost.
#:
#: **20.0, not 12.0 — user decision, 2026-07-31.** 12 was 2x the slowest flatness
#: convergence ever seen (6.0 min), which sounds like margin until you notice
#: that the one solve known to converge past it took 21.5 minutes. The exposure
#: is asymmetric: a wrongly-timed-out member silently drops a span from the curve
#: the sweep exists to draw, while the cost of being generous is bounded and
#: visible — roughly 16 min per run at the two members that currently fail. The
#: evidence for "slow members do not converge" stays exactly as strong as it was;
#: this buys the margin to find out where it stops being true.
FLATNESS_TIMEOUT_MIN = 20.0


#: How far BELOW the incumbent span the sweep reaches, as a fraction of it.
#: The sweep answers "how flat is this optimum?", which is a question about the
#: optimum's NEIGHBOURHOOD — see `flatness_sweep`.
FLATNESS_SPAN_FRACTION = 0.85


def flatness_sweep(
    batch, span_cap: float, n: int = 6, span_min: float | None = None,
    member_timeout_min: float = FLATNESS_TIMEOUT_MIN,
    run_timeout_min: float = SOLVE_TIMEOUT_MIN,
    incumbent_span: float | None = None,
    span_floor: float | None = None,
) -> list[dict]:
    """Re-optimize everything else at each of `n` fixed spans around the optimum.

    **The range is tied to the incumbent span, not to a constant** (2026-07-31,
    HANDOFF issue 0f). It used to be `linspace(1.5, cap, 6)`, which dates from a
    2.2 m cap with an interior optimum. Once the optimum sat ON the cap, four of
    the six spans were 10-25% below it in a region that had been shown to hold no
    aircraft — so the sweep spent most of a run's time re-deriving that the
    bottom of its own range was empty, and the question it exists to answer is
    about the neighbourhood of the optimum, which 1.5 m is not in for a 2.0 m
    design. It now samples `[FLATNESS_SPAN_FRACTION x s*, cap]`, where `s*` is
    the incumbent's span, which is the same range whether the optimum is on the
    cap or interior.

    What that costs, stated plainly: **the flatness figure is no longer
    comparable across runs with different champions**, because it is no longer
    the same set of spans. That is why this was deferred twice. It is worth it
    because the alternative is a sweep whose samples are chosen by a constant
    from a retired cap.

    `span_min` overrides the derived floor (tests, and a deliberate wide sweep);
    `span_floor` is the span variable's own declared lower bound, which the
    derived range is never allowed to go under.

    Swept DOWNWARD from the cap, short-circuited when a span is PROVED to hold
    no aircraft, and bounded so that a span which proves nothing cannot cost the
    run an hour. Each part carries its own weight:

    **Downward**, because feasibility in span is an interval [s_min, cap] on this
    class of model — shrinking span at a fixed wing area drives CL up and makes
    the stall, gust and stability constraints harder, never easier. So an
    infeasible member licenses an inference about SMALLER spans only, and
    sweeping up from the bottom licenses nothing at all: 1.5 m being infeasible
    says nothing about 1.6 m.

    **Only on a PROOF**, because `Infeasible_Problem_Detected` is the solver
    certifying that there is no aircraft there, whereas a timeout certifies
    nothing — cascading a timeout would silently discard spans that are merely
    slow, which is the same mistake in the other direction.

    **And bounded**, because on THIS model that proof has never arrived. Gating
    the cascade on the status alone (as of 2026-07-30) did nothing whatsoever:
    every failure ever recorded, in every run, is `Maximum_WallTime_Exceeded`,
    so the 2026-07-31 sweep spent 130.6 minutes on four spans and skipped none.
    The single observation the gate was designed against (FINDINGS §14.5.8) came
    from a diagnostic with the static-margin floor relaxed to 0.05, which is not
    the configuration the sweep runs in.

    Trying to MAKE the proof arrive was the obvious next move and it failed on
    measurement: a feasibility-only solve (constant objective, same constraints)
    reached no verdict at span 1.8 m in either 5 or 20 minutes, and at 20 minutes
    sat FURTHER from lift equilibrium (0.356) than the full member did at 30
    (0.030). Removing the objective does not regularise this problem, it flattens
    it. So the cascade stays — it is correct, and it costs six lines — but what
    actually reclaims the time is refusing to pay the full 30-minute run ceiling
    for an answer a shorter member budget gives just as well.
    See `FLATNESS_TIMEOUT_MIN`.

    `run_timeout_min` is the run-wide ceiling (`--solve-timeout-min`), and it is
    a true CEILING: lowering it lowers the member budget with it, because that
    flag is documented as the limit for one member solve and a phase that
    silently ignored it would be lying. Raising it is the asymmetric case — that
    does not undo a budget set from evidence about this phase specifically.

    `batch(label, jobs)` runs a list of `(key, kwargs)` member solves; injected
    rather than imported so the sweep is testable without a solver.
    """
    member_timeout_min = min(member_timeout_min, run_timeout_min)
    if span_min is None:
        # Below the incumbent, never above the cap: the cap is a declared
        # manufacturing limit and a member past it is not an aircraft anyone
        # agreed to build.
        span_min = FLATNESS_SPAN_FRACTION * min(incumbent_span or span_cap, span_cap)
        if span_floor is not None:
            # never below the variable's own declared floor: a `fixed` value
            # outside the box is an INVALID problem, not an infeasible one, and
            # the member would come back as a solver error rather than a span
            span_min = max(span_min, float(span_floor))
    spans = sorted((float(s) for s in np.linspace(span_min, span_cap, n)), reverse=True)
    fr: dict[float, dict] = {}
    floor: float | None = None
    for span in spans:
        if floor is not None:
            fr[span] = {
                "failed": f"skipped: {floor:.2f} m proved infeasible and span "
                "feasibility is an interval up to the cap",
                "return_status": SKIPPED_STATUS,
            }
            log.info("  flatness sweep: %.2f m skipped (below the infeasible %.2f m)",
                     span, floor)
            continue
        fr[span] = batch("flatness sweep", [
            (span, {"fixed": {"span": span}, "timeout_min": member_timeout_min})
        ])[span]
        if fr[span].get("return_status") == PROVEN_INFEASIBLE_STATUS:
            floor = span
            log.info("  flatness sweep: %.2f m proved infeasible — smaller spans "
                     "will be skipped", span)

    return [
        {"span": s, "objective_value": None, **_failed_entry(fr[s])}
        if "failed" in fr[s]
        else {
            "span": s,
            "objective_value": fr[s]["objective_value"],
            "solve_minutes": fr[s].get("solve_minutes"),
        }
        for s in sorted(spans)
    ]


def optimize(
    aircraft,
    mission,
    runs_root: Path = Path("runs"),
    input_files: list[Path] | None = None,
    multistart: int = 3,
    flatness: bool = True,
    parallel: int = 1,
    memory_budget_gb: float | None = None,
    warm_start: dict | None = None,
    warm_start_from: str | None = None,
    solve_timeout_min: float = SOLVE_TIMEOUT_MIN,
    max_iter: int = SOLVE_MAX_ITER,
    checkpoint_dir: Path | None = None,
    pause_file: Path | None = None,
    live_dir: Path | None = None,
) -> tuple[RunResult, Path]:
    """M2 entry point: multi-start NLP -> champion -> shadow price -> flatness
    sweep -> numeric re-evaluation of the champion through the M1 pipeline.

    parallel: how many NLP solves may run concurrently within each independent
    batch (multistart+bump, flatness, re-solve battery, discrete-study
    alternatives, winglet pair). 1 = sequential (default; required under the
    15 GB WSL cap). Cross-batch order is unchanged, so study semantics are
    identical at any width.

    memory_budget_gb: how much RAM the user is willing to dedicate. It does not
    make a solve faster — a solve is single-core and memory-bound — it decides
    how many fit side by side, so it is just a friendlier way to say `parallel`
    (memory.py). Divided by the per-solve peak this aircraft has actually been
    measured at, so the arithmetic gets better the more you run. An explicit
    `parallel` wins, since it is the more specific instruction.

    solve_timeout_min: wall-clock ceiling for any ONE member solve. A battery is
    a fixed set of independent solves and a diverging one has no natural end, so
    without a cap a single bad member can own the whole run (SOLVE_TIMEOUT_MIN).
    Members that hit it are recorded as `Maximum_WallTime_Exceeded` and the
    battery carries on.

    checkpoint_dir / pause_file: stop a multi-hour battery and get the machine
    back, without losing what it has already done. Creating `pause_file` makes
    the run finish the member in flight, then exit with `RunPaused`; every member
    completed so far is in `checkpoint_dir`, and re-running the same command with
    the same checkpoint directory continues from there.

    **The pause is at MEMBER boundaries, and that is not a shortcut — it is the
    only point where memory can actually be released.** A solve in progress is
    ~14.5 GB of CasADi graph plus IPOPT's barrier state, filter and MUMPS
    factorization; none of that is serialisable through CasADi, so freeing the
    memory necessarily destroys it. The most that could be salvaged mid-solve is
    the current iterate as a warm start, and this project has already measured
    warm starts as a wash on this model (HANDOFF: the champion sits on many
    active bounds, so IPOPT pushes off them at startup regardless). Waiting for
    the member boundary therefore costs at most `solve_timeout_min` and loses
    nothing, where a mid-solve pause would free the same memory and throw the
    solve away.

    live_dir: where the live viewer's frames go (M5.4, `liveframe`). It is a
    directory under `runs/_live/` while the run is going, because the run
    directory does not exist until the run ENDS; the frames are moved into
    `<run_dir>/frames/` here, at the end. On a PAUSE they stay where they are so
    a resume appends to them — the same lifecycle the checkpoint directory has.
    """
    if memory_budget_gb is not None and parallel <= 1:
        per = memory.observed_peak_gb(runs_root)
        parallel, why = memory.plan_parallel(memory_budget_gb, per_solve_gb=per)
        log.info(
            "memory budget %.0f GB: %s%s",
            memory_budget_gb, why,
            "" if per else f" (no measured peak yet — assuming {memory.DEFAULT_PER_SOLVE_GB:.0f} GB)",
        )
    check_parallel(parallel)
    RUN_PEAK.reset()  # per-solve marks are reset as the run goes; this keeps the max
    t_start = time.monotonic()
    total_gb, avail_gb = memory.machine_ram()
    log.info(
        "optimize: %s / %s — objective %s. Each NLP solve takes minutes and peaks "
        "near %.0f GB; a full battery runs for hours. RAM: %.1f GB free of %.1f GB.",
        getattr(aircraft, "name", type(aircraft).__name__), mission.name, mission.objective,
        memory.observed_peak_gb(runs_root) or memory.DEFAULT_PER_SOLVE_GB, avail_gb, total_gb,
    )
    if warm_start:
        log.info("warm start: seeding the nominal solve and every study candidate "
                 "from %s (all variables stay free — this is an initial guess, "
                 "not a constraint). NOTE: measured as no faster than a cold "
                 "solve even when seeded with the answer itself (5.58 vs 5.35 "
                 "min, 2026-07-31) — use it for provenance, not for speed.",
                 warm_start_from or "a previous champion")
    # `warm_start=True` alongside the seed: without it IPOPT pushes the starting
    # point off every bound before iterating, which on a champion pinned against
    # eight of them throws away most of what the seed was worth
    # (WARM_START_OPTIONS).
    warm = {"inits": dict(warm_start), "warm_start": True} if warm_start else {}

    # Where the hours actually went. Reconstructing this from the progress log
    # after the fact is what turned up the 2026-07-29 finding that 87% of a
    # 405-minute run was spent on phases that failed or barely informed; it
    # belongs in the artifact, next to what each phase concluded.
    phase_minutes: dict[str, float] = {}
    #: Members attempted per phase, so a resumed phase can report "6 of 6 from
    #: checkpoint" rather than an unexplained 0.0 minutes (see _SolveCache.resumed).
    phase_members: dict[str, int] = {}

    cache = None
    if checkpoint_dir is not None:
        cache = _SolveCache(checkpoint_dir, fingerprint.model_fingerprint(aircraft, mission))
        log.info("checkpointing members to %s%s", cache.dir,
                 f"; create {pause_file} to pause at the next member boundary"
                 if pause_file is not None else "")

    live = None
    if live_dir is not None:
        from . import liveframe

        live = liveframe.FrameWriter(live_dir, aircraft)
        log.info("live frames to %s (open the viewer from the GUI, or replay them "
                 "later with `planeopt timelapse`)", live.dir)

    def batch(label, jobs, **kw):
        t_phase = time.monotonic()
        phase_members[label] = phase_members.get(label, 0) + len(jobs)
        try:
            return _solve_many(
                aircraft, mission, jobs, parallel, label=label,
                timeout_min=solve_timeout_min, max_iter=max_iter, cache=cache,
                pause_file=pause_file, live=live, **kw
            )
        finally:
            phase_minutes[label] = round(
                phase_minutes.get(label, 0.0) + (time.monotonic() - t_phase) / 60.0, 1
            )

    rng = np.random.default_rng(0)
    # The nominal start is warmed; the PERTURBED starts are deliberately left
    # cold, so multistart still answers "does this converge from elsewhere?".
    # A warm start that also seeded them would agree with itself by construction.
    jobs = [("nominal", dict(warm))]
    for i in range(multistart - 1):
        inits = {
            "span": float(1.8 * rng.uniform(0.88, 1.12)),
            "c_root": float(0.22 * rng.uniform(0.88, 1.12)),
            "taper": float(np.clip(0.68 * rng.uniform(0.85, 1.15), 0.45, 0.95)),
            "V": float(11 * rng.uniform(0.85, 1.2)),
        }
        if getattr(aircraft, "winglet", False):
            inits["wl_len"] = float(0.12 * rng.uniform(0.5, 1.8))
            inits["wl_cant"] = float(rng.uniform(60.0, 85.0))
        jobs.append((f"perturbed_{i}", {"inits": inits}))
    # the +20 g shadow-price bump is independent of the champion, so it rides
    # the same batch; its delta is computed afterwards
    jobs.append(("mass_bump", {"extra_mass_kg": 0.020}))
    first = batch("multistart", jobs)
    starts, results = [], []
    for key, _ in jobs:
        if key == "mass_bump":
            continue
        r = first[key]
        results.append(r)
        starts.append(key if "failed" not in r else f"{key} (failed)")

    ok = [r for r in results if "failed" not in r]
    if not ok:
        raise no_survivors_error(starts, results)
    sign = 1 if OBJECTIVES[mission.objective].direction == "maximize" else -1
    champion = max(ok, key=lambda r: sign * r["objective_value"])
    spread = max(abs(r["objective_value"] - champion["objective_value"]) for r in ok)

    # Shadow price for the SCREEN only: minutes (objective units) per gram of
    # structure, measured against the multistart champion. `screen_discrete`
    # needs it before the studies run, so it cannot wait for the final design;
    # the number reported in the artifact is re-measured on that design below.
    bumped = first["mass_bump"]
    screen_shadow_per_g = (
        (bumped["objective_value"] - champion["objective_value"]) / 20.0
        if "failed" not in bumped
        else None
    )

    # discrete studies (MODEL_DETAILS 6.3): the aircraft declares
    # `discrete_options = {attr: [candidate values]}` — e.g. fuselage topology
    # (section 7.4) or tail type (section 8) — every candidate a suggestion the
    # study prices, never an assumption. Plain enumeration, one full
    # re-optimization per alternative, in declared order (greedy: each study
    # runs with the previous studies' adopted values). A winner becomes the
    # champion and stays active through the winglet study and numeric
    # re-evaluation (originals restored in the re-eval finally).
    discrete_studies = {}
    discrete_originals = {}
    #: Notes raised BEFORE the champion is re-evaluated, so before `result`
    #: exists to carry them. Merged into `result.notes` once it does — a guard
    #: that fires during selection must not be lost just because it fired early.
    early_notes: list[str] = []
    for attr, candidates in (getattr(aircraft, "discrete_options", None) or {}).items():
        baseline = getattr(aircraft, attr)
        discrete_originals[attr] = baseline
        study = {"baseline": baseline, "alternatives": {}, "adopted": baseline}
        cands = [c for c in candidates if c != baseline]
        # M5.3: shortlist a large candidate set with a no-NLP screen before
        # spending ~5 minutes of solve on each (screen_discrete). Opt-in per
        # attribute, and the full ranking is kept in the artifact so the
        # shortlist can be second-guessed without re-running anything.
        top_n = (getattr(aircraft, "discrete_screen", None) or {}).get(attr)
        if top_n and len(cands) > top_n:
            screen = screen_discrete(
                aircraft, mission, attr, cands, champion, top_n, screen_shadow_per_g,
            )
            study["screen"] = screen
            log.info(
                "study %s: screened %d candidates without solving — shortlist %s",
                attr, len(cands), ", ".join(screen["shortlist"]),
            )
            cands = screen["shortlist"]
        if not cands:
            # A single-candidate option is a DECLARED choice, not a study: the
            # aircraft is saying "this is the mount", the way `span_cap_m` says
            # "this is the cap". Recorded so the artifact still names what was
            # used, but not run as a phase — an empty phase in the progress log
            # and an empty block in the report both read as a study that failed.
            discrete_studies[attr] = study
            continue
        # alternatives within one attr are independent solves (each candidate's
        # solve depends only on its own attr value, not on the champion), so
        # they may run concurrently; adoption below is order-identical to the
        # sequential greedy (winner = argmax over baseline + candidates)
        res = batch(
            f"study {attr}", [(c, dict(warm)) for c in cands],
            prep=lambda c, a=attr: setattr(aircraft, a, c),
            restore=lambda a=attr, b=baseline: setattr(aircraft, a, b),
        )
        for cand in cands:
            r_c = res[cand]
            if "failed" in r_c:
                study["alternatives"][cand] = _failed_entry(r_c)
                continue
            delta = r_c["objective_value"] - champion["objective_value"]
            study["alternatives"][cand] = {
                **{k: r_c[k] for k in ("objective_value", "V_ms", "auw_kg")},
                "delta_objective": delta,
            }
            if sign * delta > 0:
                # A candidate only wins by comparing its objective against the
                # incumbent's, and that comparison is meaningless if its drag is
                # the mesh's rather than the aeroplane's. Checked HERE, at the
                # moment of adoption, because afterwards every downstream phase
                # is characterizing whatever this chose (FINDINGS §18).
                previous = getattr(aircraft, attr)
                setattr(aircraft, attr, cand)
                ok, check = objective_is_mesh_trustworthy(aircraft, r_c)
                if ok:
                    champion = r_c
                    study["adopted"] = cand
                else:
                    setattr(aircraft, attr, previous)
                    study["alternatives"][cand]["rejected_by_mesh_guard"] = check
                    log.warning(
                        "%s=%s won by %+.3f but its drag is MESH-DEPENDENT "
                        "(%.5f N in-loop vs %.5f N fine) — not adopted",
                        attr, cand, delta, check["in_loop"]["D_n"],
                        check["fine"]["D_n"],
                    )
                    early_notes.append(
                        f"DISCRETE CANDIDATE REJECTED BY THE MESH GUARD: "
                        f"{attr}={cand} beat the incumbent by {delta:+.3f} but its "
                        f"drag moves {100 * check['delta_frac']:+.1f}% between the "
                        f"in-loop mesh and {aero.LL_CHECK_RESOLUTION} panels/section. "
                        "It won on a number that is the discretization's, so it was "
                        "not adopted — the incumbent stands."
                    )
        discrete_studies[attr] = study

    # winglet study (MODEL_DETAILS 3.6): paired on/off re-optimization at the
    # same span cap, an inviscid VLM second opinion on the induced-drag delta,
    # and the continuous-cant cross-check (outermost panel freed to ~88 deg, no
    # explicit winglet — does one emerge from the planform architecture alone?)
    winglet_study = None
    winglet_rejected = False
    if getattr(aircraft, "winglet", False):
        winglet_study = {}
        r_on = champion  # the winglet-bearing solve, kept for the VLM check
        prev_cant = getattr(aircraft, "tip_dihedral_max_deg", 20.0)

        def _wl_prep(key):
            aircraft.winglet = False
            if key == "continuous_cant":
                aircraft.tip_dihedral_max_deg = 88.0

        def _wl_restore():
            aircraft.winglet = True
            aircraft.tip_dihedral_max_deg = prev_cant

        wr = batch(
            "winglet study", [("off", {}), ("continuous_cant", {})],
            prep=_wl_prep, restore=_wl_restore,
        )

        r_off = wr["off"]
        if "failed" in r_off:
            winglet_study["off"] = _failed_entry(r_off)
        else:
            winglet_study["off"] = {
                **{k: r_off[k] for k in ("objective_value", "V_ms", "auw_kg")},
                "span": r_off["dv"]["span"],
            }
            winglet_study["delta_objective"] = (
                champion["objective_value"] - r_off["objective_value"]
            )
            # rejection rule (EXECUTION_PLAN M4.5 gate): winglet=True only means
            # "consider one" — wl_len's lower bound forces it into the on-solve,
            # so if the off-solve wins, IT is the champion and the numeric
            # re-evaluation below runs winglet-free
            if sign * winglet_study["delta_objective"] < 0:
                winglet_rejected = True
                champion = r_off
            winglet_study["winglet_rejected"] = winglet_rejected

        champ_plane_on = aircraft.geometry(r_on["dv"])
        aircraft.winglet = False
        try:
            champ_plane_off = aircraft.geometry(r_on["dv"])
        finally:
            aircraft.winglet = True
        try:
            winglet_study["vlm_check"] = aero.vlm_induced_check(
                {"winglet_on": champ_plane_on, "winglet_off": champ_plane_off},
                r_on["V_ms"],
            )
        except Exception as e:  # numeric cross-check must never kill the run
            winglet_study["vlm_check"] = {"failed": str(e)[:120]}

        r_cant = wr["continuous_cant"]
        if "failed" in r_cant:
            winglet_study["continuous_cant"] = _failed_entry(r_cant)
        else:
            winglet_study["continuous_cant"] = {
                "objective_value": r_cant["objective_value"],
                "tip_dihedral_deg": r_cant["dv"].get("dihedral_tip"),
                "d_exp": r_cant["dv"].get("d_exp"),
                "span": r_cant["dv"]["span"],
                "caveat": "Schrenk stall stations include the canted region — "
                "indicative only; the spar-fit constraint also binds high cant",
            }

    # priced options (MODEL_DETAILS 6.3): candidates that are MEASURED and never
    # adopted. `discrete_options` above adopts whatever wins, which is right when
    # the objective can see everything at stake — a tail type, a propeller. It is
    # wrong when the alternative gives up something the model has no term for.
    #
    # Dropping the companion computer, the airspeed sensor and the telemetry
    # radio makes an aeroplane that is strictly lighter and therefore strictly
    # better by this objective, and it is not the aeroplane the user is building.
    # A study that adopted it would delete capability and report the deletion as
    # an improvement. So the run prices it and stops there — the same posture
    # `span_cap_m` takes toward the print bed: the model measures, the user
    # decides.
    #
    # Runs here, after the adopting studies, so the price is quoted against the
    # design actually being shipped rather than the multistart champion.
    priced = {}
    for attr, candidates in (getattr(aircraft, "priced_options", None) or {}).items():
        baseline = getattr(aircraft, attr)
        cands = [c for c in candidates if c != baseline]
        if not cands:
            continue
        res = batch(
            f"priced {attr}", [(c, dict(warm)) for c in cands],
            prep=lambda c, a=attr: setattr(aircraft, a, c),
            restore=lambda a=attr, b=baseline: setattr(aircraft, a, b),
        )
        entries = {}
        for cand in cands:
            r_c = res[cand]
            if "failed" in r_c:
                entries[cand] = _failed_entry(r_c)
                continue
            entries[cand] = {
                **{k: r_c[k] for k in ("objective_value", "V_ms", "auw_kg")},
                "delta_objective": r_c["objective_value"] - champion["objective_value"],
            }
        priced[attr] = {
            "baseline": baseline,
            "alternatives": entries,
            "adopted": baseline,
            "note": "PRICED, NOT ADOPTED — the alternative gives up something "
                    "this model has no term for, so the number is a price and "
                    "not a recommendation",
        }

    # --- characterization of the FINAL design ------------------------------
    # Everything from here down describes the aeroplane this run is actually
    # shipping, which is why it runs here and not earlier.
    #
    # It used to run right after the multistart, BEFORE the discrete studies and
    # the winglet study — so on 2026-08-05 the flatness curve and the whole
    # re-solve battery described a 119.93-minute aircraft carrying the incumbent
    # 11x6 prop and a winglet, while the champion being reported was a
    # 142.09-minute aircraft with a 12x10 and no winglet. Every member converged
    # and nothing said the two were different aeroplanes. A sensitivity that is
    # not a sensitivity OF THE DESIGN is worse than no sensitivity, because it
    # reads exactly like one (the same failure shape as the 2026-08-01 winglet
    # cross-check measuring its own mesh).
    #
    # The champion's discrete attributes are already set on `aircraft` by the
    # studies above; the winglet is not, so it is applied here. Both are
    # restored in the re-evaluation's `finally` below.
    if winglet_rejected:
        aircraft.winglet = False

    # --- the gate: is this design worth characterizing at all? ---------------
    # Everything below re-optimizes the design several times over — the flatness
    # sweep plus four sensitivity members — and it is the most expensive thing
    # in the run after the multistart. All of it describes the objective this
    # design reports, so if that objective is the discretization's rather than
    # the aeroplane's, the entire phase is spent characterizing an artefact.
    #
    # Under a second to ask, hours to get wrong. It is deliberately the DRAG
    # half of the mesh check and not the full one: this is a go/no-go on
    # trustworthiness, while the reporting cross-checks (static margin, lateral
    # derivatives) run later against the re-evaluated champion and are the
    # numbers the artifact actually quotes.
    design_trustworthy, gate_check = objective_is_mesh_trustworthy(aircraft, champion)
    if gate_check is not None:
        gate_diagnostics = {"objective_mesh_check": gate_check,
                            "design_trustworthy": design_trustworthy}
    else:
        gate_diagnostics = {"design_trustworthy": True, "objective_mesh_check": None}
    if not design_trustworthy:
        log.warning(
            "CHAMPION OBJECTIVE IS MESH-DEPENDENT (%.5f N in-loop vs %.5f N at %d "
            "panels/section) — skipping the sensitivity phases, which would only "
            "characterize the artefact",
            gate_check["in_loop"]["D_n"], gate_check["fine"]["D_n"],
            aero.LL_CHECK_RESOLUTION,
        )
        early_notes.append(
            "SENSITIVITY PHASES SKIPPED. The champion's drag moves "
            f"{100 * gate_check['delta_frac']:+.1f}% between the in-loop mesh and "
            f"{aero.LL_CHECK_RESOLUTION} panels/section, so its objective is not "
            "trustworthy (FINDINGS §18) and a sensitivity OF that objective would "
            "not be a sensitivity of the aeroplane. The flatness sweep and the "
            "perturbation battery did not run; the mass bump did, so a shadow "
            "price is still quoted. Fix the model before reading any of this."
        )

    # flatness: re-optimize everything else at fixed spans (up to the cap)
    flat = []
    span_cap = getattr(aircraft, "span_cap_m", 3.0)
    if flatness and design_trustworthy:
        # The declared span floor is a hard limit on what the sweep may sample:
        # a `fixed` value outside a variable's own box is not an infeasible
        # aircraft, it is an invalid problem, and IPOPT says so
        # (`Invalid_Problem_Definition`) rather than reporting a span.
        span_box = (champion.get("dv_bounds") or {}).get("span") or [None, None]
        flat = flatness_sweep(
            batch, span_cap, run_timeout_min=solve_timeout_min,
            incumbent_span=champion["dv"].get("span"),
            span_floor=span_box[0],
        )

    # re-solve battery (MODEL_DETAILS 6.4 item 2): each is a full re-optimization.
    # The +20 g bump rides along so the REPORTED shadow price is the final
    # design's too, rather than the multistart champion's (it costs one solve,
    # and a shadow price quoted against a superseded prop is not this design's
    # trade rate).
    #: `mass_bump` is NOT a sensitivity member — it is what the shadow price is
    #: computed from, and the rest of the run quotes that price. So when the
    #: gate skips characterization it drops the four perturbations and keeps
    #: this one: a run that cannot say how sensitive the design is can still say
    #: what a gram costs it, and `shadow_per_g` below has no other source.
    battery_jobs = [
        ("printed_mass_x1.10", {"printed_scale": 1.10}),
        ("printed_mass_x0.90", {"printed_scale": 0.90}),
        ("chain_eta_x0.90", {"eta_scale": 0.90}),
        ("chain_eta_x1.10", {"eta_scale": 1.10}),
        ("mass_bump", {"extra_mass_kg": 0.020}),
    ]
    if not design_trustworthy:
        battery_jobs = [j for j in battery_jobs if j[0] == "mass_bump"]
    battery = {}
    battery_results = batch("re-solve battery", battery_jobs)
    for label, r in battery_results.items():
        if label == "mass_bump":
            continue
        if "failed" in r:
            battery[label] = _failed_entry(r)
        else:
            battery[label] = {
                "objective_value": r["objective_value"],
                "delta": r["objective_value"] - champion["objective_value"],
                "span": r["dv"]["span"],
                "static_margin": r["static_margin"],
                "ballast_kg": r["dv"]["ballast_kg"],
            }
    final_bump = battery_results["mass_bump"]
    shadow_per_g = (
        (final_bump["objective_value"] - champion["objective_value"]) / 20.0
        if "failed" not in final_bump
        else screen_shadow_per_g
    )

    # What the champion is PINNED against, in the progress log as well as the
    # artifact: this is the "what to relax next" list, and the run it was added
    # for had eight entries where the session discussed three (issue 0b).
    if champion.get("active_bounds"):
        log.info(
            "champion sits on %d bound(s): %s",
            len(champion["active_bounds"]),
            ", ".join(f"{b['variable']}={b['value']:.4g} ({b['at']})"
                      for b in champion["active_bounds"]),
        )

    # numeric re-evaluation of the champion through the full M1 pipeline
    # (winglet-free when the study rejected it — `aircraft.winglet` was already
    # set to the champion's value above, so the characterization phases and this
    # re-evaluation see the same aeroplane)
    log.info("re-evaluating the champion numerically and writing artifacts")
    # A champion is only half described by its design vector; the studies also
    # picked tail type, topology, mount, prop and winglet, and those are plain
    # attributes. Record them, so rebuilding the champion later cannot silently
    # fall back to the aircraft file's defaults (report/assemble.as_champion).
    champion["discrete"] = {
        attr: getattr(aircraft, attr)
        for attr in (getattr(aircraft, "discrete_options", None) or {})
        if hasattr(aircraft, attr)
    }
    if hasattr(aircraft, "winglet"):
        champion["discrete"]["winglet"] = bool(aircraft.winglet)
    reeval_error = None
    try:
        result, run_dir = run(
            aircraft, mission, runs_root, input_files, dv=champion["dv"],
            trim_guess=(champion["alpha_deg"], champion["deflection_deg"]),
        )
        # tripped-polar dual evaluation at the champion point (MODEL_DETAILS 3.2)
        best = result.performance["best"]
        champ_plane = aircraft.geometry(champion["dv"])
    except Exception as e:  # noqa: BLE001
        # The re-evaluation is a *reporting* step: it re-runs the champion through
        # the numeric M1 pipeline for cross-checking. Losing it costs the check,
        # not the optimization — and an optimization is hours of solving. Write
        # everything the NLP found, flagged, instead of discarding the run.
        reeval_error = f"{type(e).__name__}: {e}"
        log.warning("champion re-evaluation failed; writing NLP results without it — %s",
                    reeval_error)
        best = champ_plane = None
        result = RunResult(
            aircraft=getattr(aircraft, "name", type(aircraft).__name__),
            mission=mission.name,
            objective=mission.objective,
            status=M2_STATUS,
            created=datetime.datetime.now().isoformat(timespec="seconds"),
            performance={"objective_units": OBJECTIVES[mission.objective].units},
            # Especially here. This is the path where the re-evaluation FAILED,
            # so the design vector is the only handle anyone has on what the
            # optimizer actually found — without it the run is hours of solving
            # that cannot be reproduced or investigated.
            design_vector=dict(champion.get("dv") or {}),
        )
        run_dir = assemble.write_run_dir(result, runs_root, input_files or [])
    finally:
        if winglet_rejected:
            aircraft.winglet = True
        for attr, val in discrete_originals.items():
            setattr(aircraft, attr, val)
    result.status = M2_STATUS
    # Guards that fired during SELECTION, before `result` existed to hold them.
    # Merged first so they read above the re-evaluation's own findings, which is
    # the order they happened in.
    result.notes[:0] = early_notes
    result.diagnostics |= gate_diagnostics
    if not design_trustworthy:
        result.diagnostics["characterization_skipped"] = [
            "flatness sweep", "re-solve battery (mass_bump retained)",
        ]
    if best is not None:
        # The two SM numbers side by side. They now come from the same estimator
        # (aero.SM_ALPHA_OFFSETS), so what is left is the difference between the
        # NLP's cruise alpha and the re-evaluation's trimmed one — real, since
        # SM varies with alpha on this model, and worth seeing rather than
        # rediscovering as a mystery 0.002.
        result.constraints["static_margin_nlp"] = champion["static_margin"]
        result.constraints["static_margin_gap"] = (
            result.constraints["static_margin"] - champion["static_margin"]
        )
    if warm_start:
        # provenance: a champion seeded from another run must say so, because the
        # local optimum it found may depend on where it started
        result.diagnostics["warm_started_from"] = warm_start_from or "(unnamed)"
    if reeval_error is not None:
        result.diagnostics["champion_reeval_failed"] = reeval_error
        result.notes.append(
            "Champion re-evaluation through the numeric M1 pipeline FAILED — the "
            "design vector and study results below are the optimizer's, "
            "un-cross-checked. Treat them as provisional."
        )

    # Is the champion's drag a property of the aircraft or of the panel count?
    # Two lifting-line runs at one operating point against a battery measured in
    # hours — and the failure it guards produced a 222-minute aeroplane with an
    # L/D of 889 on 2026-08-01 (aero.mesh_convergence_check, FINDINGS §18).
    if best is not None:
        mesh = aero.mesh_convergence_check(
            champ_plane, best["V_ms"], best["alpha_deg"], best["deflection_deg"],
            result.masses["x_cg_m"],
            control_name=getattr(aircraft, "pitch_control_name", "ruddervator"),
            c_ref=float(champ_plane.c_ref),
            bodies=aircraft.parasite_bodies(champion["dv"]),
        )
        result.diagnostics["aero_mesh_check"] = mesh
        smm = mesh.get("static_margin") or {}
        if smm.get("sign_flip_is_mesh_artefact"):
            result.notes.append(
                "The static margin's sign change inside its own window DISAPPEARS "
                f"at {aero.LL_CHECK_RESOLUTION} panels/section — it is a "
                "discretization artefact of the in-loop mesh, not a property of "
                "the aeroplane, and the margin should be read off the fine mesh "
                f"({smm['fine']['static_margin']:.4f}) rather than the in-loop one "
                f"({smm['in_loop']['static_margin']:.4f})."
            )
        elif smm.get("sign_flip_survives_refinement"):
            result.notes.append(
                "The static margin's sign change SURVIVES a "
                f"{aero.LL_CHECK_RESOLUTION}-panel mesh "
                f"({smm['in_loop']['static_margin']:.4f} → "
                f"{smm['fine']['static_margin']:.4f}), so refinement does not "
                "explain it. Combined with an inviscid VLM sweep that is monotone "
                "over the same window, the nonlinearity is the VISCOUS Cm at this "
                "Reynolds number — treat it as a property of the aeroplane."
            )
        if smm and not smm.get("converged"):
            log.warning("champion static margin is MESH-DEPENDENT: %.4f vs %.4f",
                        smm["in_loop"]["static_margin"], smm["fine"]["static_margin"])
            result.notes.append(
                f"CHAMPION STATIC MARGIN IS MESH-DEPENDENT: "
                f"{smm['in_loop']['static_margin']:.4f} at the in-loop resolution "
                f"against {smm['fine']['static_margin']:.4f} at "
                f"{aero.LL_CHECK_RESOLUTION} panels/section. The stability window "
                "is 0.07 wide and this moves the answer inside it."
            )
        if not mesh["converged"]:
            log.warning(
                "champion drag is MESH-DEPENDENT: %.5f N in the loop vs %.5f N at "
                "%d panels/section — the objective is not trustworthy",
                mesh["in_loop"]["D_n"], mesh["fine"]["D_n"], aero.LL_CHECK_RESOLUTION,
            )
            result.notes.append(
                f"CHAMPION DRAG IS MESH-DEPENDENT: {mesh['in_loop']['D_n']:.5f} N at "
                f"the in-loop resolution against {mesh['fine']['D_n']:.5f} N at "
                f"{aero.LL_CHECK_RESOLUTION} panels/section "
                f"({100 * mesh['delta_frac']:+.1f}%). The optimizer may have found a "
                "discretization artefact rather than an aircraft — do not report "
                "this objective until it is understood (FINDINGS §18)."
            )

    # Does the aeroplane actually weathercock? The in-loop directional
    # constraint is a DECLARED vertical-tail-volume floor standing in for a yaw
    # axis (MODEL_DETAILS 8.4) — it constrains a proxy for Cn_beta and never
    # Cn_beta itself, so nothing in the run has ever checked the thing the floor
    # exists to guarantee. This is that check, and it is cheap: a sideslip sweep
    # carries no polar, so the whole 3-mesh ensemble costs ~2 s against a
    # battery measured in hours.
    if best is not None:
        try:
            direc = aero.vlm_directional_check(
                {"champion": champ_plane}, best["V_ms"], best["alpha_deg"],
                result.masses["x_cg_m"],
            )["champion"]
            result.diagnostics["directional_check"] = direc
            if not direc["reliable"]:
                log.warning("directional check is UNRELIABLE: %s",
                            direc["unreliable_reason"])
                result.notes.append(
                    "The directional cross-check could not agree with itself "
                    f"({direc['unreliable_reason']}). Cn_beta is reported but "
                    "must not be relied on."
                )
            elif not direc["directionally_stable"]:
                log.warning(
                    "champion is DIRECTIONALLY UNSTABLE: Cn_beta = %+.6f/deg",
                    direc["cn_beta"],
                )
                result.notes.append(
                    f"CHAMPION IS DIRECTIONALLY UNSTABLE: Cn_beta = "
                    f"{direc['cn_beta']:+.6f}/deg. The declared vertical-tail-volume "
                    "floor was met and the aeroplane still does not weathercock — "
                    "the floor is the wrong constraint for this geometry, not "
                    "merely a loose one."
                )
            if direc["reliable"] and not direc["roll_stable"]:
                result.notes.append(
                    f"Cl_beta = {direc['cl_beta']:+.6f}/deg is POSITIVE — the "
                    "champion has no dihedral effect. The effective-dihedral floor "
                    "is a roll-moment proxy and this is the direct measurement."
                )
        except Exception as e:  # noqa: BLE001 — a diagnostic must never cost the run
            log.warning("directional check failed: %s: %s", type(e).__name__, e)

    # Is the static margin the AIRFRAME's, or LiftingLine's? Until 2026-08-06
    # nothing in this app looked at Cm twice, while drag had two cross-checks —
    # backwards, because Cm is the quantity the project already knows is its
    # weakest and the only one that decides whether the aeroplane is flyable.
    # The VLM shares the library but not the solution scheme, and the SHAPE of
    # Cm(alpha) is comparable across the two even though the levels are not
    # (the VLM is inviscid; LL carries NeuralFoil's viscous Cm).
    if best is not None:
        try:
            smc = aero.vlm_static_margin_check(
                {"champion": champ_plane}, best["V_ms"], best["alpha_deg"],
                result.masses["x_cg_m"], float(champ_plane.c_ref),
                bodies=aircraft.parasite_bodies(champion["dv"]),
            )["champion"]
            result.diagnostics["sm_cross_check"] = smc
            ll_sm = result.constraints.get("static_margin")
            if ll_sm is not None:
                smc["ll_static_margin"] = float(ll_sm)
                smc["delta_vs_ll"] = float(smc["static_margin"] - ll_sm)
            # The case worth shouting about: LL says the margin changes sign
            # inside its own window and the independent method says it does not.
            # That is evidence the nonlinearity is the DISCRETIZATION's, and it
            # is the difference between an aeroplane that fails its stability
            # requirement and one that does not.
            # read from `constraints` rather than a local: the LL verdict is
            # produced in `_champion_diagnostics`, not in this function
            ll_sign_ok = result.constraints.get("sm_sign_consistent")
            if smc["reliable"] and smc["sign_consistent"] and ll_sign_ok is False:
                result.notes.append(
                    f"STATIC-MARGIN SIGN FLIP IS NOT CONFIRMED BY AN INDEPENDENT "
                    f"METHOD: LiftingLine reports a local dCm/dCL going negative "
                    f"inside the window, but the VLM sweep over the same alphas is "
                    f"monotone and returns SM = {smc['static_margin']:.4f} against "
                    f"LL's {ll_sm:.4f}. The two methods differ by viscosity, so this "
                    "does not settle which is right — it localizes the "
                    "nonlinearity to LL's viscous Cm or its discretization, and "
                    "the margin should not be treated as failing on LL's word alone."
                )
        except Exception as e:  # noqa: BLE001 — a diagnostic must never cost the run
            log.warning("static-margin cross-check failed: %s: %s", type(e).__name__, e)

    # What the afterbody term actually charged, at the champion point and
    # computed NUMERICALLY rather than read off the NLP graph. Two of these
    # numbers are the ones the next battery has to be read against: whether
    # theta_max settled near the separation threshold, and whether the boat-tail
    # came off its 1.8 x d_eq floor (MODEL_DETAILS 7.3, HANDOFF).
    if best is not None:
        try:
            champ_bodies = aircraft.parasite_bodies(champion["dv"])
            body = next((b for b in champ_bodies if "afterbody" in b), None)
            if body is not None:
                s_ref = float(champ_plane.s_ref)
                total = aero.body_cd0(champ_bodies, best["V_ms"], s_ref) * s_ref
                ab = {k: float(v) for k, v in body["afterbody"].items()}
                ab["fineness"] = float(body["fineness"])
                # of the WHOLE body drag area (skin friction + excrescence +
                # base), so it reads as a share of what the buildup reports
                ab["share_of_body_drag"] = ab["base_drag_area_m2"] / total if total else None
                result.diagnostics["afterbody"] = ab
        except Exception as e:  # noqa: BLE001 — a diagnostic must never cost the run
            log.warning("afterbody diagnostics failed: %s: %s", type(e).__name__, e)

    tripped = None
    if best is not None:
        trip = aero.tripped_cd_delta(champ_plane, best["V_ms"], best["CL"])
        q = 0.5 * 1.225 * best["V_ms"] ** 2
        drag_tripped = best["drag_n"] + q * champ_plane.s_ref * trip["dcd_total"]
        try:
            pr_trip = propulsion.solve(best["V_ms"], drag_tripped, aircraft.powertrain())
            obj_trip = OBJECTIVES[mission.objective].evaluator(
                best["V_ms"], pr_trip["P_elec_w"], mission, aircraft.powertrain()
            )
        except ValueError:
            obj_trip = None
        tripped = {
            "dcd_total": trip["dcd_total"],
            "objective_tripped": obj_trip,
            "delta": (obj_trip - best.get("objective_value")) if obj_trip else None,
        }

    result.performance["optimization"] = {
        "champion": champion,
        "resolve_battery": battery,
        "discrete_studies": discrete_studies or None,
        "priced_options": priced or None,
        "winglet_study": winglet_study,
        "tripped_polars": tripped,
        "multistart": [
            {"start": s, **({k: v for k, v in r.items() if k != "clmax_3d_used"})}
            for s, r in zip(starts, results)
        ],
        "multistart_objective_spread": spread,
        "shadow_price_obj_per_gram": shadow_per_g,
        "flatness_span": flat,
        "nlp_vs_reeval_gap": (
            champion["objective_value"]
            - result.performance["best"].get("objective_value", float("nan"))
            if best is not None
            else None
        ),
    }
    result.notes.append(
        "M3 NLP: trimmed (explicit deflection), SM window, gust margin, spar "
        "stress/deflection sizing, ballast cap, battery-position balance."
    )
    # Measured per-solve peak, so the NEXT run's memory budget divides by data
    # rather than by the hard-coded fallback. Children cover the forked (parallel)
    # path; RUN_PEAK covers the in-process one, where the mark is reset between
    # solves and so cannot be read off the process at the end. `peak_rss_gb()`
    # on self remains as a floor for anything that ran outside a batch.
    result.diagnostics["peak_rss_gb"] = round(
        max(memory.peak_rss_gb(children=True), memory.peak_rss_gb(), RUN_PEAK.gb), 2
    )
    result.diagnostics["parallel_width"] = parallel
    result.diagnostics["solve_timeout_min"] = solve_timeout_min
    result.diagnostics["max_iter"] = max_iter
    # A truncated run must SAY it is truncated. `--max-iter 3` produces a full
    # artifact — champion, studies, sensitivities, a build document — that looks
    # exactly like a real one and describes an aeroplane no solver ever finished
    # converging. This project's recurring defect is the claim a run is not
    # entitled to make (FINDINGS §20), and this would be the easiest one yet to
    # make by accident.
    if max_iter < SOLVE_MAX_ITER:
        result.diagnostics["iteration_truncated"] = True
        log.warning(
            "THIS RUN WAS ITERATION-CAPPED at %d (default %d) — its numbers are "
            "not converged results", max_iter, SOLVE_MAX_ITER,
        )
        result.notes.insert(0, (
            f"THIS RUN IS NOT AN OPTIMIZATION. Every member was capped at "
            f"{max_iter} IPOPT iterations (default {SOLVE_MAX_ITER}), so the "
            "champion, the studies and every sensitivity below describe wherever "
            "each solve happened to be when it was stopped — not an optimum. "
            "Use it to exercise the pipeline, never to choose a design."
        ))
    # Which MODEL produced these numbers. Recorded unconditionally, not only when
    # checkpointing, because the question it answers — "is this run comparable
    # with that one?" — is asked of finished artifacts far more often than of
    # checkpoint directories, and until now the only way to answer it was to date
    # the run against the commit log by hand.
    result.diagnostics["model_fingerprint"] = fingerprint.model_fingerprint(aircraft, mission)
    phase_minutes["re-eval + artifacts"] = round(
        (time.monotonic() - t_start) / 60.0 - sum(phase_minutes.values()), 1
    )
    result.diagnostics["phase_minutes"] = phase_minutes
    # A phase that cost 0.0 minutes was either not run or fully resumed, and the
    # artifact could not tell those apart. Record the resumed fraction per phase,
    # and say so plainly in a note when a whole phase came off disk — "fresh
    # battery" and "re-ran the global search" are not the same claim.
    if cache is not None and cache.resumed:
        resumed = {
            label: f"{n} of {phase_members.get(label, n)} from checkpoint"
            for label, n in sorted(cache.resumed.items())
        }
        result.diagnostics["phase_resumed"] = resumed
        whole = [
            label for label, n in cache.resumed.items()
            if n >= phase_members.get(label, n) > 0
        ]
        if whole:
            result.notes.append(
                "RESUMED, not re-solved: " + ", ".join(sorted(whole)) + " came "
                "entirely from checkpoints written by an earlier run of the same "
                f"model ({result.diagnostics['model_fingerprint']}). The physics "
                "matches — that is what the fingerprint guarantees — but this run "
                "did not re-search those phases, so their 0.0-minute entries above "
                "are a resume, not a skip."
            )
    if memory_budget_gb is not None:
        result.diagnostics["memory_budget_gb"] = memory_budget_gb
    figures.flatness_plot(flat, champion, run_dir / "figures")
    # run.json is the machine-readable truth and is written first: rendering the
    # HTML must never be what loses a completed optimization.
    (run_dir / "run.json").write_text(
        __import__("json").dumps(__import__("dataclasses").asdict(result), indent=2, default=str),
        encoding="utf-8",
    )
    try:
        (run_dir / "report.html").write_text(report_html.render(result, run_dir), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("report.html could not be rendered (run.json is intact): %s", e)
    if live is not None:
        # The run directory exists only now, so this is the first moment the
        # frames can live beside the artifacts they describe. A PAUSED run never
        # reaches here (RunPaused propagates out of `batch`), which is exactly
        # right: its frames stay in the live directory for the resume to append
        # to. See `liveframe.relocate`.
        from . import liveframe

        liveframe.relocate(live.dir, run_dir)
    log.info(
        "done in %.1f min — champion objective %.4g, artifacts in %s",
        (time.monotonic() - t_start) / 60.0, champion["objective_value"], run_dir,
    )
    return result, run_dir


# --------------------------------------------------------------------------- M4

def pareto(aircraft, mission, values: list[float], runs_root: Path = Path("runs")) -> dict:
    """Epsilon-constraint sweep (MODEL_DETAILS 5.3): re-optimize with a swept floor
    on cruise speed — the natural endurance-vs-penetration trade for this class.
    Warm-starts each solve from the previous champion."""
    points, inits = [], None
    for v_floor in values:
        m2 = __import__("dataclasses").replace(
            mission, v_wind_ms=0.0, penetration_margin_ms=float(v_floor)
        )
        try:
            r = _solve_nlp(aircraft, m2, inits=inits)
            inits = {**r["dv"], "V": r["V_ms"]}
            points.append({"v_floor": float(v_floor), **{k: r[k] for k in
                           ("objective_value", "V_ms", "P_elec_w", "auw_kg")},
                           "span": r["dv"]["span"]})
        except RuntimeError as e:
            points.append({"v_floor": float(v_floor), "failed": str(e)[:100]})
    return {"axis": "min cruise speed (m/s)", "points": points}


def airfoil_study(aircraft, mission, candidates: list[str]) -> dict:
    """Discrete outer loop (MODEL_DETAILS 6.3): full continuous solve per airfoil,
    champions compared under smooth AND tripped polars (rejection rule 3.2):
    a candidate whose tripped objective ranking flips is laminar-fragile."""
    objective = OBJECTIVES[mission.objective]
    pt = aircraft.powertrain()
    results = {}
    original = aircraft.wing_airfoil
    try:
        for name in candidates:
            aircraft.wing_airfoil = name
            try:
                r = _solve_nlp(aircraft, mission)
                plane = aircraft.geometry(r["dv"])
                q = 0.5 * 1.225 * r["V_ms"] ** 2
                s_ref = float(plane.s_ref)
                cl = r["auw_kg"] * G / (q * s_ref)
                trip = aero.tripped_cd_delta(plane, r["V_ms"], cl)
                obj_tripped = None
                try:
                    pr = propulsion.solve(
                        r["V_ms"], r["drag_n"] + q * s_ref * trip["dcd_total"], pt
                    )
                    obj_tripped = objective.evaluator(r["V_ms"], pr["P_elec_w"], mission, pt)
                except ValueError:
                    pass
                results[name] = {
                    "objective_smooth": r["objective_value"],
                    "objective_tripped": obj_tripped,
                    "dv": r["dv"], "V_ms": r["V_ms"], "auw_kg": r["auw_kg"],
                    "tripped_dcd": trip["dcd_total"],
                }
            except RuntimeError as e:
                results[name] = {"failed": str(e)[:120]}
    finally:
        aircraft.wing_airfoil = original
    return results
