"""What the queue executes — Qt-free so the command building is testable.

Every job is a subprocess of this same program, not an in-process call. A solve
peaks near 14.5 GB and can be killed by the OOM killer; as a child that takes down
one job, while in-process it would take down the GUI with the queue in it. It
also makes cancellation a kill rather than a cooperative-interrupt problem, and
means the GUI drives exactly the code path the CLI does.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

# Qt-free, like this module: `missionfile` is stdlib plus `..types`, so the
# name-sanitising rule stays in one place without dragging a dialog in behind it.
from . import missionfile

#: A live-frame directory reserved for ONE job looks like
#: `<stamp>-<mission>-<aircraft>`. Anything else in `runs/_live/` is a shared
#: directory from before that reservation existed — see `reserve_live_dir`.
_RESERVED_LIVE_DIR = re.compile(r"^\d{8}T\d{6}(-|$)")


def reserve_live_dir(runs_dir: Path, mission_name: str, aircraft_name: str) -> Path:
    """An EMPTY live-frame directory that belongs to exactly one job.

    Named `<stamp>-<mission>-<aircraft>` after `assemble.write_run_dir`'s own
    slug, so `runs/_live/` reads like `runs/` does.

    It is CREATED here rather than merely named, and that is what makes it
    unique: the stamp has one-second resolution, so two jobs queued in the same
    second would otherwise collide — which is the very bug this exists to close.
    `mkdir(exist_ok=False)` is the reservation, and the numeric suffix is the
    loser's fallback. Creating it early costs nothing: `FrameWriter` and
    `liveframe.write_view` both mkdir it anyway, and `liveframe.relocate` removes
    it when the run finishes.

    Lives here rather than in `newrun` because the dialog is no longer the only
    caller: a job restored from the queue file may carry a pre-reservation path,
    and `RunQueue.resume` has to be able to give it a fresh one. `queuestore` is
    Qt-free and could not have imported it from a dialog module.
    """
    # Local time, deliberately: these names are read by a human beside a machine,
    # not compared across time zones — same convention as a run directory.
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")  # noqa: DTZ005
    # Sanitised HERE and not only by the caller. This builds ONE path component
    # out of two names, so a `/` in either would silently make it three — and
    # the mission name is free text from the New Run dialog. `RunQueue.resume`
    # is now a second caller, passing `job.mission.stem`, so the guard belongs
    # with the function rather than with one of its callers.
    base = "-".join((
        stamp, missionfile.module_name(mission_name), missionfile.module_name(aircraft_name),
    ))
    parent = runs_dir / "_live"
    for attempt in range(1, 1000):
        candidate = parent / (base if attempt == 1 else f"{base}-{attempt}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    # A thousand live directories in one second is not a state worth a branch;
    # fall back to the plain name rather than refusing to queue the run. Frames
    # are a view of a solve and must never be what stops one.
    return parent / base


def is_reserved_live_dir(path: Path | None) -> bool:
    """Was this directory reserved for one job, or is it the shared old kind?

    `runs/_live/rcv2_endurance` is the pre-2026-08-08 naming: one directory per
    MISSION, shared by every run of it. `FrameWriter` starts one past the
    highest sequence already on disk, so resuming into one adopts whatever a
    cancelled run left there — the defect `reserve_live_dir` closed at the
    dialog. A job persisted BEFORE that fix still carries the shared path, and
    the queue file round-trips it faithfully, so the fix has to be applied on
    the way back in as well.
    """
    return path is not None and bool(_RESERVED_LIVE_DIR.match(Path(path).name))


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    #: Stopped at a member boundary on request, with everything finished so far
    #: on disk. A state of its own because the child EXITS 0 for it (a pause is a
    #: successful outcome, not a crash), so without this it was indistinguishable
    #: from DONE — a paused battery read "✓ done" and offered no way back.
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """One queued run."""

    mission: Path
    aircraft: Path
    runs_dir: Path
    optimize: bool = True
    multistart: int = 3
    flatness: bool = True
    memory_budget_gb: float | None = None
    #: wall-clock ceiling for ONE member solve (solve.SOLVE_TIMEOUT_MIN)
    solve_timeout_min: float | None = None
    #: Where per-member results are kept so a paused run can be resumed, and the
    #: sentinel whose existence asks the run to stop at the next member boundary.
    #: Both derive from the run directory so a user never has to invent a path.
    checkpoint_dir: Path | None = None
    pause_file: Path | None = None
    #: Where the live viewer's frames go while this run is going (M5.4). Under
    #: `runs/_live/` rather than in the run directory, because the run directory
    #: does not exist until the run ENDS; `liveframe.relocate` moves them into
    #: `<run_dir>/frames/` at that point.
    live_dir: Path | None = None
    #: Which camera preset a timelapse of this run should be rendered from
    #: (`render3d.VIEW_PRESETS`). Chosen before the run starts, because the point
    #: of picking it then is not having to be at the machine afterwards. Not a
    #: CLI argument: the solver has no camera. The GUI records it as a sidecar in
    #: `live_dir`, which travels with the frames into the finished run — so it
    #: still applies to a timelapse rendered months later, from anywhere.
    timelapse_view: str | None = None
    state: JobState = JobState.QUEUED
    log: list[str] = field(default_factory=list)
    run_dir: Path | None = None  # parsed out of the child's final stdout line
    exit_code: int | None = None

    @property
    def title(self) -> str:
        verb = "optimize" if self.optimize else "evaluate"
        return f"{verb} {self.aircraft.name} / {self.mission.stem}"


def planeopt_command(args: list[str]) -> tuple[str, list[str]]:
    """How to invoke this same program as a child, as (program, args).

    Frozen: this executable *is* the CLI, so it takes the subcommand directly.
    Source: go through `python -m planeopt` rather than a `planeopt` console
    script, which may not be on PATH in a venv-less invocation.

    Shared by the run queue and by the live viewer's timelapse button, so a
    packaged build cannot end up able to launch one and not the other.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, list(args)
    return sys.executable, ["-m", "planeopt", *args]


def program_and_args(job: Job) -> tuple[str, list[str]]:
    """The child process that runs `job`, as (program, args)."""
    args = [
        "optimize" if job.optimize else "run",
        str(job.mission),
        "--aircraft",
        str(job.aircraft),
        "--runs-dir",
        str(job.runs_dir),
    ]
    if job.optimize:
        args += ["--multistart", str(job.multistart)]
        if not job.flatness:
            args += ["--no-flatness"]
        # The width is derived in the child, not here: it depends on free RAM
        # and on the per-solve peak recorded in runs/, both of which are truer
        # at launch than they were when the dialog was filled in.
        if job.memory_budget_gb:
            args += ["--memory-budget-gb", str(job.memory_budget_gb)]
        if job.solve_timeout_min:
            args += ["--solve-timeout-min", str(job.solve_timeout_min)]
        if job.checkpoint_dir:
            args += ["--checkpoint", str(job.checkpoint_dir)]
        if job.pause_file:
            args += ["--pause-file", str(job.pause_file)]
        if job.live_dir:
            args += ["--live-dir", str(job.live_dir)]

    return planeopt_command(args)


def parse_run_dir(stdout: str, runs_dir: Path) -> Path | None:
    """Pull the run directory out of the child's output.

    Both CLI commands print the run directory as their last line; scan upward so
    a trailing newline or a stray line does not lose it.
    """
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
        candidate = Path(line)
        if candidate.is_dir() and candidate.name.startswith(("2", "1")):
            return candidate
        if (runs_dir / candidate.name).is_dir():
            return runs_dir / candidate.name
    return None
