"""The New Run dialog: pick an aircraft, edit the mission, choose the mode.

The mission half is a real form because a MissionSpec is pure data. The aircraft
half is a picker, not an editor — an aircraft definition is executable code with
a symbolic-safety contract (EXECUTION_PLAN §3 rule 3), and a form that pretended
otherwise would be lying about what it can guarantee.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ..mission import OBJECTIVES
from ..types import MissionSpec
from . import missionfile
from planeopt import memory

from .jobs import Job
from .workspace import Workspace


FIELD_WIDTH = 150  # every value field the same width, so the column reads as a column
#: Must equal planeopt.solve.SOLVE_TIMEOUT_MIN — see the spin box below for why
#: it is copied rather than imported. tests/test_gui.py holds them together.
SOLVE_TIMEOUT_MIN_DEFAULT = 30


def _spin(minimum: float, maximum: float, step: float, decimals: int, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    box.setFixedWidth(FIELD_WIDTH)
    return box


class NewRunDialog(QDialog):
    def __init__(self, workspace: Workspace, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New run")
        self.setMinimumWidth(520)
        self._workspace = workspace
        self._missions_dir = workspace.missions_dir
        self._runs_dir = workspace.runs_dir

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # --- aircraft ---
        aircraft_box = QGroupBox("Aircraft")
        aircraft_form = QFormLayout(aircraft_box)
        self.aircraft = QComboBox()
        # workspace.aircraft_packages() tolerates a missing directory: a packaged
        # app is routinely pointed at a folder that has none yet.
        for path in workspace.aircraft_packages():
            self.aircraft.addItem(path.name, path)
        aircraft_form.addRow("Definition", self.aircraft)
        note = QLabel(
            "Aircraft definitions are Python modules — edit "
            "<code>aircraft/&lt;name&gt;/aircraft.py</code> to change the airframe."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9a9aa0; font-size:11px;")
        aircraft_form.addRow(note)
        layout.addWidget(aircraft_box)

        # --- mission ---
        mission_box = QGroupBox("Mission")
        mission_form = QFormLayout(mission_box)
        # Fields keep their own width instead of stretching, so the rows with a
        # trailing checkbox line up with the rows without one.
        mission_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        preset_row = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.setFixedWidth(FIELD_WIDTH * 2)
        self.preset.addItem("(new mission)", None)
        for path in workspace.missions():
            self.preset.addItem(path.stem, path)
        self.preset.currentIndexChanged.connect(self._load_preset)
        preset_row.addWidget(self.preset, 1)
        mission_form.addRow("Start from", preset_row)

        self.name = QLineEdit("my_mission")
        self.name.setFixedWidth(FIELD_WIDTH * 2)
        mission_form.addRow("Name", self.name)

        self.objective = QComboBox()
        self.objective.setFixedWidth(FIELD_WIDTH * 2)
        for key, objective in OBJECTIVES.items():
            # "endurance — maximize [min]", not "endurance — min (maximize)":
            # the unit `min` next to a direction reads as "minimum".
            self.objective.addItem(f"{key} — {objective.direction} [{objective.units}]", key)
        mission_form.addRow("Objective", self.objective)

        self.v_wind = _spin(0, 30, 0.5, 1, " m/s")
        mission_form.addRow("Wind speed", self.v_wind)

        self.margin = _spin(0, 30, 0.5, 1, " m/s")
        mission_form.addRow("Penetration margin", self.margin)

        self.v_min_label = QLabel()
        self.v_min_label.setStyleSheet("color:#9a9aa0; font-size:11px;")
        mission_form.addRow("", self.v_min_label)
        self.v_wind.valueChanged.connect(self._update_v_min)
        self.margin.valueChanged.connect(self._update_v_min)

        self.v_stall = _spin(0, 30, 0.5, 1, " m/s")
        self.v_stall_enabled = QCheckBox("limit stall speed")
        self.v_stall_enabled.setChecked(True)
        self.v_stall_enabled.toggled.connect(self.v_stall.setEnabled)
        stall_row = QHBoxLayout()
        stall_row.addWidget(self.v_stall)
        stall_row.addWidget(self.v_stall_enabled)
        stall_row.addStretch(1)
        mission_form.addRow("Max stall speed", stall_row)

        self.sm_low = _spin(-0.5, 0.5, 0.01, 3, "")
        self.sm_high = _spin(-0.5, 0.5, 0.01, 3, "")
        sm_row = QHBoxLayout()
        sm_row.addWidget(self.sm_low)
        sm_row.addWidget(QLabel("to"))
        sm_row.addWidget(self.sm_high)
        sm_row.addStretch(1)
        mission_form.addRow("Static margin", sm_row)

        self.ballast = _spin(0, 2000, 5, 0, " g")
        self.ballast_enabled = QCheckBox("allow ballast")
        self.ballast_enabled.setChecked(True)
        self.ballast_enabled.toggled.connect(self.ballast.setEnabled)
        ballast_row = QHBoxLayout()
        ballast_row.addWidget(self.ballast)
        ballast_row.addWidget(self.ballast_enabled)
        ballast_row.addStretch(1)
        mission_form.addRow("Max ballast", ballast_row)

        layout.addWidget(mission_box)

        # --- mode ---
        mode_box = QGroupBox("Mode")
        mode_layout = QVBoxLayout(mode_box)
        self.mode_optimize = QRadioButton("Optimize — full NLP, studies and re-solve battery (hours)")
        self.mode_evaluate = QRadioButton("Evaluate — fixed design at the declared defaults (about a minute)")
        self.mode_optimize.setChecked(True)
        mode_layout.addWidget(self.mode_optimize)
        mode_layout.addWidget(self.mode_evaluate)

        options = QHBoxLayout()
        options.addWidget(QLabel("Multistart"))
        self.multistart = QSpinBox()
        self.multistart.setRange(1, 12)
        self.multistart.setValue(3)
        options.addWidget(self.multistart)
        self.flatness = QCheckBox("span flatness sweep")
        self.flatness.setChecked(True)
        options.addWidget(self.flatness)
        options.addSpacing(16)
        # Per-solve wall-clock ceiling. A battery is a fixed set of independent
        # solves, so one that diverges has no natural end and can quietly own the
        # whole run — a single flatness member once took 172 minutes and failed
        # anyway. Exposed because "how long am I willing to spend finding out
        # this member does not converge?" is the user's call, not the model's.
        options.addWidget(QLabel("Solve timeout"))
        self.solve_timeout = QSpinBox()
        self.solve_timeout.setRange(5, 240)
        # Literal, not an import of planeopt.solve: that module pulls in
        # aerosandbox, and paying seconds of import cost to fill in a spin box
        # would show up as a stalled dialog. A test pins the two together.
        self.solve_timeout.setValue(SOLVE_TIMEOUT_MIN_DEFAULT)
        self.solve_timeout.setSuffix(" min")
        self.solve_timeout.setToolTip(
            "Wall-clock ceiling for ONE member solve. A converging solve takes "
            "4-10 minutes. A member that hits the cap is recorded as "
            "Maximum_WallTime_Exceeded and the batch carries on."
        )
        options.addWidget(self.solve_timeout)
        options.addStretch(1)
        mode_layout.addLayout(options)

        # --- memory budget ---
        # RAM, not CPU, is what limits this app: a solve is single-core and peaks
        # near 13 GB, so the budget does not make one solve faster — it decides
        # how many independent solves in a batch run side by side. The dial is
        # therefore phrased as memory (what the user actually owns) rather than
        # as a worker count (an implementation detail they would have to convert).
        mem_row = QHBoxLayout()
        self.memory_enabled = QCheckBox("Dedicate memory")
        mem_row.addWidget(self.memory_enabled)
        total_gb, _ = memory.machine_ram()
        ceiling = max(8.0, total_gb + memory.swap_gb() - memory.RESERVE_GB)
        self.memory_budget = _spin(4.0, round(ceiling), 1.0, 0, " GB")
        # narrower than the mission fields: this row lives in the Mode box, whose
        # controls are compact, and a 150 px box for "26 GB" reads as a gap
        self.memory_budget.setFixedWidth(90)
        self.memory_budget.setValue(min(round(ceiling), 26.0))
        mem_row.addWidget(self.memory_budget)
        mem_row.addStretch(1)
        mode_layout.addLayout(mem_row)

        self.memory_note = QLabel()
        self.memory_note.setStyleSheet("color:#9a9aa0; font-size:11px;")
        self.memory_note.setWordWrap(True)
        self.memory_note.setFrameShape(QFrame.NoFrame)
        mode_layout.addWidget(self.memory_note)

        self.memory_enabled.toggled.connect(self._update_mode)
        self.memory_budget.valueChanged.connect(self._update_memory_note)
        self.mode_optimize.toggled.connect(self._update_mode)
        layout.addWidget(mode_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Queue run")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        for role in (QDialogButtonBox.Ok, QDialogButtonBox.Cancel):
            buttons.button(role).setIcon(QIcon())  # platform icons clash with this theme
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Start from the sample mission when there is one — the common case is
        # "same mission, one value changed".
        if self.preset.count() > 1:
            self.preset.setCurrentIndex(1)
        else:
            self._apply(MissionSpec(name="my_mission", objective="endurance"))
        self._update_mode()

    # --- form <-> MissionSpec --------------------------------------------

    def _update_v_min(self) -> None:
        self.v_min_label.setText(
            f"minimum airspeed = {self.v_wind.value() + self.margin.value():.1f} m/s"
        )

    def _update_mode(self) -> None:
        optimizing = self.mode_optimize.isChecked()
        for widget in (self.multistart, self.flatness, self.solve_timeout):
            widget.setEnabled(optimizing)
        # Concurrency only exists inside an optimize battery — an evaluation is
        # a single pass, so offering to spread it over memory would be a lie.
        self.memory_enabled.setEnabled(optimizing)
        self.memory_budget.setEnabled(optimizing and self.memory_enabled.isChecked())
        self._update_memory_note()

    def _update_memory_note(self) -> None:
        total_gb, avail_gb = memory.machine_ram()
        measured = memory.observed_peak_gb(self._runs_dir)
        per = measured or memory.DEFAULT_PER_SOLVE_GB
        source = "measured" if measured else "estimated"
        have = f"{avail_gb:.0f} GB free of {total_gb:.0f} GB" if total_gb else "memory unknown"

        if not (self.mode_optimize.isChecked() and self.memory_enabled.isChecked()):
            self.memory_note.setText(
                f"{have}. A solve peaks near {per:.0f} GB ({source}) and uses one core; "
                "runs execute one at a time."
            )
            return
        # The full reason string is for the run log; the dialog gets the number
        # and, only when it applies, the one caveat that changes what the user
        # should do.
        budget = self.memory_budget.value()
        width, _ = memory.plan_parallel(budget, per_solve_gb=measured)
        plural = "" if width == 1 else "s"
        text = f"{have}. {width} concurrent solve{plural} at ~{per:.0f} GB each ({source})."
        if not memory.parallel_supported():
            text += " This platform cannot run solves concurrently, so the budget has no effect."
        elif avail_gb and budget > avail_gb - memory.RESERVE_GB:
            text += " More than is free right now — this relies on swap."
        self.memory_note.setText(text)

    def _load_preset(self) -> None:
        path = self.preset.currentData()
        if path is None:
            return
        try:
            self._apply(missionfile.load(Path(path)))
        except Exception as e:  # noqa: BLE001 — a bad file must not kill the dialog
            QMessageBox.warning(self, "Could not read mission", f"{path}\n\n{e}")

    def _apply(self, mission: MissionSpec) -> None:
        self.name.setText(mission.name)
        index = self.objective.findData(mission.objective)
        if index >= 0:
            self.objective.setCurrentIndex(index)
        self.v_wind.setValue(mission.v_wind_ms)
        self.margin.setValue(mission.penetration_margin_ms)
        self.v_stall_enabled.setChecked(mission.v_stall_max_ms is not None)
        self.v_stall.setValue(mission.v_stall_max_ms or 8.0)
        self.sm_low.setValue(mission.static_margin_range[0])
        self.sm_high.setValue(mission.static_margin_range[1])
        self.ballast_enabled.setChecked(mission.ballast_max_kg is not None)
        self.ballast.setValue((mission.ballast_max_kg or 0.0) * 1000.0)
        self._update_v_min()

    def mission(self) -> MissionSpec:
        return MissionSpec(
            name=self.name.text().strip() or "mission",
            objective=self.objective.currentData(),
            v_wind_ms=self.v_wind.value(),
            penetration_margin_ms=self.margin.value(),
            v_stall_max_ms=self.v_stall.value() if self.v_stall_enabled.isChecked() else None,
            static_margin_range=(self.sm_low.value(), self.sm_high.value()),
            ballast_max_kg=self.ballast.value() / 1000.0 if self.ballast_enabled.isChecked() else None,
            notes="written by the planeopt GUI",
        )

    def accept(self) -> None:
        if self.sm_low.value() >= self.sm_high.value():
            QMessageBox.warning(
                self, "Static margin", "The lower bound must be below the upper bound."
            )
            return
        if self.aircraft.currentData() is None:
            QMessageBox.warning(self, "Aircraft", "No aircraft definitions found.")
            return

        # Starting from an existing mission pre-fills its name, so queueing would
        # quietly rewrite the file it was loaded from. Only ask when the content
        # would actually change — re-running an unedited mission is not a hazard.
        target = self._missions_dir / f"{self.mission().name}.py"
        if target.exists() and target.read_text(encoding="utf-8") != missionfile.render(self.mission()):
            answer = QMessageBox.question(
                self,
                "Overwrite mission file?",
                f"{target.name} already exists and your changes differ from it.\n\n"
                "Overwrite it, or go back and give this mission a new name?",
                QMessageBox.Save | QMessageBox.Cancel,
            )
            if answer != QMessageBox.Save:
                self.name.setFocus()
                self.name.selectAll()
                return
        super().accept()

    def job(self) -> Job:
        """Write the mission module, then describe the run to queue."""
        mission = self.mission()
        path = missionfile.save(mission, self._missions_dir / f"{mission.name}.py")
        return Job(
            mission=path,
            aircraft=Path(self.aircraft.currentData()),
            runs_dir=self._runs_dir,
            optimize=self.mode_optimize.isChecked(),
            multistart=self.multistart.value(),
            flatness=self.flatness.isChecked(),
            solve_timeout_min=float(self.solve_timeout.value()),
            # Every optimize job gets a checkpoint directory and a pause
            # sentinel, unasked. They cost nothing when unused, and the
            # alternative is a Pause button that is greyed out exactly when
            # someone finally wants it, four hours into a battery.
            checkpoint_dir=(
                self._runs_dir / "_checkpoints" / mission.name
                if self.mode_optimize.isChecked() else None
            ),
            pause_file=(
                self._runs_dir / "_checkpoints" / f"{mission.name}.PAUSE"
                if self.mode_optimize.isChecked() else None
            ),
            memory_budget_gb=(
                self.memory_budget.value()
                if self.mode_optimize.isChecked() and self.memory_enabled.isChecked()
                else None
            ),
        )
