"""Champion report rendering: RunResult (+ run dir figures) -> self-contained HTML."""

from __future__ import annotations

import base64
import csv
from pathlib import Path

import jinja2

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


def render(result, run_dir: Path | None = None) -> str:
    figures = []
    has_3d = False
    stations = []
    if run_dir is not None:
        for png in sorted((run_dir / "figures").glob("*.png")):
            b64 = base64.b64encode(png.read_bytes()).decode()
            figures.append({"name": png.stem, "b64": b64})
        has_3d = (run_dir / "interactive_3d.html").exists()
        # Read back the exported loft definition rather than recomputing it, so
        # the table in the report and the CSV a builder works from can never
        # disagree about the same aircraft.
        csv_path = run_dir / "geometry" / "stations.csv"
        if csv_path.is_file():
            with csv_path.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    stations.append({
                        **row,
                        **{k: float(row[k]) for k in row if k.endswith(("_m", "_deg"))},
                        "station": int(row["station"]),
                    })
    # Imported rather than restated: the sweep's range rule is described in the
    # report, and a hardcoded percentage here would drift from the code that
    # picks the spans (solve.FLATNESS_SPAN_FRACTION).
    from ..solve import FLATNESS_SPAN_FRACTION

    return _env.get_template("report.html.j2").render(
        r=result, figures=figures, has_3d=has_3d, stations=stations,
        flatness_span_fraction=FLATNESS_SPAN_FRACTION,
    )
