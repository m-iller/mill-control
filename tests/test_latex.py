"""Математическая запись формул и числа для показа."""

from __future__ import annotations

import pytest
from matplotlib.mathtext import MathTextParser

from millrepair.expr import ExpressionError
from millrepair.io_json import load_default_model
from millrepair.latex import ROLE_LHS, expression_layout, expression_to_latex, name_to_latex
from millrepair.util import format_display


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("G", "G"),
        ("k_l", "k_{l}"),
        ("mu0", r"\mu_{0}"),
        ("phi", r"\varphi"),
        ("sigma_H_nom", r"\sigma_{H,\mathrm{nom}}"),
        ("dTheta_nom", r"\Delta \Theta_{\mathrm{nom}}"),
        ("Ra1", r"R_{\mathrm{a1}}"),
        ("Cw", "C_{w}"),
        ("has_measurement", r"\mathrm{has\_measurement}"),
    ],
)
def test_names_get_greek_letters_and_indices(name: str, expected: str) -> None:
    assert name_to_latex(name) == expected


def test_division_becomes_fraction_and_power_keeps_brackets() -> None:
    assert expression_to_latex("a / b") == r"\dfrac{a}{b}"
    assert expression_to_latex("(a + b)**2") == r"{\left(a + b\right)}^{2}"
    assert expression_to_latex("a - (b - c)") == r"a - \left(b - c\right)"
    assert expression_to_latex("-(a + b) * c") == r"-\left(a + b\right) \cdot c"
    assert expression_to_latex("x**(1/n)") == "{x}^{1/n}"
    assert expression_to_latex("sqrt(a / b)", "y") == r"y = \sqrt{\dfrac{a}{b}}"


def test_numbers_use_decimal_comma_and_powers_of_ten() -> None:
    assert expression_to_latex("0.8 * x") == r"0{,}8 \cdot x"
    assert expression_to_latex("1.5e-6 * x") == r"1{,}5 \cdot 10^{-6} \cdot x"


def test_ternary_is_split_into_piecewise_rows() -> None:
    layout = expression_layout("a if flag else b if x < 1 else c", "R")
    assert layout.piecewise
    assert [body for body, _condition in layout.rows] == ["a", "b", "c"]
    assert layout.rows[0][1].endswith(r"\mathrm{flag} \neq 0")
    assert layout.rows[-1][1] == r"\mathrm{иначе}"
    assert layout.inline().startswith("R = ")


def test_broken_formula_raises_expression_error() -> None:
    with pytest.raises(ExpressionError):
        expression_to_latex("1 +")


def test_every_default_formula_is_drawable() -> None:
    """Все формулы модели по умолчанию разбираются mathtext без ошибок."""
    parser = MathTextParser("path")
    model = load_default_model()
    pieces: list[str] = []
    for symbol in model.symbols:
        if symbol.formula is not None:
            layout = expression_layout(symbol.formula.expression, name_to_latex(symbol.name))
            pieces.append(layout.lhs)
            pieces.extend(part for row in layout.rows for part in row if part)
    for unit in model.units:
        for mode in unit.failure_modes:
            for role, formula in mode.formulas.items():
                layout = expression_layout(formula.expression, ROLE_LHS[role])
                pieces.append(layout.lhs)
                pieces.extend(part for row in layout.rows for part in row if part)
    assert len(pieces) > 40
    for piece in pieces:
        parser.parse(f"${piece}$")


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (14866.8, 5, "14 867"),
        (0.014461, 4, "0,01446"),
        (72, 4, "72"),
        (6.72639e-05, 4, "6,726·10⁻⁵"),
        (-3.5, 4, "−3,5"),
        (0, 4, "0"),
        (None, 4, "—"),
        (float("inf"), 4, "∞"),
    ],
)
def test_format_display(value, digits: int, expected: str) -> None:
    assert format_display(value, digits) == expected
