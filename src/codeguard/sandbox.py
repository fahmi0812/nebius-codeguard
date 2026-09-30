"""Nebius Token Factory Sandboxes via the official Contree SDK.

Docs:
- https://docs.tokenfactory.nebius.com/sandboxes/overview
- https://docs.tokenfactory.nebius.com/sandboxes/sdk/python_sdk/getting-started

``ContreeSync()`` reads ``NEBIUS_API_KEY`` and ``NEBIUS_PROJECT_ID`` from the
environment (``config.py`` loads ``.env``) and targets the Token Factory
Sandboxes endpoint by default.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings

WORKDIR = "/tmp/codeguard"

# Runs every ``test_*`` function in solution.py, reports each one, and exits
# non-zero if any test fails or none exist. Output format is parsed by
# ``gates.parse_test_summary``.
TEST_HARNESS = '''import sys, traceback
import solution
tests = [(n, getattr(solution, n)) for n in sorted(dir(solution))
         if n.startswith("test_") and callable(getattr(solution, n))]
if not tests:
    print("NO_TESTS: solution.py defines no test_* functions")
    sys.exit(3)
failed = 0
for name, fn in tests:
    try:
        fn()
        print("ok   ", name)
    except Exception:
        failed += 1
        print("FAIL ", name)
        traceback.print_exc()
if failed:
    print(f"FAILED {failed}/{len(tests)} tests")
    sys.exit(1)
print(f"PASS {len(tests)} tests")
'''


@dataclass
class RunResult:
    exit_code: int | None
    stdout: str
    stderr: str
    raw: dict[str, Any] = field(default_factory=dict)
    duration_s: float | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def make_contree_sync(settings: Settings):
    """Build ContreeSync; credentials come from NEBIUS_API_KEY / NEBIUS_PROJECT_ID env."""
    from contree_sdk import ContreeSync

    if not settings.project_id:
        raise RuntimeError("NEBIUS_PROJECT_ID missing — Contree requires the Project header")
    return ContreeSync()


class SandboxClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = make_contree_sync(self.settings)
        return self._client

    def run(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        files: dict[str, bytes] | None = None,
        cwd: str | None = None,
        timeout: float = 120,
    ) -> RunResult:
        """Run one command in a fresh disposable sandbox from ``settings.sandbox_image``."""
        started = time.monotonic()
        try:
            image = self.client.images.use(self.settings.sandbox_image)
            result = image.run(
                command, args=args or [], files=files, cwd=cwd, timeout=timeout
            ).wait()
            return RunResult(
                exit_code=result.exit_code,
                stdout=_text(result.stdout),
                stderr=_text(result.stderr),
                raw={"image": self.settings.sandbox_image},
                duration_s=time.monotonic() - started,
            )
        except Exception as exc:  # noqa: BLE001
            return RunResult(
                exit_code=None,
                stdout="",
                stderr=f"sandbox error: {type(exc).__name__}: {exc}",
                raw={"error": type(exc).__name__},
                duration_s=time.monotonic() - started,
            )

    def run_python(self, code: str) -> RunResult:
        return self.run("python", ["-c", code])

    def run_write_test(self, *, source: str, timeout: float = 120) -> RunResult:
        """Upload ``source`` as solution.py + a harness, run every ``test_*`` function."""
        files = {
            f"{WORKDIR}/solution.py": source.encode("utf-8"),
            f"{WORKDIR}/run_tests.py": TEST_HARNESS.encode("utf-8"),
        }
        return self.run("python", ["run_tests.py"], files=files, cwd=WORKDIR, timeout=timeout)
