"""Insecure module: tests would pass, but CodeGuard must REJECT it before execution."""


def calculate(expression: str) -> float:
    return eval(expression)  # arbitrary code execution


def test_calculate():
    assert calculate("2 + 3") == 5
