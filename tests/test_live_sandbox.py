"""Optional live test against Nebius Token Factory Sandboxes (spawns 1 sandbox).

Deselected by default (see ``addopts`` in pyproject). Run with:

    set -a; source .env; set +a
    pytest -m live
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_PROJECT_ID")),
        reason="NEBIUS_API_KEY / NEBIUS_PROJECT_ID not set",
    ),
]


def test_sandbox_runs_example_tests():
    from codeguard.config import get_settings
    from codeguard.gates import decide, parse_test_summary
    from codeguard.sandbox import SandboxClient

    settings = get_settings(load_env=False)
    source = (ROOT / "examples/good_fizzbuzz.py").read_text()
    run = SandboxClient(settings).run_write_test(source=source)
    summary = parse_test_summary(run.exit_code, run.stdout)
    assert run.exit_code == 0, run.stderr
    assert summary.ok and summary.total == 4
    assert decide(exit_code=run.exit_code, source=source, test_ok=summary.ok).accepted
