import pytest

from codeguard.gates import (
    count_test_functions,
    decide,
    parse_test_summary,
    preflight,
    quality_scan,
    security_scan,
    static_security_scan,
)

CLEAN = '''
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 3

def test_add_zero():
    assert add(0, 0) == 0
'''


def test_clean_source_has_no_findings():
    assert security_scan(CLEAN) == []
    assert quality_scan(CLEAN) == []
    assert preflight(CLEAN) == []


@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("x = eval('1+1')", "eval()"),
        ("exec('print(1)')", "exec()"),
        ("m = __import__('os')", "__import__()"),
        ("code = compile('1', 'f', 'eval')", "compile()"),
        ("import subprocess", "subprocess"),
        ("from socket import socket", "socket"),
        ("import urllib.request", "urllib.request"),
        ("import os\nos.system('ls')", "os.system()"),
        ("import os\nos.remove('x')", "os.remove()"),
        ("from os import system", "os.system"),
        ("import builtins\nbuiltins.eval('1')", "builtins.eval()"),
    ],
)
def test_security_scan_blocks_dangerous_code(snippet, expected):
    hits = security_scan(snippet)
    assert hits, snippet
    assert any(expected in h for h in hits), hits


def test_security_scan_reports_line_numbers():
    hits = security_scan("a = 1\nb = eval('2')\n")
    assert hits == ["blocked call: eval() (line 2)"]


def test_raw_pattern_rm_rf_is_blocked_even_in_strings():
    assert any("rm -rf /" in h for h in security_scan("CMD = 'rm -rf /'\n"))


def test_safe_lookalikes_are_not_blocked():
    src = (
        "import ast, os.path, json\n"
        "def evaluate(x):\n    return ast.literal_eval(x)\n"
        "def f(obj):\n    return obj.eval()\n"
        "def g():\n    return os.path.join('a', 'b')\n"
    )
    assert security_scan(src) == []


def test_syntax_error_falls_back_to_substring_scan():
    src = "def broken(:\n    return eval('1')\n"
    hits = security_scan(src)
    assert "blocked pattern: eval(" in hits
    assert quality_scan(src)[0].startswith("syntax error")


def test_backwards_compatible_alias():
    assert static_security_scan is security_scan


def test_count_test_functions_top_level_only():
    src = "def test_a(): pass\nasync def test_b(): pass\ndef helper(): pass\nclass C:\n    def test_m(self): pass\n"
    assert count_test_functions(src) == 2
    assert count_test_functions("def (:") == 0


def test_quality_scan_requires_tests():
    assert quality_scan("def f():\n    return 1\n") == ["too few test_* functions: 0 < 1"]
    assert quality_scan(CLEAN, min_tests=3) == ["too few test_* functions: 2 < 3"]
    assert quality_scan("   \n") == ["empty source"]


@pytest.mark.parametrize(
    "exit_code, stdout, expected",
    [
        (0, "ok    test_a\nok    test_b\nPASS 2 tests\n", (2, 0, 2, True)),
        (1, "ok    test_a\nFAIL  test_b\nFAILED 1/2 tests\n", (1, 1, 2, False)),
        (1, "PASS 2 tests\n", (2, 0, 2, False)),  # PASS line but non-zero exit
        (3, "NO_TESTS: solution.py defines no test_* functions\n", (None, None, None, False)),
        (None, "", (None, None, None, False)),
        (0, "PASS 0 tests\n", (0, 0, 0, False)),
    ],
)
def test_parse_test_summary(exit_code, stdout, expected):
    s = parse_test_summary(exit_code, stdout)
    assert (s.passed, s.failed, s.total, s.ok) == expected


def test_decide_accepts_only_with_full_evidence():
    r = decide(exit_code=0, source=CLEAN, test_ok=True)
    assert r.accepted is True
    assert r.reasons == []
    assert [c[0] for c in r.checks] == ["security scan", "quality scan", "sandbox exit code", "tests passed"]
    assert all(ok for _, ok, _ in r.checks)


def test_decide_rejects_non_zero_exit_and_failed_tests():
    r = decide(exit_code=1, source=CLEAN, test_ok=False)
    assert not r.accepted
    assert r.reasons == ["non-zero exit: 1", "tests failed"]


def test_decide_rejects_missing_exit_code():
    r = decide(exit_code=None, source=CLEAN, test_ok=True)
    assert not r.accepted
    assert "no exit code (sandbox did not run)" in r.reasons


def test_decide_rejects_insecure_code_even_if_tests_pass():
    src = CLEAN + "\nvalue = eval('1')\n"
    r = decide(exit_code=0, source=src, test_ok=True)
    assert not r.accepted
    assert any("eval" in reason for reason in r.reasons)


def test_decide_rejects_when_tests_not_ok_even_with_exit_zero():
    r = decide(exit_code=0, source=CLEAN, test_ok=False)
    assert not r.accepted
    assert r.reasons == ["tests failed"]
