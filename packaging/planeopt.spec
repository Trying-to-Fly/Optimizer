# PyInstaller spec for the planeopt CLI — see packaging/README.md.
#
# onedir, not onefile: the bundle is several hundred MB (CasADi/IPOPT, SciPy,
# the AeroSandbox airfoil database, NeuralFoil weights). onefile would unpack
# all of it to a temp directory on every invocation, which is intolerable for a
# tool whose runs already last hours.
#
# Build:  pyinstaller --noconfirm --clean packaging/planeopt.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Packages whose data files are read at runtime and would otherwise be dropped:
#   planeopt     prop proxy tables + the report Jinja template
#   aerosandbox  airfoil coordinate database, property tables
#   neuralfoil   trained network weights (.npz) behind every polar
#   plotly       the JS bundle inlined into interactive_3d.html
datas, binaries, hiddenimports = [], [], []
for package in ("planeopt", "aerosandbox", "neuralfoil", "plotly"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# CasADi is handled by hand, and the placement is the whole point. PyInstaller
# hoists the extension module _casadi.pyd to the bundle root because `_casadi`
# is a top-level import, but collect_all files the package's shared libraries
# under casadi/ — so the .pyd loads and immediately fails to find libcasadi.
# Landing every library at the root puts them beside the .pyd (which is also
# where CasADi's plugin loader looks for libcasadi_nlpsol_ipopt and friends).
# Skipping collect_all here also drops ~130 MB of headers, .lib import
# libraries and cmake config that only matter when compiling against CasADi.
import casadi as _casadi_build_probe

_casadi_dir = Path(_casadi_build_probe.__file__).parent
_shared_libs = (
    list(_casadi_dir.glob("*.dll"))
    or list(_casadi_dir.glob("*.so*"))
    or list(_casadi_dir.glob("*.dylib"))
)
if not _shared_libs:
    raise SystemExit(f"no CasADi shared libraries found in {_casadi_dir}")
binaries += [(str(lib), ".") for lib in _shared_libs]
hiddenimports += collect_submodules("casadi")

# Aircraft/mission configs are user-authored Python executed at run time
# (cli._load_attr). They import aerosandbox freely, so the analysis below cannot
# see what they need — these are the imports a config is entitled to expect.
hiddenimports += [
    "aerosandbox",
    "aerosandbox.numpy",
    "scipy.optimize",
    "scipy.interpolate",
    "scipy.special",
]

# Weight the bundle does not need. The CAD extra alone (OCP + VTK + cadquery)
# is roughly 900 MB; STEP import stays a source-install feature, and `planeopt
# info` reports it as unavailable in a frozen build.
excludes = [
    "cadquery", "OCP", "vtkmodules", "vtk", "ezdxf", "nptyping",
    "IPython", "jupyter", "notebook", "ipykernel", "ipywidgets",
    "pytest", "sphinx", "tkinter", "PyQt5", "PyQt6", "PySide2",
    # PySide6 itself ships (the GUI is part of the product), but only the
    # Core/Gui/Widgets stack is used — QML, 3D, media and the rest are tens of
    # MB of Qt libraries this app never loads.
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtOpenGLFunctions", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    # NOT shiboken6: it is the binding layer PySide6 imports at startup, and
    # excluding it leaves an exe whose CLI works fine and whose GUI cannot load.
]

# SPECPATH is injected by PyInstaller; spell the entry path out so the build
# works from any working directory.
_here = Path(SPECPATH)

a = Analysis(
    [str(_here / "entry.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],  # CASADIPATH is set by planeopt/__init__.py — see README
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="planeopt",
    debug=False,
    strip=False,
    upx=False,  # UPX corrupts some MKL/CasADi DLLs; size is not the constraint here
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="planeopt",
)
