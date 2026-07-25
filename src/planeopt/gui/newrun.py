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
from .jobs import Job


FIELD_WIDTH = 150  # every value field the same width, so the column reads as a column


def _spin(minimum: float, maximum: float, step: float, decimals: int, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    box.setFixedWidth(FIELD_WIDTH)
    return box


class NewRunDialog(QDialog):
    def __init__(
        self,
        aircraft_dir: Path,
        missions_dir: Path,
        runs_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New run")
        self.setMinimumWidth(520)
        self._aircraft_dir = aircraft_dir
        self._missions_dir = missions_dir
        self._runs_dir = runs_dir

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # --- aircraft ---
        aircraft_box = QGroupBox("Aircraft")
        aircraft_form = QFormLayout(aircraft_box)
        self.aircraft = QComboBox()
        for path in sorted(p for p in aircraft_dir.iterdir() if (p / "aircraft.py").is_file()):
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
        for path in sorted(missions_dir.glob("*.py")):
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
        options.addStretch(1)
        mode_layout.addLayout(options)
        self.mode_optimize.toggled.connect(self._update_mode)
        layout.addWidget(mode_box)

        warning = QLabel(
            "A solve peaks near 13 GB of memory. Runs execute one at a time."
        )
        warning.setStyleSheet("color:#9a9aa0; font-size:11px;")
        warning.setFrameShape(QFrame.NoFrame)
        layout.addWidget(warning)

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
        for widget in (self.multistart, self.flatness):
            widget.setEnabled(self.mode_optimize.isChecked())

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
        )
