"""Тесты безопасного вычислителя формул."""

from __future__ import annotations

import math

import numpy as np
import pytest

from millrepair.expr import (
    CONSTANTS,
    ExpressionError,
    UnsafeExpression,
    evaluate,
    free_names,
)


def test_arithmetic_and_power_associativity() -> None:
    assert evaluate("1 + 2 * 3", {}) == 7
    assert evaluate("1/4", {}) == pytest.approx(0.25)
    assert evaluate("-3 + 5", {}) == 2
    assert evaluate("2**3**2", {}) == 512
    assert evaluate("(2**3)**2", {}) == 64


def test_functions_and_constants() -> None:
    assert evaluate("sqrt(4) + abs(-3)", {}) == pytest.approx(5)
    assert evaluate("log(e)", {}) == pytest.approx(1)
    assert evaluate("log10(100)", {}) == pytest.approx(2)
    assert evaluate("exp(0)", {}) == pytest.approx(1)
    assert evaluate("sin(0) + cos(0)", {}) == pytest.approx(1)
    assert evaluate("tanh(0)", {}) == pytest.approx(0)
    assert evaluate("pow(2, 3)", {}) == pytest.approx(8)
    assert evaluate("min(3, 1, 2) + max(3, 1, 2)", {}) == pytest.approx(4)
    assert evaluate("clip(-1, 0, 1)", {}) == pytest.approx(0)
    assert evaluate("clip(2, 0, 1)", {}) == pytest.approx(1)
    assert evaluate("gamma(1 + 1/2)", {}) == pytest.approx(math.gamma(1.5))
    assert evaluate("pi", {}) == pytest.approx(math.pi)
    assert set(CONSTANTS) == {"pi", "e"}


def test_comparisons_and_ternary() -> None:
    assert evaluate("1 < 2 <= 2", {}) is True
    assert evaluate("3 < 2", {}) is False
    assert evaluate("1 == 1", {}) is True
    assert evaluate("1 != 2", {}) is True
    assert evaluate("a if c else b", {"a": 10, "b": 20, "c": 1}) == 10
    assert evaluate("a if c else b", {"a": 10, "b": 20, "c": 0}) == 20
    # Скалярная ветвь не вычисляется: деление на ноль в отброшенной ветви не мешает.
    assert evaluate("1 if 1 else (1/0)", {}) == 1


def test_numpy_arrays() -> None:
    values = np.array([0.0, 1.0, 4.0])
    out = evaluate("sqrt(x) + 1", {"x": values})
    assert isinstance(out, np.ndarray)
    np.testing.assert_allclose(out, np.array([1.0, 2.0, 3.0]))
    clipped = evaluate("clip(x, 0, 1)", {"x": np.array([-1.0, 0.5, 3.0])})
    np.testing.assert_allclose(clipped, np.array([0.0, 0.5, 1.0]))
    chosen = evaluate("a if c else b", {"a": values, "b": values + 5, "c": np.array([1, 0, 1])})
    np.testing.assert_allclose(chosen, np.array([0.0, 6.0, 4.0]))
    curve = evaluate("exp(-(t/10)**2)", {"t": np.array([0.0, 10.0])})
    np.testing.assert_allclose(curve, np.array([1.0, math.exp(-1.0)]))


def test_free_names() -> None:
    assert free_names("k_l * A * (G/G0)**a + pi") == {"k_l", "A", "G", "G0", "a"}
    assert free_names("exp(-(t/eta)**beta)") == {"t", "eta", "beta"}
    assert free_names("max(0, 1 - lam / lam_kr) + v_b0") == {"lam", "lam_kr", "v_b0"}
    assert free_names("sqrt(pi) + e") == set()
    assert "sqrt" not in free_names("sqrt(x) + y")


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",
        "(1).__class__",
        "lambda x: x",
        "(lambda: 1)()",
        "x[0]",
        "a.b",
        "[1, 2]",
        "{1, 2}",
        "{'a': 1}",
        "(x for x in y)",
        "x and y",
        "x or y",
        "not x",
        "x // y",
        "x % y",
        "x @ y",
        "~x",
        "x << 1",
        "__name__",
        "x.__class__",
        "eval('1')",
        "exec('1')",
        "min(x, default=1)",
        "max(*xs)",
        "'text'",
        "True",
        "import os",
    ],
)
def test_forbidden_constructs(expr: str) -> None:
    with pytest.raises(ExpressionError):
        evaluate(expr, {"x": 1, "y": 2, "a": 1, "xs": 1})


def test_unsafe_is_expression_error() -> None:
    with pytest.raises(UnsafeExpression):
        free_names("obj.attr")


def test_syntax_and_missing_name() -> None:
    with pytest.raises(ExpressionError, match="синтаксическая"):
        evaluate("1 +", {})
    with pytest.raises(ExpressionError, match="не задано имя"):
        evaluate("x + 1", {})
    with pytest.raises(ExpressionError, match="пустая"):
        evaluate("   ", {})


def test_unknown_function() -> None:
    with pytest.raises(UnsafeExpression, match="не разрешена"):
        evaluate("sinus(0)", {})
