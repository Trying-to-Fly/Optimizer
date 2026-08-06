# Code review — `macos-support` (commit 66ffbf7)

> **Resolved 2026-08-06.** All eight findings are fixed on `main`, after the
> branch was merged. Two details of the report did not survive contact with the
> merged tree and are corrected below: `test_prop_screen.py` holds eight tests
> rather than seven (six need the checkpoint, two do not), and the review's
> "Verified clean" list predates the two commits that landed after 66ffbf7.
>
> What each fix is pinned by, since a fix with no test is a fix until the next
> session: finding 1 by a seven-row truth table over `_make_fork_safe_on_macos`
> plus an end-to-end check that a shell-pinned, NumPy-first process is not
> refused; finding 2 by an offscreen dialog test counting runs-directory scans
> across spinner ticks, and by a probe count over `plan_parallel`; finding 4 by
> a fork test that runs on any POSIX host rather than only on a Mac; finding 6
> by running the suite with the checkpoint moved away. Findings 3, 5, 7 and 8
> are covered by the existing tests they touch, plus a new `test_fonts.py` for
> the consolidated `fonts.mono`. The loose `> 0` assertion this report calls out
> in the macOS forked-child test is now bounded, so a unit slip fails it.
>
> Each fix was confirmed to fail before it was applied — the truth-table rows
> were run against the old branch, the fork hook was unplugged, the scan was put
> back in the tick handler, and the checkpoint was hidden.

Reviewed 2026-08-06. Scope: the committed diff vs `main` ("The app ran on a Mac; none of the guards that stop it eating the machine did"). Method: 8 finder angles followed by 4 adversarial verifier passes; every finding below survived an attempt to refute it against the committed code. Uncommitted working-tree edits (a concurrent work stream) were excluded; `cli.py` and `solve.py` were verified via `git show HEAD:`.

## Confirmed findings, ranked

### 1. MEDIUM — deliberately presetting the safe `VECLIB_MAXIMUM_THREADS=1` is misclassified as unsafe
`src/planeopt/__init__.py:79` (corroborated independently by two finder angles and two verifiers)

```python
if preset is not None and preset != "1":
    _FORK_SAFE_MACOS = None   # deliberate override — caller's risk
else:
    _FORK_SAFE_MACOS = in_time
```

A preset of exactly `"1"` — the safe value, and the exact remedy `check_parallel`'s own error message prescribes — falls through to the `in_time` check. If NumPy was imported before planeopt (embedding, notebook, array-first test), `_FORK_SAFE_MACOS` becomes `False`: `solve.check_parallel` (line 1221) refuses parallel runs and `planeopt info` (cli.py:471) reports "UNSAFE — NumPy was imported before planeopt" — even though Accelerate honoured the env var from process start, so forks are genuinely safe.

Verified truth table: `(preset="1", numpy-first) → False` (refuse) while `(preset="4", numpy-first) → None` (allow). So the safe preset is refused and an unsafe preset is waved through. The failure loop is closed: the RuntimeError tells the user to set `VECLIB_MAXIMUM_THREADS=1` before launching, which is what they already did — following the error's advice can never clear it. This contradicts the function's own docstring ("a deliberate override … is left alone"). Failure direction is conservative (refusal, not segfault), which caps severity at medium.

**Fix:** treat `preset == "1"` as a deliberate override (`None`), or as verified-safe (`True`). Default CLI/GUI paths are unaffected (planeopt always imports first there).

Secondary, lower: on non-Accelerate NumPy builds (conda/OpenBLAS) the pin is a no-op and numpy-first also yields `False`, over-refusing a width that would work. Backend introspection would be a precision improvement, not a safety requirement — the `True` state is sound for the Accelerate failure it guards.

### 2. LOW — the GUI budget spinner re-does heavy work on every tick
`src/planeopt/gui/newrun.py:305-321`, `src/planeopt/memory.py:655`

`plan_parallel` with default args calls `machine_ram()` twice plus `swap_gb()`; the spinner's `valueChanged` handler already holds those numbers and passes none of them, so each tick performs three full Mach probes where one would do. Verifier's addition (found while checking, confirmed by inspection but not itself adversarially verified): the same handler's `observed_peak_gb(self._runs_dir)` call (newrun.py:306) re-lists the runs directory and re-parses up to 25 `run.json` files from disk on every tick — that dwarfs the redundant syscalls. Accept `available_gb`/`ceiling_gb` params at the call sites and cache/debounce the observed-peak scan.

### 3. LOW — `mach_host_self()` leaks a host-port uref per `_vm_statistics` call
`src/planeopt/memory.py:193`

Called per invocation, never `mach_port_deallocate`'d; each call adds a user-reference on the host-port name, ~3× per spinner tick via finding 2. Materiality is bounded — XNU saturates urefs at ~65535 rather than growing kernel memory — so this is hygiene, not a leak that hurts. **Fix:** cache the host port in `_libsystem()` (trivial, and eliminates the amplification).

### 4. LOW — per-instance `os.register_at_fork` hook can never be unregistered
`src/planeopt/memory.py:322`

`_FootprintSampler.__init__` registers a bound method per instance; Python has no unregister API, so every instance (and its lock) is pinned for process lifetime and the interpreter's fork-hook list grows. Production creates exactly one instance (`_SAMPLER`, line 374), so the leak today is confined to tests (test_memory.py:208) and future multi-instance use. **Fix:** one module-level hook that resets the `_SAMPLER` singleton.

### 5. LOW — `peak_rss_gb` interleaves three mechanisms where `machine_ram` got a clean dispatch
`src/planeopt/memory.py:536`

Darwin sampler-first, an inline win32 ctypes block (540-569), then a shared POSIX rusage branch whose darwin/linux unit difference is a ternary at line 584 — while the same commit refactored `machine_ram` (line 435) into per-platform dispatch. The hazard is demonstrated, not hypothetical: the kB-vs-bytes slip this very commit fixed lived in that shared branch, invisible because it reads as "the Linux path"; the only test of the macOS forked-child fallback asserts merely `> 0`, which a 10⁶-scale slip passes. Cleanup, not a fix — the current code is correct, and the new bounds/cross-check tests mitigate.

### 6. LOW — module-wide skip in `test_prop_screen.py` permanently disables two artifact-free tests
`tests/test_prop_screen.py:43`

The conditional `pytestmark` skips all seven tests when the gitignored `runs/` checkpoint is missing, but two tests (lines 129, 142) never touch `INCUMBENT` — so every fresh checkout and all CI permanently skip the `discrete_screen` declaration invariants. The guard itself is a strict improvement over main (skip instead of collection error); only its granularity is wrong. Note when narrowing: `INCUMBENT = None` (line 42) is currently safe *only because* of the blanket skip — re-guard the screen fixture.

### 7. LOW — `_CAN_CLEAR_REFS` makes a test environment-sensitive (and it writes to `/proc` mid-suite)
`tests/test_memory.py:292-307`

`_CAN_CLEAR_REFS` is named like a capability probe but is a bare `sys.platform == "linux"` check; in `test_the_macos_probes_are_unreachable_off_macos` the "linux" param's expectation reduces to "whatever the real host does". On a Linux host with masked `/proc` (container) or kernel < 4.0, `reset_peak_rss()` returns `False` while the test expects `True` — spurious failure unrelated to the test's subject. The monkeypatch of `memory.sys.platform` patches the real `sys` module globally, so on a Linux host the "linux" param performs a *real* `clear_refs` write, resetting the test process's RSS watermark mid-suite. **Fix:** assert only what the test owns (macOS probes unreachable; `is False` for win32) and drop the constant. Note: the success-path test at line 151 shares the same environment sensitivity.

### 8. LOW — cleanup batch (all verified behavior-preserving)

- **`gui/window.py:289-293`** hand-builds the mono QFont that `views._mono(9)` and `render3d.mono_font(9)` already build, and imports `MONO_FAMILIES` via `views` instead of `gui/fonts.py`; `views.py:32` and `render3d.py:530` each hold an independent `fonts.families()` result. This is the exact drift this commit healed (main had `'Monospace'` vs `'monospace'`). Caveats: window.py's block predates this commit (adjacent-scope cleanup), and `fonts.py` is deliberately Qt-free — a shared helper there pulls in QtGui (harmless; QtGui ≠ QtWidgets) and should say so.
- **`memory.py:584`** — `1024**3` re-spells the module's own `GB` constant (line 56) in the darwin `ru_maxrss` scale (bytes on darwin — semantics verified). Touch up the adjacent `1024**2/1024**3` comment alongside.
- **`memory.py:168-182`** — `_libsystem`'s hand-rolled tri-value cache (missing attr / `False` sentinel / lib, plus `lib or None` — a no-op since CDLL is always truthy) is observably equivalent to `@functools.cache` returning lib-or-None, including negative caching; tests swap `_cached = None` pokes for documented `cache_clear()`. `functools` needs adding to memory.py's imports; the existing test structure already clears inside the patched context, so ordering is fine.
- **`memory.py:349-350`** — the pid check in `_FootprintSampler._run` is unreachable (fork carries only the calling thread; every `_pid` writer stores the running process's own pid). It is also incoherent as defense-in-depth: it checks the pid *after* taking `self._lock`, so a hypothetical ghost thread would deadlock on the inherited lock before reaching it. Delete; the real protections are the at-fork hook and `peak_gb`'s pre-lock guard.
- **`memory.py:318`** — `_started` is always exactly `self._thread is not None` (writers at 318/328/335 in lockstep, single reader at 366). Drop it and guard on the thread; if applied, assign the thread before any dependence (there is a benign first-restart window between lines 335 and 340).
- **`tests/test_memory.py`** — five pasted darwin skipif markers with two drifted reason strings (176, 203, 212, 245 vs 275). Hoist one module-level `darwin_only`, matching `needs_fork` in test_parallel.py:13. Scope to this file (test_parallel.py:138 has its own inline straggler).

## Refuted candidates (do not act on these)

- **"Collapse `_FORK_SAFE_MACOS` to a boolean / add a public accessor"** — the tri-state is load-bearing: `None` deliberately encodes "not macOS OR caller's own override, leave alone" vs `True` "verified pinned in time", the docstring argues for it explicitly, and `test_parallel.py:148` depends on `is True` to verify the pin actually landed. The finder's "three modules, scattered" was wrong: two production call sites, both testing the one actionable state. (Fixing finding 1 changes which bucket `preset=="1"` lands in — it does not require restructuring the flag.)
- **"`_FootprintSampler` thread polls 4×/sec in idle GUI sessions"** — the GUI never starts the sampler; only `reset_peak_rss()` does, called solely from the CLI battery loop (solve.py:1407), and the GUI runs solves in QProcess subprocesses. Residual cost is 4 microsecond-scale syscalls/sec during an active solve. A `stop()` would be nice-to-have hygiene only.
- **"`cli.py:496` darwin swap clause violates memory.py's platform ownership"** — one presentation string in a diagnostics command; no computation keys off it, correct on every platform, speculative drift only.

## Verified clean (checked, no action)

No circular imports; the macOS forked-child fallback path is correct; ctypes struct layouts match the Mach headers; no stale font stack remains; `needs_fork` marker correctly reused; test byte-size literals match file idiom; `cli.info()` clause-building acceptable.
