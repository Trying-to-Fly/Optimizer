#!/bin/sh
# Drives the four arms of warm_start_experiment.py, one process each, in order.
#
# `caffeinate -dimsu` because this runs 25-45 minutes on a laptop and a lid
# close mid-arm would land in that arm's wall-clock. solve.py already brackets
# the solve with BOTH clocks (`time.time` and `time.monotonic`) so a suspension
# is detectable after the fact — this stops it happening in the first place.
#
# Stops at the first failing arm: the two warm arms read champion.json, and the
# cold control is what they are measured against, so continuing past a failure
# would produce numbers with nothing to compare them to.
set -e

STATE="${1:-docs/studies/warm_start}"
PY=".venv/bin/python"

for arm in champion bump_cold bump_inits_only bump_inits_and_options; do
    echo "=== $arm ==="
    caffeinate -dimsu "$PY" tools/bughunt/warm_start_experiment.py "$arm" "$STATE"
done

"$PY" tools/bughunt/warm_start_experiment.py report "$STATE"
