"""A content fingerprint of everything that can change a solve RESULT.

WHY THIS EXISTS

A battery's checkpoints are keyed by `(phase label, member key)` and nothing
else, so the sequence lines up but the PHYSICS does not have to. Resume a run
after the model has moved and you get a single artifact whose members were
solved under two different models — champion from one, flatness curve from the
other — with no warning anywhere, because every individual member converged.

That is not hypothetical. On 2026-08-01 a whole battery had to be discarded for
exactly this reason (`vortex_core_radius`, FINDINGS section 18.7), and the only
thing that caught it was a human remembering which checkpoints predated the fix.
Nothing stopped it happening again — and the GUI is the path most exposed to it,
because it derives the checkpoint directory from the MISSION NAME alone, so two
runs a month apart with different physics land in the same folder by default.

WHAT IT COVERS, AND THE INCLUSION RULE

Everything, minus an explicit exclusion list. The rule is deliberately the
pessimistic one: a module is part of the model unless someone has said in
writing that it is presentation. Getting that wrong in the safe direction costs
a re-solve; getting it wrong in the other direction costs a run you believe.

`tests/test_fingerprint.py` pins the partition, so a NEW module cannot silently
escape the fingerprint by being neither listed nor noticed.

WHAT IT DOES WITH A MISMATCH

Nothing dramatic: checkpoint entries live in a per-fingerprint SUBDIRECTORY, so
a changed model simply starts a fresh set beside the old one. No error to
dismiss, no results deleted, and resuming within one model works exactly as
before. The alternative designs are both worse — refusing to start turns a model
edit into a blocked run, and discarding the old entries throws away hours to
protect against a mistake the user may not have made.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import inspect
import json
from pathlib import Path

_PKG = Path(__file__).resolve().parent

#: Package-relative paths that CANNOT change a solve result: entry points and
#: the two presentation layers. Each one is excluded because it reads the model
#: and never feeds it — `report/` renders a finished RunResult, `gui/` is a
#: client over the same library and artifacts (`gui/__init__.py`), and `cli.py`
#: / `__main__.py` only parse arguments and dispatch.
#:
#: Everything else in the package is model, including the shipped propeller and
#: airfoil tables under `data/` — a refitted table moves every objective that
#: reads it, and it is the kind of change least likely to be remembered.
NON_MODEL = ("gui", "report", "cli.py", "__main__.py")

#: Read in binary and hashed whole, so this stays honest about non-Python model
#: inputs. `.pyc` is excluded because it is derived, and would make the
#: fingerprint depend on whether something had been imported yet.
_SKIP_SUFFIXES = (".pyc", ".pyo")
_SKIP_DIRS = ("__pycache__",)


def _iter_files(root: Path, exclude: tuple[str, ...] = ()):
    """Every non-derived file under `root`, in a stable order.

    Sorted by POSIX-relative path rather than by `rglob`'s filesystem order,
    because the fingerprint has to be identical on two machines that walk the
    same tree in different orders.
    """
    excluded = {(root / e).resolve() for e in exclude}
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if not path.is_file():
            continue
        if path.suffix in _SKIP_SUFFIXES or any(d in path.parts for d in _SKIP_DIRS):
            continue
        if any(parent in excluded for parent in (path, *path.parents)):
            continue
        yield path


def _hash_tree(digest, root: Path, exclude: tuple[str, ...] = ()) -> None:
    for path in _iter_files(root, exclude):
        # The NAME goes in as well as the bytes: renaming a module changes
        # behaviour (it changes what imports resolve) without changing content.
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")


def aircraft_source_dirs(aircraft) -> list[Path]:
    """Every package directory that contributes code to this aircraft.

    The MRO, not just `type(aircraft)`, because an experiment package is a
    SUBCLASS of the sample living in its own directory (`aircraft/vtail_span300/`
    over `aircraft/vtail_sample/`). Fingerprinting only the subclass would miss
    every change to the aeroplane it inherits, which is most of the aeroplane.
    """
    dirs: list[Path] = []
    for klass in type(aircraft).__mro__:
        if klass is object:
            continue
        try:
            source = Path(inspect.getfile(klass)).resolve()
        except (TypeError, OSError):  # a class with no source file on disk
            continue
        parent = source.parent
        if parent not in dirs:
            dirs.append(parent)
    return dirs


def mission_key(mission) -> str:
    """Canonical JSON for a MissionSpec's VALUES.

    Values rather than the file, because the GUI's New Run dialog rewrites
    `missions/<name>.py` from its form every time it queues a run: the same
    filename can carry a different wind speed, and the checkpoint directory is
    named from that filename.

    `notes` is included even though it cannot change a solve. It is one string,
    and a fingerprint that a reader has to reason about ("does this field count?")
    is a fingerprint that will eventually be wrong.
    """
    if dataclasses.is_dataclass(mission):
        data = dataclasses.asdict(mission)
    else:  # a duck-typed mission; fall back to its public attributes
        data = {k: v for k, v in vars(mission).items() if not k.startswith("_")}
    return json.dumps(data, sort_keys=True, default=str)


@functools.lru_cache(maxsize=1)
def _package_digest() -> bytes:
    """The model half of the fingerprint, computed once per process.

    Caching here is not only for speed (the walk is ~5 s on a Windows-mounted
    filesystem, and it is wanted at least twice per run). It is also the more
    CORRECT reading: the model code this process is running was fixed at import,
    so re-reading the files later could produce a digest describing source the
    process is not executing. One job per process is what the GUI does anyway —
    `gui/runner.py` is a queue over QProcess — and the CLI is one run per
    invocation.
    """
    digest = hashlib.sha256()
    _hash_tree(digest, _PKG, exclude=NON_MODEL)
    return digest.digest()


def model_fingerprint(aircraft, mission) -> str:
    """A short hex digest of (model code + shipped data + aircraft + mission).

    Short because it names a directory a human has to read in a path; 12 hex
    characters is 48 bits, which against the handful of models one project holds
    is not a collision risk worth trading legibility for.
    """
    digest = hashlib.sha256()
    digest.update(b"planeopt-model-fingerprint-v1\0")
    digest.update(_package_digest())
    for directory in aircraft_source_dirs(aircraft):
        digest.update(b"aircraft\0")
        _hash_tree(digest, directory)
    digest.update(b"mission\0")
    digest.update(mission_key(mission).encode("utf-8"))
    return digest.hexdigest()[:12]
