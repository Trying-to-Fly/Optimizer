"""Thin CLI — EXECUTION_PLAN.md section 3 rule 1: zero logic lives here.

Parse arguments, import config modules, call the library, print the run directory.
The future GUI is a second thin client over the same calls and artifacts.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer

from . import solve
from .report import assemble, html
from .types import AircraftDefinition, MissionSpec

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


def _load_attr(py_file: Path, attr: str):
    # Config packages may import sibling modules (e.g. their construction profile).
    parent = str(py_file.resolve().parent)
    sys.path.insert(0, parent)
    try:
        spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[py_file.stem] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(parent)
    try:
        return getattr(module, attr)
    except AttributeError:
        raise typer.BadParameter(f"{py_file} does not define `{attr}`")


def load_aircraft(path: Path) -> tuple[AircraftDefinition, Path]:
    py = path / "aircraft.py" if path.is_dir() else path
    return _load_attr(py, "AIRCRAFT"), py


def load_mission(path: Path) -> tuple[MissionSpec, Path]:
    return _load_attr(path, "MISSION"), path


@app.command()
def run(
    mission: Path = typer.Argument(..., help="Mission module, e.g. missions/endurance_sample.py"),
    aircraft: Path = typer.Option(..., "--aircraft", "-a", help="Aircraft package dir or aircraft.py"),
    runs_dir: Path = typer.Option(Path("runs"), help="Root directory for run artifacts"),
):
    """Evaluate/optimize AIRCRAFT for MISSION; write a run artifact directory."""
    ac, ac_file = load_aircraft(aircraft)
    ms, ms_file = load_mission(mission)
    result, run_dir = solve.run(ac, ms, runs_dir, input_files=[ac_file, ms_file])
    typer.echo(f"status: {result.status}")
    typer.echo(run_dir)


@app.command()
def report(run_dir: Path = typer.Argument(..., help="A runs/<...> directory")):
    """Re-render report.html from an existing run.json."""
    result = assemble.load(run_dir)
    (run_dir / "report.html").write_text(html.render(result, run_dir))
    typer.echo(run_dir / "report.html")


@app.command()
def objectives():
    """List the objective library."""
    from .mission import OBJECTIVES

    for o in OBJECTIVES.values():
        typer.echo(f"{o.name:15s} {o.direction:8s} [{o.units}] wind={o.wind_mode:10s} {o.description}")


if __name__ == "__main__":
    app()
