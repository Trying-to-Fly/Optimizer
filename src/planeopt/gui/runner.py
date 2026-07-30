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
            job.state = JobState.DONE if exit_code == 0 else JobState.FAILED
        if job.state is JobState.DONE:
            job.run_dir = parse_run_dir(self._stdout, job.runs_dir)

        self.queue_changed.emit()
        self.job_finished.emit(job)
        self._start_next()

    def shutdown(self) -> None:
        """Kill any running child — a solve would otherwise outlive the window."""
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(3000)
