"""Champion report rendering: RunResult -> self-contained HTML.

M0 renders the skeleton (status, geometry, masses, mission). The M4 report battery
(active set, shadow prices, re-solves, flatness/Pareto figures as embedded base64
PNGs) extends the same template.
"""

from __future__ import annotations

from pathlib import Path

import jinja2

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


def render(result) -> str:
    return _env.get_template("report.html.j2").render(r=result)
