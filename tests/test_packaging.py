"""Distribution invariants: everything the app reads at runtime must travel with it.

These guard the failure that a source-tree checkout cannot show — an installed
wheel or a frozen (PyInstaller) build resolves paths from the package, not the
repo, so any runtime file living outside src/planeopt/ silently disappears.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from planeopt import propulsion

PACKAGE_DIR = Path(propulsion.__file__).parent


def test_builtin_props_live_inside_the_package():
    # If this ever points outside the package, the wheel and the .exe lose the tables.
    assert PACKAGE_DIR in propulsion.BUILTIN_PROPS_DIR.parents
    assert propulsion.BUILTIN_PROPS_DIR.is_dir()


def test_every_shipped_table_loads():
    keys = propulsion.available_props()
    assert len(keys) > 400, "the APC catalogue should ship, not a handful of tables"
    for key in keys:
        table = propulsion.PropTable(key)
        assert table.j_max > 0
        assert len(table.ct_coeffs) and len(table.cp_coeffs)
        # the bivariate fit is useless without the Reynolds reconstruction
        assert table.re_coeff > 0
        assert 0 < table.re_range[0] < table.re_range[1]


def test_no_synthetic_tables_ship():
    """Every table must trace to a published source — APC's files or UIUC's.

    The retired apc_11x6_blend was a pitch interpolation between two real props,
    which quietly made one study candidate non-measured — the confound that made
    the 2026-07-27 prop result unreadable. UIUC tables are wind-tunnel
    MEASUREMENT, so they satisfy this check by being more trustworthy than APC's
    simulation output, not less.
    """
    for key in propulsion.available_props():
        source = propulsion.PropTable(key).meta.get("source", "")
        traced = source.upper().startswith("PER3_") or source.startswith("UIUC PDB vol ")
        assert traced, f"{key} traces to no published source: {source!r}"


def test_sample_aircraft_table_is_shipped():
    # The fixture names a table; a release that drops it breaks the sample run.
    assert "apc_11x6" in propulsion.available_props()


def test_missing_table_names_the_search_path_and_alternatives():
    with pytest.raises(FileNotFoundError) as e:
        propulsion.PropTable("no_such_prop")
    msg = str(e.value)
    assert "no_such_prop" in msg
    assert propulsion.PROPS_DIR_ENV in msg  # tells the user how to add their own
    # 443 tables must not be dumped into an exception message
    assert len(msg) < 600, f"error message is {len(msg)} chars — it lists too much"


def test_missing_table_suggests_near_misses():
    with pytest.raises(FileNotFoundError) as e:
        propulsion.PropTable("apc_11x7z")
    assert "apc_11x7e" in str(e.value)  # the table they probably meant


def test_user_directory_overrides_shipped_tables(tmp_path, monkeypatch):
    shipped = json.loads((propulsion.BUILTIN_PROPS_DIR / "apc_11x6.json").read_text())
    custom = dict(shipped, j_range=[0.0, 0.123])
    (tmp_path / "apc_11x6.json").write_text(json.dumps(custom))
    (tmp_path / "my_own_prop.json").write_text(json.dumps(custom))

    monkeypatch.setenv(propulsion.PROPS_DIR_ENV, str(tmp_path))
    assert propulsion.PropTable("apc_11x6").j_max == pytest.approx(0.123)
    assert propulsion.PropTable("my_own_prop").j_max == pytest.approx(0.123)
    assert "my_own_prop" in propulsion.available_props()

    monkeypatch.delenv(propulsion.PROPS_DIR_ENV)
    assert propulsion.PropTable("apc_11x6").j_max != pytest.approx(0.123)


def test_report_template_is_package_data():
    assert (PACKAGE_DIR / "report" / "templates" / "report.html.j2").is_file()


def _text_io_calls_missing_encoding(tree: ast.AST) -> list[str]:
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kwargs = {k.arg for k in node.keywords}
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"read_text", "write_text"}:
            # Path.write_text's second positional argument is the encoding.
            positional = len(node.args) >= (2 if node.func.attr == "write_text" else 1)
            if "encoding" not in kwargs and not positional:
                bad.append(f"{node.func.attr} at line {node.lineno}")
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            mode = next((a.value for a in node.args[1:2] if isinstance(a, ast.Constant)), "r")
            if "b" not in str(mode) and "encoding" not in kwargs:
                bad.append(f"open at line {node.lineno}")
    return bad


def test_text_io_always_declares_utf8():
    """Locale-default encoding is a Windows crash waiting on a multi-hour run.

    The reports carry eta/Delta/arrow characters that cp1252 cannot encode, so
    every text read/write in the package must name its encoding explicitly.
    """
    offenders = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        bad = _text_io_calls_missing_encoding(ast.parse(path.read_text(encoding="utf-8")))
        if bad:
            offenders[path.relative_to(PACKAGE_DIR).as_posix()] = bad
    assert not offenders, f"text I/O without an explicit encoding: {offenders}"
