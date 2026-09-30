#!/usr/bin/env bash
# Record the terminal scenes used in the demo video (writes demo/raw/*.cast).
# Requires: asciinema, a filled .env (loaded by codeguard itself; nothing is echoed).
set -euo pipefail
cd "$(dirname "$0")/../.."
unset NO_COLOR
export PATH="$PWD/.venv/bin:$PATH" TERM=xterm-256color COLORTERM=truecolor FORCE_COLOR=1
REC="${ASCIINEMA:-asciinema} rec --overwrite -q --cols 120 --rows 32 -i 2"
T=demo/tools/type_and_run.py
PY=.venv/bin/python

scene="${1:-all}"
if [[ $scene == all || $scene == setup ]]; then
  $REC -c "$PY $T 'codeguard doctor' 'pytest -q'" demo/raw/01_setup.cast
fi
if [[ $scene == all || $scene == run ]]; then
  $REC -c "$PY $T \"codeguard run '${DEMO_TASK:-Write roman_to_int(s: str) -> int that converts a valid Roman numeral (I to MMMCMXCIX) to an integer.}'\"" demo/raw/02_run.cast
fi
if [[ $scene == all || $scene == broken ]]; then
  $REC -c "$PY $T 'codeguard check examples/broken_add.py'" demo/raw/03_broken.cast
fi
if [[ $scene == all || $scene == insecure ]]; then
  $REC -c "$PY $T 'codeguard check examples/insecure_eval.py'" demo/raw/04_insecure.cast
fi
if [[ $scene == repair ]]; then
  # Second live task — Nemotron's first draft sometimes misses a Unicode edge case,
  # which exercises the evidence-driven repair loop.
  $REC -c "$PY $T \"codeguard run 'Write slugify(text: str) -> str that lowercases, replaces runs of non-alphanumeric characters with a single hyphen, and strips leading/trailing hyphens.'\"" demo/raw/05_repair.cast
fi
