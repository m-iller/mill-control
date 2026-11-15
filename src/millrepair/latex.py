"""Формула-строка в математическую запись (подмножество LaTeX для mathtext).

``k_l * A * (G/G0)**a_l`` превращается в дробь со степенью и индексами.
Здесь только текст: картинку из него делает ``ui/formula_view.py``.
Разбор идёт тем же ``ast``, что и в вычислителе, ничего не выполняется.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from millrepair.expr import ExpressionError, _parse

__all__ = [
    "ROLE_LHS",
    "FormulaLayout",
    "expression_layout",
    "expression_to_latex",
    "name_to_latex",
]

# Левая часть формул вида отказа: чему равно выражение каждой роли.
ROLE_LHS: dict[str, str] = {
    "wear_rate": "v",
    "residual": "R",
    "t_det": r"t_{\mathrm{det}}",
    "eta": r"\eta",
    "reliability": "P(t)",
    "t_fail": r"t_{\mathrm{fail}}",
}

_GREEK: dict[str, str] = {
    "alpha": r"\alpha",
    "beta": r"\beta",
    "gamma": r"\gamma",
    "delta": r"\delta",
    "eps": r"\varepsilon",
    "epsilon": r"\varepsilon",
    "zeta": r"\zeta",
    "eta": r"\eta",
    "theta": r"\theta",
    "kappa": r"\kappa",
    "lam": r"\lambda",
    "lambda": r"\lambda",
    "mu": r"\mu",
    "nu": r"\nu",
    "xi": r"\xi",
    "rho": r"\rho",
    "sigma": r"\sigma",
    "tau": r"\tau",
    "phi": r"\varphi",
    "chi": r"\chi",
    "psi": r"\psi",
    "omega": r"\omega",
    "Gamma": r"\Gamma",
    "Delta": r"\Delta",
    "Theta": r"\Theta",
    "Lambda": r"\Lambda",
    "Sigma": r"\Sigma",
    "Phi": r"\Phi",
    "Psi": r"\Psi",
    "Omega": r"\Omega",
}

# Приоритеты: чем больше число, тем крепче связь.
_P_TERNARY, _P_COMPARE, _P_ADD, _P_MUL, _P_UNARY, _P_POW, _P_ATOM = range(7)

_NAMED_FUNCTIONS: dict[str, str] = {
    "log": r"\ln",
    "log10": r"\lg",
    "sin": r"\sin",
    "cos": r"\cos",
    "tanh": r"\tanh",
    "min": r"\min",
    "max": r"\max",
    "gamma": r"\Gamma",
    "clip": r"\mathrm{clip}",
}

_COMPARE: dict[type, str] = {
    ast.Eq: "=",
    ast.NotEq: r"\neq",
    ast.Lt: "<",
    ast.LtE: r"\leq",
    ast.Gt: ">",
    ast.GtE: r"\geq",
}

_HEAD = re.compile(r"^([A-Za-z]+?)(\d*)$")


@dataclass
class FormulaLayout:
    """Запись формулы для показа.

    ``rows`` — пары «выражение, условие». Одна строка с пустым условием —
    обычная формула. Несколько строк — кусочная запись с фигурной скобкой:
    так показывается тернарный оператор ``a if cond else b``.
    """

    lhs: str
    rows: list[tuple[str, str]]

    @property
    def piecewise(self) -> bool:
        return len(self.rows) > 1

    def inline(self) -> str:
        """Вся формула одной строкой, без фигурной скобки."""
        prefix = f"{self.lhs} = " if self.lhs else ""
        if not self.piecewise:
            return prefix + self.rows[0][0]
        parts = []
        for body, condition in self.rows:
            parts.append(body + r"\ \ " + (condition or r"\mathrm{иначе}"))
        return prefix + r";\quad ".join(parts)


def _escape(text: str) -> str:
    return text.replace("_", r"\_")


def _word(text: str) -> str:
    """Одна буква — курсив переменной, слово — прямой шрифт."""
    if text in _GREEK:
        return _GREEK[text]
    if len(text) == 1:
        return text
    return r"\mathrm{" + _escape(text) + "}"


def name_to_latex(name: str) -> str:
    """Имя величины: греческие буквы и нижние индексы.

    ``sigma_H_nom`` → σ с индексом «H, nom», ``mu0`` → μ₀, ``dTheta_nom`` → ΔΘ
    с индексом. Имена из длинных слов (``has_measurement``) остаются словами.
    """
    parts = [part for part in name.split("_") if part]
    if not parts:
        return _word(name)
    head, subs = parts[0], list(parts[1:])
    match = _HEAD.match(head)
    letters, digits = (match.group(1), match.group(2)) if match else (head, "")
    if letters in _GREEK:
        base = _GREEK[letters]
    elif len(letters) > 1 and letters[0] == "d" and letters[1:] in _GREEK:
        base = r"\Delta " + _GREEK[letters[1:]]
    elif len(letters) == 1:
        base = letters
    elif len(letters) == 2 and letters[1].islower() and letters[1] != letters[0]:
        # Ra, Cw, Qv, kG читаются как буква с индексом.
        base = letters[0]
        subs.insert(0, letters[1])
    elif len(letters) == 2 and letters[1].isupper():
        base = letters[0]
        subs.insert(0, letters[1])
    else:
        # Слово целиком: measured, consumed, has_measurement.
        return r"\mathrm{" + _escape(name) + "}"
    if digits:
        # Ra1 — это R с индексом «a1», а mu0 — μ с индексом «0».
        if len(letters) == 2 and letters not in _GREEK and subs:
            subs[0] = subs[0] + digits
        else:
            subs.insert(0, digits)
    if not subs:
        return base
    rendered = []
    for sub in subs:
        if sub.isdigit() or len(sub) == 1:
            rendered.append(sub)
        elif sub in _GREEK:
            rendered.append(_GREEK[sub])
        else:
            rendered.append(r"\mathrm{" + _escape(sub) + "}")
    return base + "_{" + ",".join(rendered) + "}"


def _number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    text = repr(float(value))
    if "e" in text or "E" in text:
        mantissa, exponent = text.lower().split("e")
        power = str(int(exponent))
        if mantissa.endswith(".0"):
            mantissa = mantissa[:-2]
        if mantissa == "1":
            return "10^{" + power + "}"
        return mantissa.replace(".", "{,}") + r" \cdot 10^{" + power + "}"
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", "{,}")


def _paren(text: str) -> str:
    return r"\left(" + text + r"\right)"


class _Writer:
    def write(self, node: ast.AST, *, small: bool = False, nested: bool = False) -> tuple[str, int]:
        """Вернуть запись и её приоритет. ``small`` — мы внутри степени или индекса."""
        if isinstance(node, ast.Constant):
            text = _number(node.value)
            return text, (_P_MUL if r"\cdot" in text else _P_ATOM)
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return r"\pi", _P_ATOM
            if node.id == "e":
                return r"\mathrm{e}", _P_ATOM
            return name_to_latex(node.id), _P_ATOM
        if isinstance(node, ast.UnaryOp):
            operand = self.wrap(node.operand, _P_UNARY, small=small, nested=nested)
            sign = "-" if isinstance(node.op, ast.USub) else "+"
            return sign + operand, _P_UNARY
        if isinstance(node, ast.BinOp):
            return self._binop(node, small, nested)
        if isinstance(node, ast.Compare):
            parts = [self.wrap(node.left, _P_ADD, small=small, nested=nested)]
            for op, right in zip(node.ops, node.comparators, strict=True):
                parts.append(_COMPARE.get(type(op), "?"))
                parts.append(self.wrap(right, _P_ADD, small=small, nested=nested))
            return " ".join(parts), _P_COMPARE
        if isinstance(node, ast.IfExp):
            body = self.wrap(node.body, _P_COMPARE, small=small, nested=nested)
            orelse = self.wrap(node.orelse, _P_COMPARE, small=small, nested=nested)
            test = self._condition(node.test)
            text = body + r"\ \mathrm{если}\ " + test + r"\ \mathrm{иначе}\ " + orelse
            return text, _P_TERNARY
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return self._call(node, small, nested)
        raise ExpressionError(f"конструкция {type(node).__name__} не показывается")

    def wrap(
        self, node: ast.AST, minimum: int, *, small: bool = False, nested: bool = False
    ) -> str:
        text, priority = self.write(node, small=small, nested=nested)
        return _paren(text) if priority < minimum else text

    def _condition(self, node: ast.AST) -> str:
        """Условие тернарного оператора. Голое имя-флаг читается как «≠ 0»."""
        text, _priority = self.write(node)
        if isinstance(node, ast.Name):
            return text + r" \neq 0"
        return text

    def _binop(self, node: ast.BinOp, small: bool, nested: bool = False) -> tuple[str, int]:
        op = node.op
        if isinstance(op, ast.Add):
            left = self.wrap(node.left, _P_ADD, small=small, nested=nested)
            right = self.wrap(node.right, _P_ADD, small=small, nested=nested)
            return f"{left} + {right}", _P_ADD
        if isinstance(op, ast.Sub):
            left = self.wrap(node.left, _P_ADD, small=small, nested=nested)
            right = self.wrap(node.right, _P_MUL, small=small, nested=nested)
            return f"{left} - {right}", _P_ADD
        if isinstance(op, ast.Mult):
            left = self.wrap(node.left, _P_MUL, small=small, nested=nested)
            right = self.wrap(node.right, _P_MUL, small=small, nested=nested)
            if right.startswith(("-", "+")):
                right = _paren(right)
            return rf"{left} \cdot {right}", _P_MUL
        if isinstance(op, ast.Div):
            if small:
                # В показателе степени дробь в строку: 1/β читается лучше мелкой дроби.
                left = self.wrap(node.left, _P_MUL, small=True)
                right = self.wrap(node.right, _P_UNARY, small=True)
                if isinstance(node.right, ast.BinOp):
                    right = _paren(self.write(node.right, small=True)[0])
                return f"{left}/{right}", _P_MUL
            # Внешняя дробь крупная, вложенные — обычные, иначе формула расползается.
            command = r"\frac" if nested else r"\dfrac"
            numerator, _ = self.write(node.left, nested=True)
            denominator, _ = self.write(node.right, nested=True)
            return command + "{" + numerator + "}{" + denominator + "}", _P_ATOM
        if isinstance(op, ast.Pow):
            base, priority = self.write(node.left, small=small, nested=nested)
            # Индекс и степень у одной буквы допустимы, у дроби и суммы нужны скобки.
            if priority < _P_ATOM or isinstance(node.left, (ast.BinOp, ast.UnaryOp)):
                base = _paren(base)
            elif isinstance(node.left, ast.Constant) and base.startswith("10^"):
                base = _paren(base)
            exponent, _ = self.write(node.right, small=True)
            return "{" + base + "}^{" + exponent + "}", _P_POW
        raise ExpressionError("операция не показывается")

    def _call(self, node: ast.Call, small: bool, nested: bool = False) -> tuple[str, int]:
        name = node.func.id  # type: ignore[union-attr]
        args = node.args
        if name == "sqrt" and len(args) == 1:
            return r"\sqrt{" + self.write(args[0], nested=nested)[0] + "}", _P_ATOM
        if name == "abs" and len(args) == 1:
            return r"\left|" + self.write(args[0], small=small, nested=nested)[
                0
            ] + r"\right|", _P_ATOM
        if name == "exp" and len(args) == 1:
            inner = self.write(args[0], small=small, nested=nested)[0]
            return r"\exp" + _paren(inner), _P_ATOM
        if name == "pow" and len(args) == 2:
            fake = ast.BinOp(left=args[0], op=ast.Pow(), right=args[1])
            return self._binop(fake, small, nested)
        head = _NAMED_FUNCTIONS.get(name, r"\mathrm{" + _escape(name) + "}")
        inner = r",\ ".join(self.write(arg, small=small, nested=nested)[0] for arg in args)
        return head + _paren(inner), _P_ATOM


def _branches(node: ast.AST, writer: _Writer) -> list[tuple[str, str]]:
    """Разложить цепочку ``a if c1 else b if c2 else d`` на строки."""
    rows: list[tuple[str, str]] = []
    current = node
    while isinstance(current, ast.IfExp):
        body, _ = writer.write(current.body)
        rows.append((body, r"\mathrm{если}\ " + writer._condition(current.test)))
        current = current.orelse
    tail, _ = writer.write(current)
    if rows:
        rows.append((tail, r"\mathrm{иначе}"))
    else:
        rows.append((tail, ""))
    return rows


def expression_layout(expression: str, lhs: str = "") -> FormulaLayout:
    """Разобрать формулу в запись для показа.

    ``lhs`` — готовая левая часть (уже в LaTeX), например от ``name_to_latex``.
    Ошибка разбора — ``ExpressionError``, как у вычислителя.
    """
    tree = _parse(expression)
    return FormulaLayout(lhs=lhs, rows=_branches(tree.body, _Writer()))


def expression_to_latex(expression: str, lhs: str = "") -> str:
    """Формула одной строкой LaTeX."""
    return expression_layout(expression, lhs).inline()
