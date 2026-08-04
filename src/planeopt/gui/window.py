"""The main window: runs on the left, detail/compare on the right, queue below.

Layout follows how the work actually goes — you look at past runs far more often
than you launch new ones, and when one is running you want its progress visible
without losing the run you were reading.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from . import queuestore, runindex
from .jobs import Job, JobState
from .newrun import NewRunDialog
from .runner import RunQueue
from .views import MONO_FAMILIES, CompareView, DetailView
from .workspace import Workspace, resolve

_STATE_MARK = {
    JobState.QUEUED: "·",
    JobState.RUNNING: "▶",
    JobState.DONE: "✓",
    # "▮▮" (U+25AE), not "⏸" (U+23F8): no font on this machine carries the
    # Miscellaneous-Technical pause glyph and it rendered as a tofu box. U+25AE
    # is in Geometric Shapes, the same block as the ▶ above it, so it renders
    # wherever that one does and matches its weight.
    JobState.PAUSED: "▮▮",
    JobState.FAILED: "✗",
    JobState.CANCELLED: "—",
}

PAUSE_LABEL = "Pause running job"
PAUSE_TIP = (
    "Stop after the member solve currently in flight, keeping everything "
    "finished so far and freeing the memory. It is not instant: a solve in "
    "progress holds ~13 GB of solver state that cannot be saved, so the wait "
    "is up to one member."
)
RESUME_LABEL = "Resume paused job"
RESUME_TIP = (
    "Continue this job from its checkpoint directory. Members already solved "
    "are read from disk rather than re-solved, and the run picks up at the one "
    "it stopped before."
)

STYLE = """
QMainWindow, QWidget { background: #1c1c1f; color: #e4e4e7; }
QTreeWidget, QPlainTextEdit, QTableWidget {
    background: #232326; border: 1px solid #2f2f34; border-radius: 6px;
    alternate-background-color: #27272b;
    gridline-color: #2f2f34;
    selection-background-color: #2d4a73;
}
/* Qt ships a light scrollbar that glares against this palette. */
QScrollBar:vertical, QScrollBar:horizontal { background: #1c1c1f; border: none; }
QScrollBar:vertical { width: 11px; }
QScrollBar:horizontal { height: 11px; }
QScrollBar::handle {
    background: #3a3a40; border-radius: 5px; min-height: 28px; min-width: 28px;
}
QScrollBar::handle:hover { background: #4a4a52; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QTreeWidget::item { padding: 5px 4px; }
QTreeWidget::item:selected { background: #2d4a73; }
QHeaderView::section {
    background: #232326; color: #9a9aa0; border: none;
    border-bottom: 1px solid #2f2f34; padding: 6px;
}
QPushButton {
    background: #2f2f34; border: 1px solid #3a3a40; border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background: #3a3a40; }
QPushButton:disabled { color: #6a6a70; background: #262629; }
QPushButton#primary { background: #2d4a73; border-color: #3a5f8f; }
QPushButton#primary:hover { background: #365a8c; }
QGroupBox {
    border: 1px solid #2f2f34; border-radius: 6px; margin-top: 10px; padding-top: 10px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #9a9aa0; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #232326; border: 1px solid #3a3a40; border-radius: 5px; padding: 4px 6px;
}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #4a7ab5;
}
QSpinBox:disabled, QDoubleSpinBox:disabled { color: #6a6a70; background: #262629; }
/* Give the steppers a matching background but leave the arrows to Qt: a
   stylesheet ::up-arrow needs a real image, and `image: none` just blanks it. */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #2f2f34; border: none; width: 17px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #44444c; }
QCheckBox, QRadioButton { spacing: 7px; }
QMenuBar { background: #1c1c1f; }
QMenuBar::item:selected { background: #2f2f34; }
QMenu { background: #232326; border: 1px solid #3a3a40; }
QMenu::item:selected { background: #2d4a73; }
QSplitter::handle { background: #1c1c1f; }
"""


SETTINGS_ORG = "planeopt"
SETTINGS_APP = "planeopt"
WORKSPACE_KEY = "workspace"


class MainWindow(QMainWindow):
    def __init__(self, workspace: Workspace) -> None:
        super().__init__()
        self.workspace = workspace
        self.summaries: list[runindex.RunSummary] = []

        self.setWindowTitle(f"planeopt {__version__}")
        self.resize(1180, 760)

        self.queue = RunQueue(self)
        self.queue.queue_changed.connect(self._refresh_queue)
        self.queue.queue_changed.connect(self._save_queue)
        self.queue.job_output.connect(self._on_output)
        self.queue.job_finished.connect(self._on_job_finished)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 800])
        self.setCentralWidget(splitter)

        self._build_menu()
        self.reload()
        self._restore_queue()

    # --- construction ------------------------------------------------------

    def _build_left(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 6, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.runs_label = QLabel("Runs")
        self.runs_label.setStyleSheet("font-size:13px; font-weight:600;")
        header.addWidget(self.runs_label)
        header.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        header.addWidget(refresh)
        layout.addLayout(header)

        self.run_tree = QTreeWidget()
        self.run_tree.setColumnCount(3)
        self.run_tree.setHeaderLabels(["When", "Aircraft", "Result"])
        self.run_tree.setRootIsDecorated(False)
        self.run_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.run_tree.itemSelectionChanged.connect(self._on_selection)
        # WHICH column is allowed to run out of room, decided here rather than by
        # whichever happens to be last. Sizing all three to their contents
        # overflowed the panel and clipped `Result` — the objective value, the one
        # number the list exists to show, rendered as "150." — while the aircraft
        # name, which the detail pane repeats in full, kept every pixel it asked
        # for. So: the ends size to their contents and the middle absorbs the
        # squeeze, eliding with a tooltip.
        run_header = self.run_tree.header()
        run_header.setStretchLastSection(False)
        run_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        run_header.setSectionResizeMode(1, QHeaderView.Stretch)
        run_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.run_tree, 1)

        self.new_run_button = QPushButton("New run…")
        self.new_run_button.setObjectName("primary")
        self.new_run_button.clicked.connect(self.new_run)
        layout.addWidget(self.new_run_button)

        queue_label = QLabel("Queue")
        queue_label.setStyleSheet("font-size:13px; font-weight:600; margin-top:6px;")
        layout.addWidget(queue_label)

        self.queue_tree = QTreeWidget()
        self.queue_tree.setColumnCount(2)
        self.queue_tree.setHeaderLabels(["Job", "State"])
        self.queue_tree.setRootIsDecorated(False)
        self.queue_tree.setMaximumHeight(150)
        # Same rule as the runs list: the title elides, the state does not.
        # "running" vs "failed" is what the row is read for.
        queue_header = self.queue_tree.header()
        queue_header.setStretchLastSection(False)
        queue_header.setSectionResizeMode(0, QHeaderView.Stretch)
        queue_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.queue_tree.itemSelectionChanged.connect(self._on_queue_selection)
        layout.addWidget(self.queue_tree)

        # Pause before Cancel: they look alike but one keeps the work and the
        # other throws away hours of it, so the safe one reads first.
        #
        # ONE button for pause and resume, because they are the same affordance
        # applied to the same job and can never both be available: a job is either
        # running or paused. Its LABEL always names the action it will take, so
        # there is nothing to infer at the moment of clicking — and a third
        # button in this stack would sit disabled almost all of the time.
        self.pause_button = QPushButton(PAUSE_LABEL)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._pause_or_resume_selected)
        layout.addWidget(self.pause_button)

        self.cancel_button = QPushButton("Cancel selected job")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_selected)
        layout.addWidget(self.cancel_button)
        return panel

    def _build_right(self) -> QWidget:
        panel = QSplitter(Qt.Vertical)

        self.stack = QStackedWidget()
        self.detail = DetailView()
        self.compare = CompareView()
        self.stack.addWidget(self.detail)
        self.stack.addWidget(self.compare)
        panel.addWidget(self.stack)

        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(12, 6, 12, 12)
        log_layout.setSpacing(6)
        self.log_label = QLabel("Progress")
        self.log_label.setStyleSheet("font-size:11px; color:#9a9aa0; font-weight:600;")
        log_layout.addWidget(self.log_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        # Absolute paths wrap into a wall of text otherwise; scroll instead.
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont()
        font.setFamilies(MONO_FAMILIES)
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(9)
        self.log.setFont(font)
        self.log.setPlaceholderText("Progress from a running solve appears here.")
        log_layout.addWidget(self.log)
        panel.addWidget(log_panel)

        panel.setStretchFactor(0, 3)
        panel.setStretchFactor(1, 1)
        panel.setSizes([520, 200])
        return panel

    def _build_menu(self) -> None:
        run_menu = self.menuBar().addMenu("&Run")
        new_action = QAction("&New run…", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_run)
        run_menu.addAction(new_action)

        open_action = QAction("&Open project folder…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.choose_workspace)
        run_menu.addAction(open_action)

        refresh_action = QAction("&Refresh runs", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.reload)
        run_menu.addAction(refresh_action)

        run_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        run_menu.addAction(quit_action)

    # --- runs --------------------------------------------------------------

    def set_workspace(self, workspace: Workspace, remember: bool = True) -> None:
        self.workspace = workspace
        if remember:
            QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(WORKSPACE_KEY, str(workspace.root))
        self.reload()

    def choose_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a project folder (the one containing aircraft/ and missions/)",
            str(self.workspace.root),
        )
        if chosen:
            self.set_workspace(Workspace(Path(chosen)))

    def reload(self) -> None:
        selected = {i.data(0, Qt.UserRole) for i in self.run_tree.selectedItems()}
        self.summaries = runindex.scan(self.workspace.runs_dir)
        self.run_tree.clear()
        for summary in self.summaries:
            item = QTreeWidgetItem(
                [
                    summary.stamp,
                    summary.aircraft or "—",
                    summary.error and "unreadable" or summary.objective_text,
                ]
            )
            item.setData(0, Qt.UserRole, str(summary.path))
            # The aircraft column is the one that elides (see _build_left), so it
            # is the one that has to carry its full text somewhere.
            item.setToolTip(1, summary.aircraft or "—")
            if summary.error:
                item.setForeground(2, Qt.gray)
            elif summary.violated_constraints:
                item.setToolTip(2, "violated: " + ", ".join(summary.violated_constraints))
            if str(summary.path) in selected:
                item.setSelected(True)
            self.run_tree.addTopLevelItem(item)
        self.runs_label.setText(f"Runs ({len(self.summaries)})")
        self._update_workspace_state()
        self._on_selection()

    def _update_workspace_state(self) -> None:
        """Say plainly where we are looking, and disable what cannot work.

        A packaged app launched from the wrong folder finds nothing; showing an
        empty list with a live New-run button just moves the confusion later.
        """
        usable = self.workspace.is_usable
        aircraft = self.workspace.aircraft_packages()
        self.new_run_button.setEnabled(bool(aircraft))
        if not usable:
            self.statusBar().showMessage(
                f"No aircraft/ or missions/ in {self.workspace.root} — "
                "use Run ▸ Open project folder…"
            )
        elif not aircraft:
            self.statusBar().showMessage(
                f"{self.workspace.root} — no aircraft definitions found in aircraft/"
            )
        else:
            self.statusBar().showMessage(
                f"{self.workspace.root} — {len(aircraft)} aircraft, "
                f"{len(self.workspace.missions())} missions"
            )

    def _selected_summaries(self) -> list[runindex.RunSummary]:
        paths = {i.data(0, Qt.UserRole) for i in self.run_tree.selectedItems()}
        return [s for s in self.summaries if str(s.path) in paths]

    def _on_selection(self) -> None:
        selected = self._selected_summaries()
        if len(selected) == 1:
            self.detail.show_run(selected[0])
            self.stack.setCurrentWidget(self.detail)
        elif len(selected) > 1:
            self.compare.show_runs(selected)
            self.stack.setCurrentWidget(self.compare)
        else:
            self.detail.show_placeholder(
                "Select a run to see its details.\nSelect several to compare them."
            )
            self.stack.setCurrentWidget(self.detail)

    # --- queue -------------------------------------------------------------

    def new_run(self) -> None:
        dialog = NewRunDialog(self.workspace, self)
        if dialog.exec() != NewRunDialog.Accepted:
            return
        try:
            job = dialog.job()
        except OSError as e:
            QMessageBox.critical(self, "Could not write mission", str(e))
            return
        self.queue.submit(job)
        self._log_line(f"queued: {job.title}")

    # --- queue persistence -------------------------------------------------

    def _save_queue(self) -> None:
        queuestore.save(self.workspace.runs_dir, self.queue.jobs)

    def _restore_queue(self) -> None:
        """Bring back a paused run from a previous session.

        Pausing exists to give the machine back, and the next thing anyone does
        with a machine they have just been given back is close the app — which
        used to lose the job while its checkpoints sat on disk with nothing left
        pointing at them.
        """
        restored = queuestore.load(self.workspace.runs_dir)
        if not restored:
            return
        self.queue.restore(restored)
        count = f"{len(restored)} job" + ("" if len(restored) == 1 else "s")
        self._log_line(
            f"-- restored {count} from the previous session. Nothing starts on its "
            f"own: select one and press “{RESUME_LABEL}”. --"
        )

    def _log_line(self, text: str) -> None:
        """Append to the progress pane, keeping the view at the LEFT margin.

        `appendPlainText` leaves the cursor at the end of what it wrote, and the
        pane does not wrap (by design — absolute paths would become a wall of
        text), so one long line scrolled the view right and the next lines
        arrived with their beginnings off-screen. Vertical auto-scroll is what a
        log tail wants; horizontal auto-scroll is not.

        Done by moving the CURSOR to the start of the line rather than by setting
        the scrollbar: Qt's own `ensureCursorVisible` runs at the next layout and
        would undo a scrollbar written here, so the fix has to be the thing Qt is
        about to scroll to.
        """
        self.log.appendPlainText(text)
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock)
        self.log.setTextCursor(cursor)

    def _refresh_queue(self) -> None:
        previous = {i.data(0, Qt.UserRole) for i in self.queue_tree.selectedItems()}
        self.queue_tree.clear()
        for job in self.queue.jobs:
            item = QTreeWidgetItem([job.title, f"{_STATE_MARK[job.state]} {job.state.value}"])
            item.setData(0, Qt.UserRole, id(job))
            self.queue_tree.addTopLevelItem(item)
            # Keep the selection across refreshes, and select the running job when
            # there is none — otherwise Cancel sits disabled while a solve runs,
            # which is exactly when you want to reach for it.
            if id(job) in previous or (not previous and job is self.queue.running):
                item.setSelected(True)
        running = self.queue.running
        self.log_label.setText(f"Progress — {running.title}" if running else "Progress")
        self._on_queue_selection()

    def _on_queue_selection(self) -> None:
        job = self._selected_job()
        self.cancel_button.setEnabled(
            job is not None and job.state in (JobState.QUEUED, JobState.RUNNING)
        )
        # The one button says which of the two it will do. Pause needs the
        # running job and a checkpoint to resume from; resume needs a paused one,
        # which by construction already has both.
        can_pause = (
            job is not None and job.state is JobState.RUNNING and bool(job.pause_file)
        )
        can_resume = job is not None and job.state is JobState.PAUSED
        self.pause_button.setEnabled(can_pause or can_resume)
        self.pause_button.setText(RESUME_LABEL if can_resume else PAUSE_LABEL)
        self.pause_button.setToolTip(RESUME_TIP if can_resume else PAUSE_TIP)

    def _selected_job(self) -> Job | None:
        items = self.queue_tree.selectedItems()
        if not items:
            return None
        job_id = items[0].data(0, Qt.UserRole)
        return next((j for j in self.queue.jobs if id(j) == job_id), None)

    def _cancel_selected(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.queue.cancel(job)

    def _pause_or_resume_selected(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        if job.state is JobState.PAUSED:
            if self.queue.resume(job):
                self._log_line(f"-- resuming {job.title} from {job.checkpoint_dir} --")
            return
        if not self.queue.pause(job):
            return
        self.pause_button.setEnabled(False)
        self._log_line(
            "-- pause requested: the run will stop after the member solve in "
            "flight and keep everything finished so far --"
        )

    def _on_output(self, job: Job, line: str) -> None:
        if job is self.queue.running:
            self._log_line(line)

    def _on_job_finished(self, job: Job) -> None:
        self._log_line(f"— {job.title}: {job.state.value}")
        if job.state is JobState.FAILED:
            self.statusBar().showMessage(f"{job.title} failed (exit {job.exit_code})", 10000)
        elif job.state is JobState.PAUSED:
            # A pause produces no run directory, so nothing appears in the runs
            # list and the only feedback would otherwise be a row changing mark.
            # Two lines, because the log pane does not wrap (by design, line 260):
            # the instruction has to fit unscrolled, and the absolute path cannot.
            self._log_line(
                f"-- paused. Select the job and press “{RESUME_LABEL}” to continue. --"
            )
            self._log_line(f"   finished members are in {job.checkpoint_dir}")
            self.statusBar().showMessage(
                f"Paused — select the job and press “{RESUME_LABEL}” to continue", 20000
            )
        # A finished run means a new directory to browse; give the filesystem a
        # moment so the artifacts are all present when we re-scan. Then show it:
        # the result you just waited hours for should not need hunting for.
        QTimer.singleShot(400, lambda: self._reload_and_select(job.run_dir))

    def _reload_and_select(self, run_dir: Path | None) -> None:
        self.reload()
        if run_dir is None:
            return
        for index in range(self.run_tree.topLevelItemCount()):
            item = self.run_tree.topLevelItem(index)
            if item.data(0, Qt.UserRole) == str(run_dir):
                self.run_tree.setCurrentItem(item)
                self.run_tree.scrollToItem(item)
                return

    def closeEvent(self, event) -> None:
        running = self.queue.running
        if running is not None:
            answer = QMessageBox.question(
                self,
                "A run is still going",
                f"{running.title} is still running. Quitting will cancel it.\n\nQuit anyway?",
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self.queue.shutdown()
        super().closeEvent(event)


def run_app(workspace: Workspace | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(SETTINGS_APP)
    app.setOrganizationName(SETTINGS_ORG)
    app.setStyleSheet(STYLE)

    if workspace is None:
        remembered = QSettings(SETTINGS_ORG, SETTINGS_APP).value(WORKSPACE_KEY)
        workspace = resolve(remembered=Path(remembered) if remembered else None)

    window = MainWindow(workspace)
    window.show()
    # Ask once, on screen, rather than opening an inexplicably empty window —
    # this is the normal state for a freshly double-clicked .exe.
    if not workspace.is_usable:
        window.choose_workspace()
    return app.exec()
