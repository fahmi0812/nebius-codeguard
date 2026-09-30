"""Quality / security gates — evidence-first accept/reject.

The gates are deliberately simple and deterministic (no model involved):

* **security scan** – AST-based policy for self-contained toy tasks: blocks
  ``eval``/``exec``/``compile``/``__import__``, process / network / native
  modules (``subprocess``, ``socket``, ``ctypes`` …), destructive ``os`` calls
  (``os.system``, ``os.remove`` …) and a few raw string patterns
  (``rm -rf /``). If the source cannot be parsed, a substring fallback is used.
* **quality scan** – source must parse and define at least one ``test_*``
  function.
* **execution evidence** – the sandbox must have run (exit code present), exit
  with ``0`` and report passing tests.

A patch is accepted only if every gate passes.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

# Calls that execute arbitrary code or bypass the import policy.
BLOCKED_CALLS = frozenset({"eval", "exec", "compile", "__import__", "breakpoint"})

# Modules that give process, network, native-code or unsafe-deserialisation access.
BLOCKED_MODULES = frozenset(
    {
        "subprocess",
        "socket",
        "ctypes",
        "pickle",
        "marshal",
        "shutil",
        "multiprocessing",
        "pty",
        "requests",
        "urllib",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
    }
)

# ``os.<name>`` calls that spawn processes or delete things.
BLOCKED_OS_CALLS = frozenset(
    {
        "system",
        "popen",
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "kill",
        "fork",
        "execv",
        "execve",
        "execl",
        "execlp",
        "execvp",
        "spawnl",
        "spawnv",
        "startfile",
    }
)

# Raw patterns checked on the text itself (also used as fallback when AST parsing fails).
FORBIDDEN_PATTERNS = (
    "eval(",
    "exec(",
    "__import__(",
    "subprocess.",
    "os.system(",
    "rm -rf /",
)
RAW_ALWAYS = ("rm -rf /",)

PASS_RE = re.compile(r"^PASS (\d+) tests\s*$", re.MULTILINE)
FAILED_RE = re.compile(r"^FAILED (\d+)/(\d+) tests\s*$", re.MULTILINE)


@dataclass
class GateReport:
    accepted: bool
    reasons: list[str]
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    """(gate name, passed, detail) — for display."""


@dataclass
class TestSummary:
    passed: int | None
    failed: int | None
    total: int | None
    ok: bool


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    """Return (base, attr) for ``foo()`` -> (None, 'foo'), ``a.b()`` -> ('a', 'b')."""
    func = node.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        base = func.value.id if isinstance(func.value, ast.Name) else None
        return base, func.attr
    return None, None


def _substring_scan(source: str, patterns: tuple[str, ...]) -> list[str]:
    lower = source.lower()
    return [f"blocked pattern: {p}" for p in patterns if p.lower() in lower]


def security_scan(source: str) -> list[str]:
    """Return a list of security findings (empty list = clean)."""
    hits: list[str] = _substring_scan(source, RAW_ALWAYS)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Can't reason about structure: fall back to raw text patterns.
        extra = [h for h in _substring_scan(source, FORBIDDEN_PATTERNS) if h not in hits]
        return hits + extra

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    hits.append(f"blocked import: {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                hits.append(f"blocked import: {node.module} (line {node.lineno})")
            elif root == "os":
                for alias in node.names:
                    if alias.name in BLOCKED_OS_CALLS:
                        hits.append(f"blocked import: os.{alias.name} (line {node.lineno})")
        elif isinstance(node, ast.Call):
            base, name = _call_name(node)
            if base is None and name in BLOCKED_CALLS:
                hits.append(f"blocked call: {name}() (line {node.lineno})")
            elif base == "os" and name in BLOCKED_OS_CALLS:
                hits.append(f"blocked call: os.{name}() (line {node.lineno})")
            elif base == "builtins" and name in BLOCKED_CALLS:
                hits.append(f"blocked call: builtins.{name}() (line {node.lineno})")
    return hits


# Backwards-compatible name used by earlier drafts / smoke test.
static_security_scan = security_scan


def count_test_functions(source: str) -> int:
    """Number of top-level ``def test_*`` functions (0 if the source does not parse)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(
        1
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def quality_scan(source: str, *, min_tests: int = 1) -> list[str]:
    """Return quality findings: syntax errors, missing tests."""
    if not source.strip():
        return ["empty source"]
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax error: line {exc.lineno}: {exc.msg}"]
    n = count_test_functions(source)
    if n < min_tests:
        return [f"too few test_* functions: {n} < {min_tests}"]
    return []


def preflight(source: str, *, min_tests: int = 1) -> list[str]:
    """Static checks that must pass *before* code is sent to a sandbox."""
    return security_scan(source) + quality_scan(source, min_tests=min_tests)


def parse_test_summary(exit_code: int | None, stdout: str) -> TestSummary:
    """Parse the sandbox harness output (``PASS n tests`` / ``FAILED f/t tests``)."""
    m_pass = PASS_RE.search(stdout or "")
    m_fail = FAILED_RE.search(stdout or "")
    if m_fail:
        failed, total = int(m_fail.group(1)), int(m_fail.group(2))
        return TestSummary(passed=total - failed, failed=failed, total=total, ok=False)
    if m_pass:
        n = int(m_pass.group(1))
        return TestSummary(passed=n, failed=0, total=n, ok=exit_code == 0 and n > 0)
    return TestSummary(passed=None, failed=None, total=None, ok=False)


def decide(
    *,
    exit_code: int | None,
    source: str,
    test_ok: bool,
    min_tests: int = 1,
) -> GateReport:
    """Combine static scans and sandbox evidence into an ACCEPT/REJECT report."""
    reasons: list[str] = []
    checks: list[tuple[str, bool, str]] = []

    sec = security_scan(source)
    reasons.extend(sec)
    checks.append(("security scan", not sec, "; ".join(sec) or "no blocked patterns"))

    qual = quality_scan(source, min_tests=min_tests)
    reasons.extend(qual)
    checks.append(
        ("quality scan", not qual, "; ".join(qual) or f"{count_test_functions(source)} test_* functions")
    )

    if exit_code is None:
        detail = "no exit code (sandbox did not run)"
        reasons.append(detail)
        checks.append(("sandbox exit code", False, detail))
    elif exit_code != 0:
        detail = f"non-zero exit: {exit_code}"
        reasons.append(detail)
        checks.append(("sandbox exit code", False, detail))
    else:
        checks.append(("sandbox exit code", True, "exit 0"))

    if not test_ok:
        reasons.append("tests failed")
    checks.append(("tests passed", test_ok, "all tests passed" if test_ok else "tests failed / not run"))

    return GateReport(accepted=not reasons and test_ok, reasons=reasons, checks=checks)
