"""Champion report rendering: RunResult (+ run dir figures) -> self-contained HTML."""

from __future__ import annotations

import base64
from pathlib import Path

import jinja2

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


def render(result, run_dir: Path | None = None) -> str:
    figures = []
    if run_dir is not None:
        for png in sorted((run_dir / "figures").glob("*.png")):
            b64 = base64.b64encode(png.read_bytes()).decode()
            figures.append({"name": png.stem, "b64": b64})
    return _env.get_template("report.html.j2").render(r=result, figures=figures)
