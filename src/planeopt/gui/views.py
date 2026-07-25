"""Right-hand panes: one run in detail, or several side by side.

Both read run.json only (EXECUTION_PLAN M5) — no library calls, no re-solving,
so browsing is instant and works on runs produced by any earlier version.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import runindex
from .runindex import RunSummary


MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "monospace"]


def _mono(size: int = 0, bold: bool = False) -> QFont:
    # setFamilies, not QFont("a, b, c"): Qt treats a comma-joined string as one
    # family name and silently falls back to the UI font when it does not exist.
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setStyleHint(QFont.Monospace)
    if size:
        font.setPointSize(size)
    font.setBold(bold)
    return font


def _fmt(value, spec: str = ".3f", suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):{spec}}{suffix}"
    except (TypeError, ValueError):
        return str(value)


class Chip(QLabel):
    """A small pill for a constraint name."""

    def __init__(self, text: str, kind: str = "neutral") -> None:
        super().__init__(text)
        colors = {
            "active": ("#1f3a5f", "#8ab4f8"),
            "violated": ("#4a1f1f", "#f28b82"),
            "neutral": ("#2a2a2e", "#c8c8cc"),
        }
        bg, fg = colors[kind]
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:9px;"
            "padding:2px 9px; font-size:11px;"
        )
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


def _fixed_height(widget: QWidget) -> QWidget:
    """Never let this widget be compressed below the height its text needs.

    Inside a resizable QScrollArea, children with the default Preferred vertical
    policy are shrunk toward their minimum when the content is taller than the
    viewport — the text clips instead of the view scrolling. Fixing the vertical
    policy makes minimumSizeHint == sizeHint, so the scroll area scrolls.
    """
    widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
    return widget


class MetricGrid(QWidget):
    """Label/value pairs in two columns, values monospaced so they line up."""

    def __init__(self) -> None:
        super().__init__()
        _fixed_height(self)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(6)
        self._row = 0

    def add(self, label: str, value: str, column: int = 0) -> None:
        name = QLabel(label)
        name.setStyleSheet("color:#9a9aa0; font-size:11px;")
        val = QLabel(value)
        val.setFont(_mono())
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row = self._row if column == 0 else self._row - 1
        self._grid.addWidget(name, row, column * 2)
        self._grid.addWidget(val, row, column * 2 + 1)
        if column == 0:
            self._row += 1


def _section(title: str) -> QLabel:
    label = QLabel(title.upper())
    label.setStyleSheet(
        "color:#7a7a80; font-size:10px; font-weight:600; letter-spacing:1px;"
        "margin-top:14px;"
    )
    return _fixed_height(label)


class DetailView(QScrollArea):
    """Everything worth knowing about one run, without opening the report."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._body = QWidget()
        self.setWidget(self._body)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(20, 16, 20, 20)
        self._layout.setSpacing(4)
        self.show_placeholder("Select a run to see its details.")

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # setParent(None) first: deleteLater alone defers destruction, so
                # the old widget keeps painting over the new content until the
                # event loop gets around to it.
                widget.setParent(None)
                widget.deleteLater()

    def show_placeholder(self, text: str) -> None:
        self._clear()
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color:#6a6a70; font-size:13px;")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def show_run(self, summary: RunSummary) -> None:
        self._clear()
        if summary.error:
            self.show_placeholder(f"{summary.stamp}\n\n{summary.error}")
            return

        title = QLabel(summary.aircraft or summary.stamp)
        title.setStyleSheet("font-size:17px; font-weight:600;")
        self._layout.addWidget(_fixed_height(title))

        subtitle = QLabel(
            f"{summary.mission} · {summary.created or summary.stamp}"
            f" · {'optimized' if summary.optimized else 'evaluation'}"
        )
        subtitle.setStyleSheet("color:#9a9aa0; font-size:12px;")
        self._layout.addWidget(_fixed_height(subtitle))

        headline = QLabel(summary.objective_text)
        headline.setFont(_mono(22, bold=True))
        headline.setStyleSheet("color:#8ab4f8; margin-top:10px;")
        self._layout.addWidget(_fixed_height(headline))
        objective_label = QLabel(summary.objective)
        objective_label.setStyleSheet("color:#9a9aa0; font-size:11px;")
        self._layout.addWidget(_fixed_height(objective_label))

        data = {}
        try:
            data = runindex.load_full(summary.path)
        except (OSError, ValueError):
            pass
        best = (data.get("performance") or {}).get("best") or {}
        masses = data.get("masses") or {}
        geometry = data.get("geometry") or {}

        self._layout.addWidget(_section("flight point"))
        grid = MetricGrid()
        grid.add("cruise speed", _fmt(summary.v_ms, ".2f", " m/s"))
        grid.add("L/D", _fmt(best.get("L_over_D"), ".2f"), column=1)
        grid.add("bus power", _fmt(best.get("P_elec_w"), ".1f", " W"))
        grid.add("CL", _fmt(best.get("CL"), ".3f"), column=1)
        grid.add("alpha", _fmt(best.get("alpha_deg"), ".2f", "°"))
        grid.add("rpm", _fmt(best.get("rpm"), ".0f"), column=1)
        self._layout.addWidget(grid)

        self._layout.addWidget(_section("geometry & mass"))
        grid = MetricGrid()
        grid.add("span", _fmt(geometry.get("span_m"), ".3f", " m"))
        grid.add("projected span", _fmt(geometry.get("span_projected_m"), ".3f", " m"), column=1)
        grid.add("wing area", _fmt(geometry.get("area_m2"), ".4f", " m²"))
        grid.add("aspect ratio", _fmt(geometry.get("aspect_ratio"), ".2f"), column=1)
        grid.add("AUW", _fmt(masses.get("auw_kg"), ".3f", " kg"))
        grid.add("wing loading", _fmt(masses.get("wing_loading_g_dm2"), ".1f", " g/dm²"), column=1)
        grid.add("CG", _fmt(masses.get("x_cg_m"), ".4f", " m"))
        self._layout.addWidget(grid)

        if summary.active_constraints or summary.violated_constraints:
            self._layout.addWidget(_section("constraints"))
            chips = QWidget()
            row = QHBoxLayout(chips)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for name in summary.active_constraints:
                row.addWidget(Chip(f"{name} binding", "active"))
            for name in summary.violated_constraints:
                row.addWidget(Chip(f"{name} violated", "violated"))
            row.addStretch(1)
            self._layout.addWidget(_fixed_height(chips))

        optimization = (data.get("performance") or {}).get("optimization") or {}
        if optimization:
            self._layout.addWidget(_section("optimization"))
            grid = MetricGrid()
            grid.add("multistart spread", _fmt(optimization.get("multistart_objective_spread"), ".2e"))
            grid.add("NLP vs re-eval", _fmt(optimization.get("nlp_vs_reeval_gap"), ".2e"), column=1)
            shadow = optimization.get("shadow_price_obj_per_gram")
            grid.add("shadow price", _fmt(shadow, ".4f", " /g"))
            self._layout.addWidget(grid)

            studies = optimization.get("discrete_studies") or {}
            if studies:
                chips = QWidget()
                row = QHBoxLayout(chips)
                row.setContentsMargins(0, 6, 0, 0)
                row.setSpacing(6)
                for attr, study in studies.items():
                    row.addWidget(Chip(f"{attr}: {study.get('adopted')}", "neutral"))
                row.addStretch(1)
                self._layout.addWidget(_fixed_height(chips))

        self._layout.addWidget(_section("artifacts"))
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for text, target, enabled in (
            ("Open report", summary.path / "report.html", summary.has_report),
            ("Open 3D model", summary.path / "interactive_3d.html", summary.has_3d),
            ("Open folder", summary.path, True),
        ):
            button = QPushButton(text)
            button.setEnabled(enabled)
            button.clicked.connect(lambda _=False, p=target: _open(p))
            row.addWidget(button)
        row.addStretch(1)
        self._layout.addWidget(_fixed_height(buttons))

        notes = data.get("notes") or []
        if notes:
            self._layout.addWidget(_section("notes"))
            for note in notes:
                label = QLabel(f"• {note}")
                label.setWordWrap(True)
                label.setStyleSheet("color:#9a9aa0; font-size:11px;")
                self._layout.addWidget(label)

        self._layout.addStretch(1)


def _open(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


# Rows of the comparison table: (label, extractor). Keeping this a plain list
# makes "compare on X too" a one-line change.
_COMPARE_ROWS: list[tuple[str, callable]] = [
    ("objective", lambda s, d: s.objective_text),
    ("cruise speed [m/s]", lambda s, d: _fmt(s.v_ms, ".2f")),
    ("L/D", lambda s, d: _fmt(((d.get("performance") or {}).get("best") or {}).get("L_over_D"), ".2f")),
    ("bus power [W]", lambda s, d: _fmt(((d.get("performance") or {}).get("best") or {}).get("P_elec_w"), ".1f")),
    ("span [m]", lambda s, d: _fmt((d.get("geometry") or {}).get("span_m"), ".3f")),
    ("projected span [m]", lambda s, d: _fmt((d.get("geometry") or {}).get("span_projected_m"), ".3f")),
    ("wing area [m²]", lambda s, d: _fmt((d.get("geometry") or {}).get("area_m2"), ".4f")),
    ("aspect ratio", lambda s, d: _fmt((d.get("geometry") or {}).get("aspect_ratio"), ".2f")),
    ("AUW [kg]", lambda s, d: _fmt((d.get("masses") or {}).get("auw_kg"), ".3f")),
    ("wing loading [g/dm²]", lambda s, d: _fmt((d.get("masses") or {}).get("wing_loading_g_dm2"), ".1f")),
    ("CG [m]", lambda s, d: _fmt((d.get("masses") or {}).get("x_cg_m"), ".4f")),
    ("static margin", lambda s, d: _fmt((d.get("constraints") or {}).get("static_margin"), ".4f")),
    ("stall [m/s]", lambda s, d: _fmt((d.get("constraints") or {}).get("v_stall_ms"), ".2f")),
    ("binding", lambda s, d: ", ".join(s.active_constraints) or "—"),
    ("violated", lambda s, d: ", ".join(s.violated_constraints) or "—"),
]


class CompareView(QWidget):
    """Selected runs as columns; differing values highlighted."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        title = QLabel("Compare")
        title.setStyleSheet("font-size:17px; font-weight:600;")
        layout.addWidget(title)
        self._hint = QLabel("Values that differ across the selected runs are highlighted.")
        self._hint.setStyleSheet("color:#9a9aa0; font-size:11px;")
        layout.addWidget(self._hint)
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

    def show_runs(self, summaries: list[RunSummary]) -> None:
        loaded = []
        for summary in summaries:
            try:
                loaded.append((summary, runindex.load_full(summary.path)))
            except (OSError, ValueError):
                loaded.append((summary, {}))

        self._table.clear()
        self._table.setColumnCount(len(loaded) + 1)
        self._table.setRowCount(len(_COMPARE_ROWS))
        self._table.setHorizontalHeaderLabels(
            ["", *[f"{s.stamp}\n{s.aircraft}" for s, _ in loaded]]
        )

        # Every cell gets an explicit colour: relying on the default palette over
        # alternating row backgrounds leaves the unchanged rows nearly invisible.
        same, differs, label_same, label_differs = (
            QColor("#8b8b92"),
            QColor("#8ab4f8"),
            QColor("#7a7a80"),
            QColor("#d4d4d8"),
        )
        for row, (label, extract) in enumerate(_COMPARE_ROWS):
            name = QTableWidgetItem(label)
            self._table.setItem(row, 0, name)
            values = []
            for column, (summary, data) in enumerate(loaded, start=1):
                try:
                    text = extract(summary, data)
                except Exception:  # noqa: BLE001 — a partial run must not break compare
                    text = "—"
                values.append(text)
                item = QTableWidgetItem(text)
                item.setFont(_mono())
                self._table.setItem(row, column, item)

            row_differs = len(set(values)) > 1  # the point of the view: what changed
            name.setForeground(label_differs if row_differs else label_same)
            for column in range(1, len(loaded) + 1):
                self._table.item(row, column).setForeground(differs if row_differs else same)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for column in range(1, len(loaded) + 1):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        self._table.resizeRowsToContents()
