# Packaging planeopt as a Windows .exe

`build_windows.ps1` freezes the CLI into `dist/planeopt/planeopt.exe` with
PyInstaller. Run it **from Windows PowerShell** — PyInstaller does not
cross-compile, so a Windows binary must be frozen by a Windows interpreter.

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

It creates `.venv-win/` (separate from the WSL `.venv` — different platform
wheels, never share a directory), installs the package non-editable, freezes
`packaging/planeopt.spec`, and smoke-tests the result with `--version` and
`info`.

Ship the whole `dist/planeopt/` directory. Neither executable runs pulled out
of it: onedir keeps the ~500 MB of CasADi/SciPy/AeroSandbox payload beside the
binaries instead of unpacking it to a temp directory on every launch.

## Two executables, and why

| File | Kind | Use |
|---|---|---|
| `planeopt.exe` | console | the CLI — `run`, `optimize`, `info`, `report`, … |
| `planeopt-gui.exe` | windowed | **double-click this** to open the desktop app |

They are built from the same `entry.py` over the same Analysis; the script
opens the GUI when the running executable's name ends in `-gui`. Two binaries
because a console program cannot be double-clicked into a GUI: Windows opens a
console, Typer reports a missing command, and the window vanishes — which reads
exactly like "the app doesn't launch". The windowed build also has no console,
so `sys.stderr` is `None` and the logging handler is skipped there.

The build stages `aircraft/` and `missions/` beside the executables. A
double-clicked app starts in whatever directory Explorer chose, so without a
project sitting next to the binary it would open onto nothing. Resolution order
is: `--project`, then the last folder chosen in the app (remembered via
QSettings), then the working directory, then the executable's own folder.
`planeopt info` prints which one won — ask for that line first when someone
reports an empty run list.

The desktop GUI ships inside the bundle (`planeopt gui`), so the build installs
`.[gui]`. Only the Core/Gui/Widgets Qt stack is kept — the spec excludes QML,
3D, media, WebEngine and the rest, which this app never loads. The GUI cannot
be launched from a headless build script, so the smoke test asserts on
`planeopt info` reporting `gui extra available` instead; that at least fails
loudly if PySide6 stops being bundled.

## What the bundle contains

`collect_all` is applied to the five packages that read data files at runtime —
`planeopt` (prop tables, report template), `aerosandbox` (airfoil database),
`neuralfoil` (network weights), `casadi` (IPOPT libraries), `plotly` (the JS
inlined into `interactive_3d.html`). If any of those were dropped the failure
would surface only at run time, so `planeopt info` prints what actually
resolved — ask for its output first in any bug report.

## Two traps this spec already works around

Both were found by running the frozen build, not by inspecting it — neither
shows up in a source checkout, and one of them fails silently.

1. **CasADi shared libraries must sit at the bundle root.** PyInstaller hoists
   the extension module `_casadi.pyd` to the root because `_casadi` is a
   top-level import, while `collect_all` files the 97 CasADi DLLs under
   `casadi/`. The result is `ImportError: DLL load failed while importing
   _casadi`. The spec collects them to the root by hand instead.
2. **CasADi's plugin loader needs `CASADIPATH`.** Fixing (1) makes `import
   casadi` work, but every NLP solve loads a *plugin*
   (`libcasadi_nlpsol_ipopt`, `libcasadi_interpolant_bspline`, ...) through a
   runtime search that misses inside a bundle. This one is nasty: nothing
   raises where the fault is. Every trim in the speed sweep is quietly recorded
   as infeasible and the run dies much later. `planeopt/__init__.py` sets
   `CASADIPATH` to the bundle directory when `sys.frozen` is set — deliberately
   in the package rather than a PyInstaller runtime hook, so it holds for any
   front end and shows up in `planeopt info`.

The moral for future dependency changes: startup success proves nothing. The
build script's smoke test therefore runs a full evaluation, which is the only
thing that exercises IPOPT, NeuralFoil, the airfoil database, the prop tables
and the report writer together.

## Deliberate limitations of a frozen build

- **No `--parallel > 1`.** Workers inherit the aircraft object across a fork
  rather than pickling it, and Windows has no fork. The CLI rejects the flag
  immediately instead of failing mid-battery. Sequential solving is unaffected.
- **No STEP import.** The `cad` extra (OCP + VTK + cadquery) is ~900 MB and is
  excluded; `planeopt info` reports it as unavailable. STEP round-trip stays a
  source-install feature.
- **Aircraft definitions are still Python modules.** The exe executes a
  user-authored `aircraft.py` (see `aircraft/vtail_sample/`). Those files import
  `aerosandbox` and `planeopt.types` from inside the bundle, which works, but
  writing one means writing Python. The GUI edits the *mission* as a form and
  picks an aircraft; a form over the aircraft itself is M5.2.

## Runtime expectations to state to any user

A single NLP solve takes minutes and peaks near 13 GB of RAM; a full
`optimize` battery runs for hours and prints progress lines as each solve
lands. Absolute endurance numbers are uncalibrated (see
`docs/VALIDATION_ANCHORS.md`) — rankings and active constraint sets are the
trustworthy outputs.

## Custom prop tables

`PLANEOPT_PROPS_DIR` prepends a directory to the proxy-table search path, so a
user adds their own prop without touching the install:

```powershell
$env:PLANEOPT_PROPS_DIR = "C:\Users\me\my_props"
planeopt info      # lists the tables it can now see
```

Build the JSON with `tools/ingest_props.py` from an APC `PER3_*.dat` file.
