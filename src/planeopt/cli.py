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

import planeopt

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
    if sys.stderr is None:
        return  # windowed build: no console to write to, and emitting would fail
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
        help="Concurrent NLP solves per batch. Each solve peaks ~14.5 GB — "
        "2 needs the 26 GB WSL allotment (HANDOFF section 2). POSIX only.",
    ),
    memory_budget_gb: float = typer.Option(
        None,
        "--memory-budget-gb",
        help="RAM to dedicate to this run; the width is derived from it and from "
        "the per-solve peak previous runs measured. Does not speed up one solve "
        "(single-core, memory-bound) — it decides how many run at once. "
        "Ignored when --parallel is given explicitly.",
    ),
    solve_timeout_min: float = typer.Option(
        solve.SOLVE_TIMEOUT_MIN, "--solve-timeout-min",
        help="Wall-clock ceiling for ONE member solve. A converging solve takes "
        "4-10 min; a diverging one has no natural end and can otherwise own the "
        "whole run. Members that hit the cap are recorded and the battery goes on.",
    ),
    checkpoint: Path = typer.Option(
        None, "--checkpoint",
        help="Directory for per-member results. A battery runs for hours; with a "
        "checkpoint directory a stopped run continues instead of restarting, and "
        "re-running the same command resumes.",
    ),
    pause_file: Path = typer.Option(
        None, "--pause-file",
        help="Create this file while a run is going to stop it cleanly at the next "
        "member boundary, freeing all memory. Needs --checkpoint to be resumable. "
        "The wait is at most one member (--solve-timeout-min) because a solve in "
        "progress cannot be saved — see `optimize`'s docstring.",
    ),
    live_dir: Path = typer.Option(
        None, "--live-dir",
        help="Directory for live viewer frames (M5.4). One small gzip'd JSON per "
        "IPOPT iterate and per finished member, moved into <run_dir>/frames/ when "
        "the run completes. Watch them in the GUI, or replay them with "
        "`planeopt timelapse`. Measured at 12 ms per iterate — 0.25 s on a "
        "286 s solve — and it can never fail a solve.",
    ),
    warm_start: Path = typer.Option(
        None, "--warm-start",
        help="A runs/<...> directory whose champion seeds the nominal solve and "
        "every study candidate. An initial guess only — all variables stay free. "
        "Perturbed multistarts stay cold, so convergence evidence survives.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """Optimize AIRCRAFT for MISSION (M2: wing + cruise state); write run artifacts."""
    _setup_logging(quiet)
    warm = warm_from = None
    if warm_start is not None:
        prior = assemble.load(warm_start)
        champ = (prior.performance.get("optimization") or {}).get("champion") or {}
        if not champ.get("dv"):
            raise typer.BadParameter(
                f"{warm_start} has no champion design vector to start from "
                "(is it an evaluation run rather than an optimize run?)",
                param_hint="--warm-start",
            )
        warm = {**champ["dv"], "V": champ["V_ms"]}
        warm_from = warm_start.name
    try:
        solve.check_parallel(parallel)
    except RuntimeError as e:  # fail in a second, not after the first batch
        raise typer.BadParameter(str(e), param_hint="--parallel")
    if pause_file is not None and pause_file.exists():
        # left over from the previous pause — clearing it here means "resume"
        # does not stop again the instant it starts
        pause_file.unlink()
        typer.echo(f"cleared the pause request at {pause_file}")
    ac, ac_file = load_aircraft(aircraft)
    ms, ms_file = load_mission(mission)
    try:
        result, run_dir = solve.optimize(
            ac, ms, runs_dir, input_files=[ac_file, ms_file],
            multistart=multistart, flatness=flatness, parallel=parallel,
            memory_budget_gb=memory_budget_gb,
            warm_start=warm, warm_start_from=warm_from,
            solve_timeout_min=solve_timeout_min,
            checkpoint_dir=checkpoint, pause_file=pause_file,
            live_dir=live_dir,
        )
    except solve.RunPaused as paused:
        # A pause is a successful outcome, not a failure: exit 0 so a shell loop
        # or the GUI queue does not treat it as a crashed run.
        typer.echo(f"PAUSED — {paused}")
        if checkpoint is not None:
            typer.echo(f"progress is in {checkpoint}; re-run the same command to resume")
        else:
            typer.echo("WARNING: no --checkpoint was given, so this run cannot resume")
        raise typer.Exit(code=0)
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
def build(
    run_dir: Path = typer.Argument(..., help="A runs/<...> directory"),
    aircraft: Path = typer.Option(..., "--aircraft", "-a", help="Aircraft package dir or aircraft.py"),
):
    """Re-render the build document (manufacturing/BUILD.md + CSVs) from a run."""
    from .report import manufacturing

    ac, _ = load_aircraft(aircraft)
    result = assemble.load(run_dir)
    champ = (result.performance.get("optimization") or {}).get("champion") or {}
    # the champion's DISCRETE choices are not in dv — without them this rebuilds
    # the aircraft file's defaults and can document parts the champion rejected
    with assemble.as_champion(result, ac) as cfg:
        out = manufacturing.write(result, ac.geometry(champ.get("dv")), ac, run_dir)
    if cfg:
        typer.echo("champion configuration: "
                   + ", ".join(f"{k}={v}" for k, v in sorted(cfg.items())))
    typer.echo(out / "BUILD.md")


@app.command()
def timelapse(
    source: Path = typer.Argument(
        ..., help="A run directory (its frames/ is found automatically), or a "
        "live frame directory under runs/_live/",
    ),
    out: Path = typer.Option(
        None, "--out",
        help="Where the images go. Default: <run_dir>/timelapse/ for a run (it is "
        "an artifact of that run), or <live_dir>-timelapse beside a live directory.",
    ),
    fps: int = typer.Option(30, help="Frames per second of the assembled video."),
    size: str = typer.Option("1920x1080", help="Render size, WIDTHxHEIGHT."),
    scalar: str = typer.Option(
        "cl", help="Colour by: cl, stall_margin, gamma, or lift_per_span.",
    ),
    kind: str = typer.Option("all", help="Which frames: all, iterate, or candidate."),
    hold_candidate: int = typer.Option(
        15, "--hold-candidate",
        help="Repeat each converged member's frame this many times, so it lingers "
        "on screen instead of flashing past between iterates.",
    ),
    view: str = typer.Option(
        None, "--view",
        help="Camera preset: front-top-left, front-top-right, rear-top-left, "
        "rear-top-right, plan, front, side. Default: whatever view was chosen "
        "for this run in the New Run dialog, else front-top-left.",
    ),
    yaw: float = typer.Option(
        None, "--yaw", help="Camera azimuth in degrees, overriding --view. "
        "0 looks from behind, 180 from ahead, -90 from the port side.",
    ),
    pitch: float = typer.Option(
        None, "--pitch", help="Camera elevation in degrees, overriding --view. "
        "0 is level with the wing, 90 is straight down.",
    ),
    streamlines: bool = typer.Option(
        True, "--streamlines/--no-streamlines",
        help="Draw the wake streamlines candidate frames carry.",
    ),
    lift_distribution: bool = typer.Option(
        False, "--lift-dist/--no-lift-dist",
        help="Draw the spanwise lift distribution against an elliptical reference.",
    ),
    colour_iterates: bool = typer.Option(
        False, "--colour-iterates",
        help="Compute each iterate's aerodynamics as it renders, so every frame "
        "is coloured instead of only the converged ones. About 0.2 s per frame, "
        "and nothing is written back — use `planeopt recolour` to pay once and "
        "keep the result. Needs the run's aircraft (found from its inputs/ "
        "snapshot, or given with --aircraft).",
    ),
    aircraft: Path = typer.Option(
        None, "--aircraft", "-a",
        help="Only for --colour-iterates: the aircraft definition this run used. "
        "Defaults to the run's own inputs/aircraft.py snapshot.",
    ),
):
    """Replay a run's live frames into PNGs (and an MP4 if ffmpeg is installed)."""
    _setup_logging()
    try:
        from .gui import timelapse as timelapse_mod
    except ImportError as e:  # PySide6 absent — the renderer is Qt's QPainter
        from .gui import INSTALL_HINT

        typer.echo(f"{INSTALL_HINT}\n\n({e})", err=True)
        raise typer.Exit(1)
    recolour_with = None
    if colour_iterates:
        from . import recolour as recolour_mod

        found = aircraft or recolour_mod.snapshot_aircraft(source)
        if found is None:
            raise typer.BadParameter(
                f"{source} has no inputs/aircraft.py snapshot, so --colour-iterates "
                "has nothing to rebuild the geometry from. Give --aircraft the "
                "definition this run used.",
                param_hint="--colour-iterates",
            )
        recolour_with, _ = load_aircraft(found)
        typer.echo(f"colouring iterates against {found}")
    try:
        result = timelapse_mod.render(
            source, out, fps=fps, size=timelapse_mod.parse_size(size), scalar=scalar,
            kind=kind, hold_candidate=hold_candidate, streamlines=streamlines,
            lift_distribution=lift_distribution, view=view, yaw=yaw, pitch=pitch,
            recolour_with=recolour_with, progress=typer.echo,
        )
    except (ValueError, FileNotFoundError) as e:
        raise typer.BadParameter(str(e))
    typer.echo(
        f"{result['images']} image(s) from {result['source_frames']} frame(s) "
        f"at {result['size'][0]}x{result['size'][1]}"
        + (f" ({result['unreadable']} unreadable, skipped)" if result["unreadable"] else "")
    )
    # Which camera, and why — an unexpected view is otherwise a five-minute
    # render followed by a hunt for where the angle came from.
    typer.echo(f"rendered from {result['camera_from']}")
    if colour_iterates:
        typer.echo(
            f"{result['recoloured']} iterate(s) coloured for this render only "
            "(untrimmed — see the caption under the stats block)"
        )
    if result["video"] is not None:
        typer.echo(result["video"])
    else:
        typer.echo("ffmpeg is not on PATH, so the PNGs were not assembled. Run:")
        typer.echo(f"  {result['ffmpeg_command']}")
    typer.echo(result["out_dir"])


@app.command()
def report(run_dir: Path = typer.Argument(..., help="A runs/<...> directory")):
    """Re-render report.html from an existing run.json."""
    result = assemble.load(run_dir)
    (run_dir / "report.html").write_text(html.render(result, run_dir), encoding="utf-8")
    typer.echo(run_dir / "report.html")


@app.command()
def props(
    match: str = typer.Argument("", help="Substring filter, e.g. '11x' or '.5e'"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show fit quality and ranges"),
):
    """List the fitted propeller tables (the whole published APC catalogue)."""
    from . import propulsion

    keys = [k for k in propulsion.available_props() if match.lower() in k.lower()]
    if not keys:
        typer.echo(f"no prop table matches {match!r} among "
                   f"{len(propulsion.available_props())} available")
        raise typer.Exit(1)
    for key in keys:
        if not detail:
            typer.echo(key)
            continue
        t = propulsion.PropTable(key)
        m = t.meta
        typer.echo(
            f"{key:22s} {str(m.get('display_name','?')):12s} "
            f"J<={t.j_max:.3f}  Re {t.re_range[0]/1e3:6.1f}k-{t.re_range[1]/1e3:6.1f}k  "
            f"eta err {m.get('eta_rel_pct', float('nan')):4.1f}%"
        )
    typer.echo(f"\n{len(keys)} of {len(propulsion.available_props())} tables")


@app.command()
def objectives():
    """List the objective library."""
    from .mission import OBJECTIVES

    for o in OBJECTIVES.values():
        typer.echo(f"{o.name:15s} {o.direction:8s} [{o.units}] wind={o.wind_mode:10s} {o.description}")


@app.command()
def gui(
    project_dir: Path = typer.Option(
        None, "--project", "-p",
        help="Folder holding aircraft/ and missions/. Default: the last one used, "
        "else the working directory, else the folder the executable lives in.",
    ),
):
    """Open the desktop app (M5): browse and compare runs, queue new ones."""
    from .gui import launch

    _setup_logging()
    try:
        raise typer.Exit(launch(project_dir))
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
    props = propulsion.available_props()
    # 443 shipped tables would bury the rest of this report, so it reports the
    # count and points at the command that lists them.
    typer.echo(f"prop tables     {len(props)} available"
               f"{'' if props else ' — NONE FOUND'}"
               f"{' (planeopt props to list)' if props else ''}")
    for d in propulsion.props_search_path():
        typer.echo(f"  search        {d} {'' if d.is_dir() else '(missing)'}")
    if not solve.parallel_available():
        parallel_state = "unavailable (no fork)"
    elif planeopt._FORK_SAFE_MACOS is False:
        # Reported rather than left to be discovered, because the symptom is
        # workers that segfault and are logged as running out of memory.
        parallel_state = "UNSAFE — NumPy was imported before planeopt (see check_parallel)"
    else:
        parallel_state = "available"
    typer.echo(f"parallel solves {parallel_state}")

    # RAM is the binding resource for this app, so the install report says what
    # this machine has and what a solve on it has actually cost.
    from . import memory as memory_mod

    total_gb, avail_gb = memory_mod.machine_ram()
    swap = memory_mod.swap_gb()
    measured = memory_mod.observed_peak_gb(Path("runs"))
    if total_gb:
        # macOS gets two extra clauses because two of its numbers mean something
        # different from their namesakes elsewhere: swap is provisioned on demand
        # rather than fixed, so the figure is a floor; and several GB of what the
        # machine is using may be sitting compressed, which is why a Mac can show
        # very little free memory and still take a 14.5 GB solve.
        clauses = []
        if swap:
            clauses.append(
                f"+{swap:.0f} GB swap"
                + (", grows on demand" if sys.platform == "darwin" else "")
            )
        compressed = memory_mod.compressed_gb()
        if compressed:
            clauses.append(f"{compressed:.1f} GB compressed")
        detail = f" ({'; '.join(clauses)})" if clauses else ""
        typer.echo(f"memory          {avail_gb:.1f} GB free of {total_gb:.1f} GB{detail}")
    else:
        typer.echo("memory          (unavailable on this platform)")
    per = measured or memory_mod.DEFAULT_PER_SOLVE_GB
    typer.echo(
        f"peak per solve  {per:.1f} GB "
        f"({'measured from runs/' if measured else 'assumed — no run has measured one yet'})"
    )
    if total_gb:
        # What --memory-budget-gb would do at the largest budget this machine
        # can back, i.e. the most concurrency available here.
        budget = max(0.0, total_gb + swap - memory_mod.RESERVE_GB)
        width, why = memory_mod.plan_parallel(budget, per_solve_gb=measured)
        typer.echo(f"  max budget    {budget:.0f} GB -> {width} concurrent solve(s) [{why}]")
    # Where CasADi will look for its solver plugins — the single most useful
    # line when a packaged build reports every point as infeasible.
    try:
        import casadi

        typer.echo(f"casadi plugins  {casadi.GlobalOptions.getCasadiPath()}")
    except Exception as e:  # noqa: BLE001 — diagnostics must never fail
        typer.echo(f"casadi plugins  UNAVAILABLE ({type(e).__name__}: {e})")
    typer.echo(f"CASADIPATH      {os.environ.get('CASADIPATH', '(unset)')}")
    typer.echo(f"runs default    {(Path('runs')).resolve()}")

    # Where the GUI would look if opened right now. This is the first thing to
    # check when a packaged app comes up with an empty run list.
    from .gui.workspace import resolve as resolve_workspace

    project = resolve_workspace()
    typer.echo(
        f"project folder  {project.root}"
        f" ({len(project.aircraft_packages())} aircraft,"
        f" {len(project.missions())} missions)"
    )

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


@app.command()
def recolour(
    source: Path = typer.Argument(
        ..., help="A run directory (its frames/ is found automatically), or a "
        "live frame directory under runs/_live/",
    ),
    aircraft: Path = typer.Option(
        None, "--aircraft", "-a",
        help="The aircraft definition the run used. Defaults to the run's own "
        "inputs/aircraft.py snapshot, which is the only copy guaranteed to be the "
        "one those frames came from. Refused if its design vector does not match "
        "the frames', since recolouring with the wrong definition would draw a "
        "different aeroplane under this run's name.",
    ),
    out: Path = typer.Option(
        None, "--out",
        help="Where the recoloured frames go. Default: <source>-coloured beside it.",
    ),
    in_place: bool = typer.Option(
        False, "--in-place",
        help="Rewrite the frames where they are. The originals are the record of "
        "what the solver saw, so this is opt-in.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """Fill in the aerodynamics on a finished run's iterate frames.

    Iterate frames are geometry-only because computing circulation DURING a solve
    means evaluating it inside the Opti graph, which peaks near 14.5 GB. Doing it
    afterwards costs a plain numeric lifting line — about 0.2 s per frame — so
    every frame of a timelapse can carry colours, a wake and a lift distribution
    for a couple of minutes of an idle machine and nothing at all from the solve.

    The numbers on a recoloured iterate are real but UNTRIMMED: lift does not
    equal weight until the solve says so. The frames say this and so does the
    stats block.
    """
    _setup_logging(quiet)
    from . import recolour as recolour_mod

    ac = None
    if aircraft is None:
        snapshot = recolour_mod.snapshot_aircraft(source)
        if snapshot is not None:
            try:
                ac, _ = load_aircraft(snapshot)
                typer.echo(f"using this run's own snapshot: {snapshot}")
            except Exception as e:  # noqa: BLE001
                # `inputs/` snapshots the files that were passed, not the package
                # around them, so an aircraft importing a sibling profile module
                # cannot be loaded from it. Say which and ask, rather than
                # tracebacking out of a convenience.
                typer.echo(
                    f"could not load {snapshot} ({type(e).__name__}: {e}) — it "
                    "snapshots the aircraft file but not its package"
                )
        if ac is None:
            raise typer.BadParameter(
                f"give --aircraft the definition {source} was run with. "
                + ("Its inputs/ snapshot could not be loaded on its own."
                   if snapshot is not None else
                   "A live frame directory has no snapshot — the run has not finished."),
                param_hint="--aircraft",
            )
    else:
        ac, _ = load_aircraft(aircraft)
    try:
        result = recolour_mod.recolour(
            source, ac, out=out, in_place=in_place,
            progress=None if quiet else typer.echo,
        )
    except (FileNotFoundError, recolour_mod.AircraftMismatch) as e:
        raise typer.BadParameter(str(e))
    typer.echo(
        f"{result['recoloured']} of {result['frames']} frame(s) recoloured in "
        f"{result['seconds']} s"
        + (f" ({result['per_frame_s']} s each)" if result["per_frame_s"] else "")
    )
    if result["skipped"]:
        # Named rather than silent: an infeasible iterate is ordinary, but "12 of
        # 300 could not be drawn" is the difference between a thin timelapse and
        # a broken one.
        typer.echo(
            f"{result['skipped']} could not be recoloured and were kept as they "
            "were (an infeasible iterate has no aeroplane to solve)"
        )
    typer.echo(result["out_dir"])


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
