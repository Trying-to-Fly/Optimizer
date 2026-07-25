"""What the queue executes — Qt-free so the command building is testable.

Every job is a subprocess of this same program, not an in-process call. A solve
peaks near 13 GB and can be killed by the OOM killer; as a child that takes down
one job, while in-process it would take down the GUI with the queue in it. It
also makes cancellation a kill rather than a cooperative-interrupt problem, and
means the GUI drives exactly the code path the CLI does.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
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
    state: JobState = JobState.QUEUED
    log: list[str] = field(default_factory=list)
    run_dir: Path | None = None  # parsed out of the child's final stdout line
    exit_code: int | None = None

    @property
    def title(self) -> str:
        verb = "optimize" if self.optimize else "evaluate"
        return f"{verb} {self.aircraft.name} / {self.mission.stem}"


def program_and_args(job: Job) -> tuple[str, list[str]]:
    """The child process to launch, as (program, args).

    Frozen: this executable *is* the CLI, so it takes the subcommand directly.
    Source: go through `python -m planeopt` rather than a `planeopt` console
    script, which may not be on PATH in a venv-less invocation.
    """
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

    if getattr(sys, "frozen", False):
        return sys.executable, args
    return sys.executable, ["-m", "planeopt", *args]


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
