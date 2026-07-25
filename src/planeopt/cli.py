"""Thin CLI — EXECUTION_PLAN.md section 3 rule 1: zero logic lives here.

Parse arguments, import config modules, call the library, print the run directory.
The future GUI is a second thin client over the same calls and artifacts.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

import typer

from . import __version__, solve
from .report import assemble, html
from .types import AircraftDefinition, MissionSpec

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


def _setup_logging(quiet: bool = False) -> None:
    """Attach the console handler to planeopt's logger only.

    Scoped to our logger on purpose: root-level config would drag in AeroSandbox
    and matplotlib chatter and bury the progress lines.
    """
    logger = logging.getLogger("planeopt")
    logger.setLevel(logging.WARNING if quiet else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)


def _version_callback(value: bool):
    if value:
        typer.echo(f"planeopt {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show the version and exit.",
    ),
):
    """General-purpose small-aircraft MDO — see `planeopt info` for the install report."""


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
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """Evaluate/optimize AIRCRAFT for MISSION; write a run artifact directory."""
    _setup_logging(quiet)
    ac, ac_file = load_aircraft(aircraft)
    ms, ms_file = load_mission(mission)
    result, run_dir = solve.run(ac, ms, runs_dir, input_files=[ac_file, ms_file])
    typer.echo(f"status: {result.status}")
    typer.echo(run_dir)


@app.command()
def optimize(
    mission: Path = typer.Argument(..., help="Mission module, e.g. missions/endurance_sample.py"),
    aircraft: Path = typer.Option(..., "--aircraft", "-a", help="Aircraft package dir or aircraft.py"),
    runs_dir: Path = typer.Option(Path("runs"), help="Root directory for run artifacts"),
    multistart: int = typer.Option(3, help="Number of NLP starts (1 = nominal only)"),
    flatness: bool = typer.Option(True, help="Span flatness sweep (re-optimized)"),
    parallel: int = typer.Option(
        1,
        help="Concurrent NLP solves per batch. Each solve peaks ~13 GB — "
        "2 needs the 26 GB WSL allotment (HANDOFF section 2). POSIX only.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """Optimize AIRCRAFT for MISSION (M2: wing + cruise state); write run artifacts."""
    _setup_logging(quiet)
    try:
        solve.check_parallel(parallel)
    except RuntimeError as e:  # fail in a second, not after the first batch
        raise typer.BadParameter(str(e), param_hint="--parallel")
    ac, ac_file = load_aircraft(aircraft)
    ms, ms_file = load_mission(mission)
    result, run_dir = solve.optimize(
        ac, ms, runs_dir, input_files=[ac_file, ms_file],
        multistart=multistart, flatness=flatness, parallel=parallel,
    )
    champ = result.performance["optimization"]["champion"]
    typer.echo(f"status: {result.status}")
    typer.echo(f"champion: {champ['dv']} V={champ['V_ms']:.1f} -> "
               f"{champ['objective_value']:.1f} {result.performance.get('objective_units','')}")
    typer.echo(run_dir)


@app.command()
def pareto(
    mission: Path = typer.Argument(...),
    aircraft: Path = typer.Option(..., "--aircraft", "-a"),
    values: str = typer.Option("10,11,12,13,14,15", help="Comma-separated cruise-speed floors (m/s)"),
):
    """Epsilon-constraint sweep: objective vs. minimum cruise speed."""
    import json

    ac, _ = load_aircraft(aircraft)
    ms, _ = load_mission(mission)
    out = solve.pareto(ac, ms, [float(x) for x in values.split(",")])
    typer.echo(json.dumps(out, indent=2))


@app.command()
def airfoils(
    mission: Path = typer.Argument(...),
    aircraft: Path = typer.Option(..., "--aircraft", "-a"),
    candidates: str = typer.Option("sd7037,ag35,e205,mh32", help="Comma-separated UIUC airfoil names"),
):
    """Discrete outer loop: one full optimization per candidate airfoil,
    compared under smooth and tripped polars."""
    import json

    ac, _ = load_aircraft(aircraft)
    ms, _ = load_mission(mission)
    out = solve.airfoil_study(ac, ms, candidates.split(","))
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command()
def brief(
    run_dir: Path = typer.Argument(..., help="A runs/<...> directory"),
    aircraft: Path = typer.Option(..., "--aircraft", "-a", help="Aircraft package dir or aircraft.py"),
):
    """Render design_brief.md from a run — the CAD round-trip's handoff document."""
    from .report import brief as brief_mod

    ac, _ = load_aircraft(aircraft)
    result = assemble.load(run_dir)
    out = run_dir / "design_brief.md"
    out.write_text(brief_mod.render(result, ac), encoding="utf-8")
    typer.echo(out)


@app.command()
def report(run_dir: Path = typer.Argument(..., help="A runs/<...> directory")):
    """Re-render report.html from an existing run.json."""
    result = assemble.load(run_dir)
    (run_dir / "report.html").write_text(html.render(result, run_dir), encoding="utf-8")
    typer.echo(run_dir / "report.html")


@app.command()
def objectives():
    """List the objective library."""
    from .mission import OBJECTIVES

    for o in OBJECTIVES.values():
        typer.echo(f"{o.name:15s} {o.direction:8s} [{o.units}] wind={o.wind_mode:10s} {o.description}")


@app.command()
def gui(
    runs_dir: Path = typer.Option(Path("runs"), help="Root directory for run artifacts"),
    aircraft_dir: Path = typer.Option(Path("aircraft"), help="Directory of aircraft packages"),
    missions_dir: Path = typer.Option(Path("missions"), help="Directory of mission modules"),
):
    """Open the desktop app (M5): browse and compare runs, queue new ones."""
    from .gui import launch

    _setup_logging()
    try:
        raise typer.Exit(launch(runs_dir, aircraft_dir, missions_dir))
    except RuntimeError as e:  # PySide6 missing — a plain message, not a traceback
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


@app.command()
def info():
    """Install report: version, packaged data, and platform capabilities.

    First thing to ask for in a bug report from a packaged build — it shows
    whether the bundled data actually resolved.
    """
    from . import propulsion

    frozen = getattr(sys, "frozen", False)
    typer.echo(f"planeopt        {__version__}")
    typer.echo(f"python          {sys.version.split()[0]} ({sys.platform})")
    typer.echo(f"install         {'frozen bundle' if frozen else 'source/wheel'}")
    typer.echo(f"package         {Path(__file__).parent}")
    typer.echo(f"prop tables     {', '.join(propulsion.available_props()) or 'NONE FOUND'}")
    for d in propulsion.props_search_path():
        typer.echo(f"  search        {d} {'' if d.is_dir() else '(missing)'}")
    typer.echo(f"parallel solves {'available' if solve.parallel_available() else 'unavailable (no fork)'}")
    # Where CasADi will look for its solver plugins — the single most useful
    # line when a packaged build reports every point as infeasible.
    try:
        import casadi

        typer.echo(f"casadi plugins  {casadi.GlobalOptions.getCasadiPath()}")
    except Exception as e:  # noqa: BLE001 — diagnostics must never fail
        typer.echo(f"casadi plugins  UNAVAILABLE ({type(e).__name__}: {e})")
    typer.echo(f"CASADIPATH      {os.environ.get('CASADIPATH', '(unset)')}")
    typer.echo(f"runs default    {(Path('runs')).resolve()}")

    try:
        import cadquery  # noqa: F401

        cad = "available"
    except Exception:
        cad = "not installed (STEP import disabled)"
    typer.echo(f"cad extra       {cad}")

    try:
        from PySide6 import QtWidgets  # noqa: F401

        gui_state = "available (planeopt gui)"
    except Exception:
        gui_state = "not installed (uv sync --extra gui)"
    typer.echo(f"gui extra       {gui_state}")


def main() -> None:
    """Console-script / frozen-bundle entry point.

    freeze_support must run before anything else: in a frozen build every
    worker process re-executes this binary, and without it a child would
    re-enter the CLI instead of the worker.
    """
    import multiprocessing

    multiprocessing.freeze_support()
    # The status strings and report contain em dashes and Greek letters; a
    # Windows console defaulting to cp1252 renders them as mojibake or raises.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
