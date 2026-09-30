"""Run the sandbox test harness locally (no network) and check config handling."""
import subprocess
import sys
from pathlib import Path

import pytest

from codeguard.config import ConfigError, describe, get_settings
from codeguard.gates import parse_test_summary
from codeguard.sandbox import TEST_HARNESS, RunResult, SandboxClient

ROOT = Path(__file__).resolve().parents[1]


def run_harness(tmp_path, source):
    (tmp_path / "solution.py").write_text(source)
    (tmp_path / "run_tests.py").write_text(TEST_HARNESS)
    p = subprocess.run([sys.executable, "run_tests.py"], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


def test_harness_pass(tmp_path):
    code, out, _ = run_harness(tmp_path, (ROOT / "examples/good_fizzbuzz.py").read_text())
    assert code == 0
    s = parse_test_summary(code, out)
    assert s.ok and s.total == 4


def test_harness_failure(tmp_path):
    code, out, err = run_harness(tmp_path, (ROOT / "examples/broken_add.py").read_text())
    assert code == 1
    assert "FAIL  test_add_positive" in out and "AssertionError" in err
    s = parse_test_summary(code, out)
    assert (s.passed, s.failed, s.ok) == (1, 1, False)


def test_harness_no_tests(tmp_path):
    code, out, _ = run_harness(tmp_path, "X = 1\n")
    assert code == 3 and "NO_TESTS" in out


def test_harness_import_error(tmp_path):
    code, _, err = run_harness(tmp_path, "raise RuntimeError('boom')\n")
    assert code == 1 and "boom" in err


ENV_VARS = [
    "NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "LLM_BASE_URL", "NEMOTRON_MODEL", "NEMOTRON_JUDGE_MODEL",
    "SANDBOX_BASE_URL", "CONTREE_BASE_URL", "SANDBOX_IMAGE", "MODEL_TIMEOUT_SECONDS",
]


@pytest.fixture
def clean_env(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_settings_defaults(clean_env):
    clean_env.setenv("NEBIUS_API_KEY", "dummy-key-for-tests")
    s = get_settings(load_env=False)
    assert s.llm_base_url == "https://api.tokenfactory.nebius.com/v1"
    assert s.nemotron_model == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert s.nemotron_judge_model == s.nemotron_model
    assert s.sandbox_image == "python:3.12-slim"
    assert s.timeout == 90


def test_settings_missing_key(clean_env):
    with pytest.raises(ConfigError):
        get_settings(load_env=False)
    assert get_settings(load_env=False, require_key=False).api_key == ""


def test_settings_overrides_and_trailing_slash(clean_env):
    clean_env.setenv("NEBIUS_API_KEY", "k")
    clean_env.setenv("LLM_BASE_URL", "https://example.test/v1/")
    clean_env.setenv("NEMOTRON_MODEL", "nvidia/other")
    clean_env.setenv("MODEL_TIMEOUT_SECONDS", "15")
    s = get_settings(load_env=False)
    assert s.llm_base_url == "https://example.test/v1"
    assert s.nemotron_judge_model == "nvidia/other"
    assert s.timeout == 15


def test_bad_timeout(clean_env):
    clean_env.setenv("NEBIUS_API_KEY", "k")
    clean_env.setenv("MODEL_TIMEOUT_SECONDS", "soon")
    with pytest.raises(ConfigError):
        get_settings(load_env=False)


def test_secrets_never_in_repr_or_describe(clean_env):
    secret = "super-secret-value-123"
    clean_env.setenv("NEBIUS_API_KEY", secret)
    clean_env.setenv("NEBIUS_PROJECT_ID", "project-xyz")
    s = get_settings(load_env=False)
    assert secret not in repr(s) and secret not in str(s)
    d = describe(s)
    assert secret not in str(d) and "project-xyz" not in str(d)
    assert d["NEBIUS_API_KEY"] == "set"


def test_sandbox_client_reports_errors_as_no_exit_code(clean_env):
    clean_env.setenv("NEBIUS_API_KEY", "k")  # no project id -> client construction fails
    sb = SandboxClient(get_settings(load_env=False))
    r = sb.run_python("print(1)")
    assert isinstance(r, RunResult)
    assert r.exit_code is None and "sandbox error" in r.stderr and not r.ok
