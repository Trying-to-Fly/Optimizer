"""Sequential run queue over QProcess.

One job at a time by design: a single NLP solve peaks near 13 GB, so a second
concurrent solve is how you meet the OOM killer rather than how you go faster
(and on Windows there is no fork-based concurrency at all).

Progress arrives as the child's stderr — solve.py logs there — and is emitted
line by line so the UI can show a live tail instead of a frozen window.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal

from .jobs import Job, JobState, parse_run_dir, program_and_args


def _was_paused(job: Job) -> bool:
    """Did this exit-0 child stop on request rather than finish?

    Read from the SENTINEL FILE rather than from the child's output. `cli.optimize`
    unlinks the sentinel at startup, so its presence when the child exits is a
    record that a pause was asked for and honoured — where stdout can interleave
    with hours of solver chatter, and a distinct exit code would break the
    contract the CLI documents for shell users ("a pause is a successful outcome,
    not a failure: exit 0").

    `run_dir is None` is the second half, and it covers the one case the sentinel
    alone gets wrong: a pause requested so late that the battery finished its
    last member anyway. That run produced artifacts, so it is DONE.
    """
    return (
        job.pause_file is not None
        and job.run_dir is None
        and job.pause_file.exists()
    )


class RunQueue(QObject):
    """Owns the pending jobs and the one child process that may be running."""

    queue_changed = Signal()  # any job's state changed, or the queue's contents
    job_output = Signal(object, str)  # (Job, one line of output)
    job_finished = Signal(object)  # (Job) — terminal state reached

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.jobs: list[Job] = []
        self._process: QProcess | None = None
        self._current: Job | None = None
        self._stdout = ""

    # --- queue management -------------------------------------------------

    def submit(self, job: Job) -> None:
        self.jobs.append(job)
        self.queue_changed.emit()
        self._start_next()

    def restore(self, jobs: list[Job]) -> None:
        """Adopt jobs read back from disk, WITHOUT starting any of them.

        The one difference from `submit`, and the reason this is a separate
        method rather than a flag: opening the window must never be what commits
        the machine to a two-hour solve. `queuestore.load` brings everything back
        PAUSED, so the Resume button is the only thing that starts one.
        """
        self.jobs.extend(jobs)
        self.queue_changed.emit()

    def pause(self, job: Job) -> bool:
        """Ask a running job to stop at its next member boundary.

        Unlike cancel, this keeps the work: the child writes each finished
        member to its checkpoint directory and exits cleanly, so re-queuing the
        same job continues instead of restarting. It cannot be instant — a solve
        in progress holds ~13 GB of solver state that cannot be saved, so the
        only stop that frees memory without discarding work is one that waits
        for the member to finish (up to the solve timeout).
        """
        if job is not self._current or self._process is None or not job.pause_file:
            return False
        job.pause_file.parent.mkdir(parents=True, exist_ok=True)
        job.pause_file.write_text("pause requested from the GUI\n", encoding="utf-8")
        return True

    def resume(self, job: Job) -> bool:
        """Put a paused job back in the queue, continuing where it stopped.

        Everything needed is already on the Job — same mission, same aircraft,
        same checkpoint directory — so resuming is re-queuing it, not filling the
        New Run dialog in again from memory and hoping every field matches. A
        mismatched field would not fail loudly; it would produce a run whose
        members came from two different configurations.

        The pause sentinel is deliberately NOT cleared here. `cli.optimize`
        unlinks it at startup and says so in its output, which keeps one owner
        for that file and makes a CLI resume behave identically to this one.
        """
        if job.state is not JobState.PAUSED:
            return False
        job.state = JobState.QUEUED
        job.exit_code = None
        self.queue_changed.emit()
        self._start_next()
        return True

    def cancel(self, job: Job) -> None:
        """Cancel a queued job, or kill it if it is the running one."""
        if job is self._current and self._process is not None:
            job.state = JobState.CANCELLED
            self._process.kill()  # terminate() is ignored by a solver mid-iteration
            return
        if job.state is JobState.QUEUED:
            job.state = JobState.CANCELLED
            self.queue_changed.emit()
            self.job_finished.emit(job)

    @property
    def running(self) -> Job | None:
        return self._current

    # --- process plumbing -------------------------------------------------

    def _start_next(self) -> None:
        if self._current is not None:
            return
        pending = [j for j in self.jobs if j.state is JobState.QUEUED]
        if not pending:
            return
        job = pending[0]

        program, args = program_and_args(job)
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(args)
        process.readyReadStandardError.connect(self._read_stderr)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._current = job
        self._process = process
        self._stdout = ""
        job.state = JobState.RUNNING
        self._append(job, f"$ {program} {' '.join(args)}")
        self.queue_changed.emit()
        process.start()

    def _append(self, job: Job, text: str) -> None:
        for line in text.splitlines():
            if line.strip():
                job.log.append(line)
                self.job_output.emit(job, line)

    def _read_stderr(self) -> None:
        if self._process is None or self._current is None:
            return
        chunk = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        self._append(self._current, chunk)

    def _read_stdout(self) -> None:
        if self._process is None or self._current is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        self._stdout += chunk
        self._append(self._current, chunk)

    def _on_error(self, error) -> None:
        if self._current is not None:
            self._append(self._current, f"process error: {error}")

    def _on_finished(self, exit_code: int, _status) -> None:
        job, self._current, process = self._current, None, self._process
        self._process = None
        if process is not None:
            process.deleteLater()
        if job is None:
            return

        job.exit_code = exit_code
        if job.state is not JobState.CANCELLED:
            if exit_code == 0:
                job.run_dir = parse_run_dir(self._stdout, job.runs_dir)
                job.state = JobState.PAUSED if _was_paused(job) else JobState.DONE
            else:
                job.state = JobState.FAILED

        self.queue_changed.emit()
        self.job_finished.emit(job)
        self._start_next()

    def shutdown(self) -> None:
        """Kill any running child — a solve would otherwise outlive the window."""
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(3000)
