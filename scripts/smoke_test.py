#!/usr/bin/env python3
"""Live smoke: Nemotron chat -> Contree hello -> Nemotron write-run-test -> gates.

Usage (from repo root, with .env filled):
  .venv/bin/python scripts/smoke_test.py
  .venv/bin/python scripts/smoke_test.py --skip-sandbox

Spawns at most 2 sandboxes (hello + write-run-test).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codeguard.agent import judge_evidence, propose_patch  # noqa: E402
from codeguard.config import get_settings  # noqa: E402
from codeguard.gates import decide, parse_test_summary  # noqa: E402
from codeguard.llm import smoke_completion  # noqa: E402
from codeguard.sandbox import SandboxClient  # noqa: E402

TASK = """Write a small Python module (no third-party imports, no file/network/OS access) with:
- a function `is_palindrome(s: str) -> bool` that ignores case and non-alphanumeric characters;
- at least three test functions named `test_*` that use plain `assert` statements (no pytest import).
Return the whole module in a single ```python code fence."""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-sandbox", action="store_true")
    args = p.parse_args()

    settings = get_settings()
    print("LLM base:", settings.llm_base_url)
    print("Model:", settings.nemotron_model)
    text = smoke_completion(settings)
    print("Nemotron smoke reply:", repr(text[:200]))
    print("Nemotron:", "OK" if text else "EMPTY")
    if not text:
        return 1
    if args.skip_sandbox:
        return 0

    sb = SandboxClient(settings)
    print("\n[1] Sandbox hello (image:", settings.sandbox_image + ")")
    hello = sb.run_python("print('hello from contree')")
    print("exit:", hello.exit_code, "| stdout:", repr(hello.stdout), "| stderr:", repr(hello.stderr[:300]))
    if not hello.ok:
        return 1

    print("\n[2] Nemotron writes function + tests")
    source = propose_patch(TASK, settings)
    print("----- solution.py -----\n" + source + "\n-----------------------")

    print("\n[3] Sandbox runs tests")
    run = sb.run_write_test(source=source)
    print("exit:", run.exit_code)
    print("stdout:", run.stdout[:1000])
    print("stderr:", run.stderr[:1000])
    test_ok = parse_test_summary(run.exit_code, run.stdout).ok

    print("\n[4] Gates")
    report = decide(exit_code=run.exit_code, source=source, test_ok=test_ok)
    print("gate verdict:", "ACCEPT" if report.accepted else "REJECT", report.reasons)

    evidence = f"exit_code={run.exit_code}\nstdout:\n{run.stdout[:2000]}\nstderr:\n{run.stderr[:2000]}"
    print("judge (Nemotron):", judge_evidence(evidence, settings)[:600])

    return 0 if report.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
