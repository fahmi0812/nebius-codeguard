"""Deliberately buggy module: CodeGuard must REJECT it (a test fails in the sandbox)."""


def add(a: int, b: int) -> int:
    return a - b  # bug: should be a + b


def test_add_positive():
    assert add(2, 3) == 5


def test_add_zero():
    assert add(0, 0) == 0
