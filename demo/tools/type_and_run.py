#!/usr/bin/env python3
"""Demo helper: 'type' a shell command with a fake prompt, then run it.

Used inside `asciinema rec` so recordings look like a human at a terminal.
Never pass commands that print environment variables.
"""
import subprocess
import sys
import time

PROMPT = "\x1b[1;32mcodeguard-demo\x1b[0m:\x1b[1;34m~/nebius-codeguard\x1b[0m$ "


def main() -> int:
    rc = 0
    for cmd in sys.argv[1:]:
        sys.stdout.write(PROMPT)
        sys.stdout.flush()
        time.sleep(0.6)
        for ch in cmd:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(0.03)
        time.sleep(0.5)
        sys.stdout.write("\n")
        sys.stdout.flush()
        rc = subprocess.call(cmd, shell=True)
        time.sleep(1.5)
    sys.stdout.write(PROMPT)
    sys.stdout.flush()
    time.sleep(1.0)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
