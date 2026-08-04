"""The job queue, on disk, so a paused run survives closing the app.

WHY THIS EXISTS

Pausing a battery exists to give the machine back — a solve holds ~14 GB for
hours — and the natural next thing to do with a machine you have just been given
back is close the app. That lost the job: the queue was a list in memory, so the
checkpoints survived and the Resume button had nothing left to point at. The
work was recoverable only by re-filling the New Run dialog from memory and
hoping every field matched, which is exactly what `RunQueue.resume` exists to
avoid.

Qt-free, like `jobs.py` and `runindex.py`, so the behaviour is testable without a
display.

TWO RULES WORTH KNOWING

**Nothing starts on its own at launch.** Every restored job comes back PAUSED,
including one that was QUEUED and had not begun and one that was RUNNING when the
window closed. Opening the app must never be what commits the machine to a
two-hour solve, and "press Resume to start" is one rule the reader can hold rather
than three states with different launch behaviour. A restored job that had never
started simply begins at its first member; a checkpoint directory it never wrote
to is empty, which is the same thing.

**Terminal states are not persisted.** DONE, FAILED and CANCELLED jobs cannot be
acted on, so keeping them would grow the queue list forever across sessions while
the runs list already records every finished run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .jobs import Job, JobState

#: Lives beside `_checkpoints`, `_logs` and `_diagnostics` under the runs
#: directory — the same convention, and gitignored for the same reason.
FILENAME = "_queue.json"

#: What survives a restart, split by how it is written back.
#:
#: `log` is excluded — the child's transient output, thousands of lines, and the
#: progress pane starts empty anyway. `run_dir` is excluded because a restorable
#: job has not produced one: a job with a run directory is DONE, which is not a
#: state this file keeps.
_REQUIRED_PATHS = ("mission", "aircraft", "runs_dir")
_OPTIONAL_PATHS = ("checkpoint_dir", "pause_file")
_PLAIN = ("optimize", "multistart", "flatness", "memory_budget_gb", "solve_timeout_min")

RESTORABLE = (JobState.QUEUED, JobState.RUNNING, JobState.PAUSED)


def path_for(runs_dir: Path) -> Path:
    return Path(runs_dir) / FILENAME


def save(runs_dir: Path, jobs: list[Job]) -> None:
    """Write the resumable jobs. Never raises — losing the queue file must not
    take down a window that is otherwise working, and the checkpoints (the part
    that took hours) are not in here."""
    target = path_for(runs_dir)
    payload = [
        {
            **{k: (str(getattr(job, k)) if getattr(job, k) is not None else None)
               for k in (*_REQUIRED_PATHS, *_OPTIONAL_PATHS)},
            **{k: getattr(job, k) for k in _PLAIN},
            "state": job.state.value,
        }
        for job in jobs
        if job.state in RESTORABLE
    ]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # write-then-rename, so a crash mid-write cannot leave a half file that
        # the next launch parses into a job with a missing aircraft
        tmp = target.with_suffix(".json.part")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        pass


def load(runs_dir: Path) -> list[Job]:
    """Read the queue back, every job PAUSED. Never raises: an unreadable or
    outdated file means an empty queue, not a window that will not open."""
    target = path_for(runs_dir)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []

    jobs: list[Job] = []
    for entry in payload:
        if not isinstance(entry, dict) or not all(entry.get(k) for k in _REQUIRED_PATHS):
            continue  # an entry from an older schema, or a truncated one
        fields = {k: Path(entry[k]) for k in _REQUIRED_PATHS}
        fields.update(
            {k: Path(entry[k]) for k in _OPTIONAL_PATHS if entry.get(k)}
        )
        # A key that is absent or null keeps the dataclass default, which is the
        # right answer for both halves: `multistart` has a real default that must
        # not be overwritten with None, and `memory_budget_gb` defaults to None
        # anyway.
        fields.update({k: entry[k] for k in _PLAIN if entry.get(k) is not None})
        try:
            job = Job(**fields)
        except TypeError:
            continue
        job.state = JobState.PAUSED
        jobs.append(job)
    return jobs
