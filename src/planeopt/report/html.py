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


def _fmt(value, spec: str = "%.3f") -> str:
    """Format a number, and never print a minus sign in front of nothing.

    An IPOPT solution sits on a bound to within its own tolerance, so a variable
    whose floor is zero comes back as something like -3e-17. `"%.4f"` renders
    that as **-0.0000**, and `"%+.0f"` on the ballast column as **-0** — which
    reads as a negative mass of ballast, on a row whose declared box starts at
    zero. The magnitude is not being hidden: -0.0001 still prints as -0.0001,
    because the zeros are only stripped when every digit shown is a zero.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    text = spec % value
    if text.lstrip("+-").strip("0.") == "":
        return text.lstrip("+-") if text.startswith("-") else text
    return text


def _pairs(mapping) -> list[tuple[str, str]]:
    """A dict-valued constraint as readable rows instead of a Python repr.

    `constraints.sm_read_at` is a mapping, and the constraints table's fallback
    branch is `{{ v }}` — so it rendered as `{'nlp_V_ms': 9.741593732349461,
    'reeval_V_ms': 9.5, ...}`, quotes and all, at full float precision. That
    field is the one HANDOFF points at first when the two static margins
    disagree, so hiding it the way the Geometry table hides mappings would be
    worse than the repr. Floats are shortened here for the same reason the
    numeric branch exists: seventeen significant figures of a cruise speed is
    not a measurement, it is a repr.
    """
    rows = []
    for key, value in mapping.items():
        if isinstance(value, float):
            rows.append((str(key), _fmt(value, "%.4g")))
        else:
            rows.append((str(key), str(value)))
    return rows


_env.filters["num"] = _fmt
_env.filters["pairs"] = _pairs


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
