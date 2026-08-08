"""The live solve viewer — M5.4, `docs/LIVE_VIEWER_PLAN.md` section 4.2.

A popup that shows the aeroplane the optimizer is currently shaping: geometry
morphing every IPOPT iterate, a coloured and fully annotated frame every time a
member converges. It reads gzip'd JSON frames off disk and renders them with
`render3d`; it never imports aerosandbox, CasADi or an aircraft module, and
closing it cannot touch the run.

**The transport is a watched directory, not a pipe.** That one choice is what
makes the same window serve four cases with no protocol: a live run, a CLI run
started in a terminal, a run that was paused and resumed, and a FINISHED run
being scrubbed months later out of `<run_dir>/frames/`. Nothing has to be
parsed, and a frame that exists is a frame that is complete (the writer lands
them with `os.replace`).

Watching is a `QFileSystemWatcher` **and** a slow poll. The watcher is the fast
path and the poll is the one that actually works: this project's runs directory
lives on `/mnt/c`, a 9p mount into the Windows filesystem, where inotify does
not fire for writes made by another process.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..liveframe import frame_paths, header_text, read_frame, read_view, write_view
from . import render3d

#: What the view picker shows once the camera has been orbited off every preset.
#: A combo that keeps naming "Plan" while you look at the model from an angle is
#: worse than no combo — it is a label that is wrong.
CUSTOM_VIEW = "Custom"

#: How often the directory is re-listed when the watcher says nothing. Frames
#: arrive every second or two at most, so this is a tail and not a spin: it is a
#: `readdir` of a few thousand entries, microseconds either way.
POLL_MS = 900

#: Degrees of orbit per pixel dragged, and the wheel's zoom factor per notch.
ORBIT_PER_PIXEL = 0.4
ZOOM_PER_NOTCH = 1.15


class ModelView(QWidget):
    """The 3D area. Owns the camera; the window owns everything else."""

    camera_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.state = render3d.RenderState()
        #: Where a double-click (and the Reset gesture) comes back to. The view
        #: chosen for this run, not a global default: "reset" means "back to how
        #: this opened", and for a run queued with a plan view, snapping to a
        #: three-quarter corner would be the surprise, not the fix.
        self.home = render3d.DEFAULT_CAMERA
        self.frame: dict | None = None
        self.message = "Waiting for the first frame…"
        self.setMinimumSize(520, 380)
        self.setMouseTracking(False)
        self._drag: tuple[QPointF, bool] | None = None

    def show_frame(self, frame: dict | None) -> None:
        self.frame = frame
        if frame is not None:
            # Fold the frame into the camera fit and colour range NOW rather
            # than at the next paint. Those are properties of the data, not of
            # the painting, and a window that is minimised or occluded still has
            # to have seen every frame — otherwise restoring it re-scales the
            # model against whichever frames happened to be painted. `prepare`
            # is idempotent, so the paint below repeating it costs nothing.
            self.state.prepare(frame)
        self.update()

    def reset_camera(self) -> None:
        self.set_camera(self.home)

    def set_camera(self, camera) -> None:
        self.state.camera = camera
        # The fit goes too: it only ever grows, so a zoom that was fitted around
        # a wide three-quarter view would leave a plan view floating in a box
        # sized for a different projection.
        self.state.fit.reset()
        if self.frame is not None:
            self.state.prepare(self.frame)
        self.camera_changed.emit()
        self.update()

    # --- painting -------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt naming
        painter = QPainter(self)
        rect = QRectF(self.rect())
        if self.frame is None:
            painter.fillRect(rect, render3d.BACKGROUND)
            painter.setFont(render3d.mono_font(10))
            painter.setPen(render3d.TEXT_DIM)
            painter.drawText(rect, Qt.AlignCenter, self.message)
            return
        render3d.render_frame(painter, rect, self.frame, self.state)

    # --- camera control -------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pan = bool(event.buttons() & Qt.MiddleButton) or bool(
            event.modifiers() & Qt.ShiftModifier
        )
        self._drag = (QPointF(event.position()), pan)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            return
        last, pan = self._drag
        delta = event.position() - last
        self._drag = (QPointF(event.position()), pan)
        if pan:
            self.state.camera = self.state.camera.panned(delta.x(), delta.y())
        else:
            self.state.camera = self.state.camera.orbit(
                delta.x() * ORBIT_PER_PIXEL, delta.y() * ORBIT_PER_PIXEL
            )
        self.camera_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_camera()

    def wheelEvent(self, event) -> None:  # noqa: N802
        notches = event.angleDelta().y() / 120.0
        if notches:
            self.state.camera = self.state.camera.zoomed(ZOOM_PER_NOTCH**notches)
            self.camera_changed.emit()
            self.update()


class LiveViewWindow(QWidget):
    """The popup. One instance per application, retargeted at each run.

    Retargeted rather than re-created because the camera, the zoom and the
    chosen scalar are things the user set up and should not have to set up again
    for the next member, let alone the next run.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("planeopt — live solve")
        self.setWindowFlag(Qt.Window, True)
        self.resize(1120, 760)

        self.directory: Path | None = None
        self.run_dir: Path | None = None
        self._paths: list[Path] = []
        #: True while the code, not the user, is moving the slider. Without it
        #: every arriving frame would look like a drag and turn following off.
        self._syncing = False

        self.view = ModelView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(self._build_header())
        layout.addWidget(self.view, 1)
        layout.addLayout(self._build_footer())

        # The combo reports the camera rather than owning it, so every route to
        # a camera change — a preset, a drag, a wheel, a double-click, the view
        # stored for a run — lands in the same place and none of them can leave
        # the label naming a view nobody is looking at.
        self.view.camera_changed.connect(self._sync_view_preset)
        self._sync_view_preset()

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _: self.rescan())
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.rescan)

    # --- construction ---------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Colour by"))
        self.scalar = QComboBox()
        for name, label, unit in render3d.SCALARS:
            self.scalar.addItem(f"{label} [{unit}]" if unit else label, name)
        self.scalar.currentIndexChanged.connect(self._scalar_changed)
        self.scalar.setToolTip(
            "The in-loop model is a lifting line with one chordwise panel, so "
            "there is no chordwise pressure distribution and no Cp to plot. "
            "These are what a spanwise strip actually has. Stall margin is "
            "cl/cl_max at the local Reynolds number — 1.0 is the section limit, "
            "on a fixed scale so the colour means the same thing every frame. It "
            "covers the main wing only; the tail and winglets use a different "
            "airfoil and are left grey rather than given a borrowed limit."
        )
        row.addWidget(self.scalar)

        row.addSpacing(12)
        self.streamlines = QCheckBox("Wake")
        self.streamlines.setChecked(True)
        self.streamlines.toggled.connect(self._overlays_changed)
        self.streamlines.setToolTip(
            "Streamlines traced downstream from the trailing edge through the "
            "lifting line's own induced-velocity field — the same field the "
            "forces are read from. Candidate frames only; an iterate has no "
            "solved circulation to trace through."
        )
        row.addWidget(self.streamlines)

        self.lift_curve = QCheckBox("Lift dist")
        self.lift_curve.setChecked(False)
        self.lift_curve.toggled.connect(self._overlays_changed)
        self.lift_curve.setToolTip(
            "Spanwise lift distribution over the wing, against the elliptical "
            "distribution of the same total lift and span. How much the taper "
            "and the washout actually cost, drawn on the aeroplane."
        )
        row.addWidget(self.lift_curve)

        row.addSpacing(12)
        row.addWidget(QLabel("View"))
        self.view_preset = QComboBox()
        for name, (label, _) in render3d.VIEW_PRESETS.items():
            self.view_preset.addItem(label, name)
        # Last, and only ever SELECTED by the code — picking "Custom" from the
        # list would have to mean something, and there is nothing for it to mean.
        self.view_preset.addItem(CUSTOM_VIEW, None)
        self.view_preset.activated.connect(self._preset_chosen)
        self.view_preset.setToolTip(
            "Snap the camera to a standard view. Drag to orbit from there, "
            "wheel to zoom, shift-drag or middle-drag to pan; double-click to "
            "come back. This is the view on screen only — the timelapse uses "
            "the one chosen for the run until “Use for timelapse” says otherwise."
        )
        row.addWidget(self.view_preset)

        row.addSpacing(12)
        self.follow = QCheckBox("Follow latest")
        self.follow.setChecked(True)
        self.follow.toggled.connect(self._follow_toggled)
        self.follow.setToolTip(
            "Off freezes the view on one frame and enables the slider, so you "
            "can go back over what the solver did. Frames already on disk are "
            "all scrubbable; the run carries on either way."
        )
        row.addWidget(self.follow)

        row.addStretch(1)
        self.adopt_button = QPushButton("Use for timelapse")
        self.adopt_button.clicked.connect(self._adopt_view)
        self.adopt_button.setToolTip(
            "Record the camera you are looking at now as this run's timelapse "
            "view, replacing the one chosen when the run was queued. Saved "
            "beside the frames, so it travels into the finished run."
        )
        row.addWidget(self.adopt_button)

        self.timelapse_button = QPushButton("Render timelapse…")
        self.timelapse_button.clicked.connect(self._render_timelapse)
        self.timelapse_button.setToolTip(
            "Replay every frame on disk into PNGs (and an MP4 if ffmpeg is "
            "installed) through this same renderer. Runs as a separate process."
        )
        row.addWidget(self.timelapse_button)
        return row

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        # Always live, never greyed. It doubles as the run's progress bar, and
        # dragging it is the obvious way to say "stop following" — which is what
        # it does, rather than sitting disabled until a checkbox releases it.
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setToolTip(
            "Scrub back through the frames on disk. Dragging turns off "
            "“Follow latest”; tick it again to jump back to the newest."
        )
        self.slider.valueChanged.connect(self._slider_moved)
        row.addWidget(self.slider, 1)
        self.status = QLabel("—")
        self.status.setStyleSheet("color:#9a9aa0; font-size:11px;")
        row.addWidget(self.status)
        return row

    # --- targeting ------------------------------------------------------

    def watch(self, directory, run_dir=None, live: bool = True) -> None:
        """Point the window at a frame directory and show it.

        `run_dir` is where the frames will END UP when the run finishes
        (`liveframe.relocate` moves them there), so the window can follow them
        instead of going blank the moment the run succeeds.
        """
        directory = Path(directory)
        if directory != self.directory:
            self.view.state.fit.reset()
            self.view.state.color_range = render3d.ColorRange()
            self._paths = []
            self.view.show_frame(None)
            # A NEW run opens at the view that run was queued with. Retargeting
            # otherwise preserves what the user set up (the docstring above), and
            # this is not an exception to that: the stored view IS something they
            # set up, for this run, and it is the only camera in the app that
            # anyone chose in advance.
            self._apply_stored_view(directory)
        self.directory = directory
        self.run_dir = Path(run_dir) if run_dir else None
        self.view.message = (
            "Waiting for the first frame…" if live
            else f"No frames in {directory.name}"
        )
        for old in self._watcher.directories():
            self._watcher.removePath(old)
        if directory.is_dir():
            self._watcher.addPath(str(directory))
        self._timer.start() if live else self._timer.stop()
        self.rescan()

    def stop_following(self) -> None:
        """The run is over: keep scrubbing what is there, stop polling."""
        self._timer.stop()

    # --- frame stream ---------------------------------------------------

    def rescan(self) -> None:
        if self.directory is None:
            return
        paths = frame_paths(self.directory)
        if not paths and self.run_dir is not None and (self.run_dir / "frames").is_dir():
            # The run finished while we were watching and `liveframe.relocate`
            # moved the frames into the run directory. Follow them rather than
            # showing an empty window over a directory that no longer exists.
            self.watch(self.run_dir / "frames", self.run_dir, live=False)
            return
        if len(paths) == len(self._paths):
            return
        self._paths = paths
        self._syncing = True
        try:
            self.slider.setMaximum(max(0, len(paths) - 1))
            if self.follow.isChecked():
                self.slider.setValue(max(0, len(paths) - 1))
        finally:
            self._syncing = False
        if self.follow.isChecked():
            self._show_index(len(paths) - 1)
        self._update_status()

    def _show_index(self, index: int) -> None:
        if not (0 <= index < len(self._paths)):
            return
        path = self._paths[index]
        try:
            frame = read_frame(path)
        except (OSError, ValueError) as e:
            # One unreadable frame is a frame, not a viewer failure.
            self.status.setText(f"{path.name} unreadable ({e})")
            return
        self.view.show_frame(frame)
        self._update_status()

    def _update_status(self) -> None:
        total = len(self._paths)
        index = self.slider.value() + 1 if total else 0
        # A finished run's frames live in `<run>/frames/`, and "frames" names
        # nothing — say which run it is.
        where = "—"
        if self.directory is not None:
            where = (
                self.directory.parent.name if self.directory.name == "frames"
                else self.directory.name
            )
        frame = self.view.frame
        progress = header_text(frame) if frame else "waiting for a member"
        self.status.setText(
            f"total frame {index}/{total}   ·   {progress}   ·   {where}"
        )

    # --- controls -------------------------------------------------------

    def _scalar_changed(self) -> None:
        self.view.state.scalar = self.scalar.currentData()
        # The new scalar has its own units, so the old range means nothing.
        self.view.state.color_range = render3d.ColorRange()
        self._show_index(self.slider.value())

    # --- the timelapse view ---------------------------------------------

    def _apply_stored_view(self, directory: Path) -> None:
        """Open at the camera recorded for this run, if there is one."""
        from dataclasses import replace

        stored = read_view(directory) or {}
        camera = render3d.camera_from_view(stored.get("view"))
        camera = replace(
            camera,
            **{
                key: float(stored[key])
                for key in ("yaw_deg", "pitch_deg", "zoom", "pan_x", "pan_y")
                if isinstance(stored.get(key), (int, float))
            },
        )
        self.view.home = camera
        self.view.set_camera(camera)

    def _preset_chosen(self, index: int) -> None:
        name = self.view_preset.itemData(index)
        if name is None:  # the "Custom" row — it reports, it does not command
            self._sync_view_preset()
            return
        self.view.set_camera(render3d.camera_from_view(name))

    def _sync_view_preset(self) -> None:
        """Name the camera in the combo, or say Custom. Never emits a change."""
        name = render3d.view_of(self.view.state.camera)
        index = self.view_preset.findData(name) if name else -1
        if index < 0:
            index = self.view_preset.count() - 1  # Custom
        self.view_preset.blockSignals(True)
        try:
            self.view_preset.setCurrentIndex(index)
        finally:
            self.view_preset.blockSignals(False)

    def _adopt_view(self) -> None:
        """Record the camera on screen as this run's timelapse view."""
        if self.directory is None:
            return
        camera = self.view.state.camera
        written = write_view(self.directory, {
            "view": render3d.view_of(camera),
            "yaw_deg": camera.yaw_deg,
            "pitch_deg": camera.pitch_deg,
            "zoom": camera.zoom,
            "pan_x": camera.pan_x,
            "pan_y": camera.pan_y,
        })
        if written is None:
            self.status.setText(f"could not record the timelapse view in {self.directory}")
            return
        self.view.home = camera
        named = render3d.view_of(camera)
        label = render3d.VIEW_PRESETS[named][0] if named else "this custom angle"
        self.status.setText(f"timelapse view set to {label}")

    def _overlays_changed(self) -> None:
        # A repaint, not a reload: both overlays are already in the frame the
        # view is holding, so toggling one is free and cannot lose the position
        # in a scrubbed run.
        self.view.state.show_streamlines = self.streamlines.isChecked()
        self.view.state.show_lift = self.lift_curve.isChecked()
        self.view.update()

    def _follow_toggled(self, following: bool) -> None:
        if following and self._paths:
            self._syncing = True
            try:
                self.slider.setValue(len(self._paths) - 1)
            finally:
                self._syncing = False
            self._show_index(len(self._paths) - 1)

    def _slider_moved(self, value: int) -> None:
        if self._syncing:
            return
        # Moving the slider IS the request to stop following. One gesture, and
        # the checkbox reports what happened rather than gating it.
        self.follow.setChecked(False)
        self._show_index(value)

    def _render_timelapse(self) -> None:
        """Shell out to `planeopt timelapse` — never render in-process.

        Five thousand frames at 1080p is minutes of drawing, and doing it on the
        GUI thread would freeze the window that is showing a running solve.
        """
        from PySide6.QtCore import QProcess

        from .jobs import planeopt_command

        if self.directory is None:
            return
        program, args = planeopt_command(["timelapse", str(self.directory)])
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(args)
        process.setProcessChannelMode(QProcess.MergedChannels)

        def show_last_line() -> None:
            # Read ONCE — `readAllStandardOutput` drains the buffer, so a second
            # call in the same slot returns nothing.
            text = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
            for line in reversed(text.splitlines()):
                if line.strip():
                    self.status.setText(line.strip()[:120])
                    return

        process.readyReadStandardOutput.connect(show_last_line)
        process.start()
        self.status.setText("rendering timelapse…")
