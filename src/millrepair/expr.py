"""Безопасный вычислитель формул.

Формула — строка вроде ``k_l * A * (G/G0)**a``. Разбор делает модуль ``ast``,
вычисление идёт по белому списку узлов. Встроенный ``eval`` не используется.

Выражение считается и на числах, и на массивах numpy (кривые по времени ``t``).
"""

from __future__ import annotations

import ast
import math
import threading
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy import special

ALLOWED_FUNCTIONS: tuple[str, ...] = (
    "exp",
    "log",
    "log10",
    "sqrt",
    "abs",
    "min",
    "max",
    "pow",
    "gamma",
    "sin",
    "cos",
    "tanh",
    "clip",
)
CONSTANTS: tuple[str, ...] = ("pi", "e")

_CONSTANT_VALUES: dict[str, float] = {"pi": math.pi, "e": math.e}


class ExpressionError(Exception):
    """Формула не разбирается или не считается."""


class UnsafeExpression(ExpressionError):
    """В формуле есть конструкция вне белого списка."""


def _np_min(*args: Any) -> Any:
    if not args:
        raise ExpressionError("min() без аргументов")
    result = args[0]
    for item in args[1:]:
        result = np.minimum(result, item)
    return result


def _np_max(*args: Any) -> Any:
    if not args:
        raise ExpressionError("max() без аргументов")
    result = args[0]
    for item in args[1:]:
        result = np.maximum(result, item)
    return result


_FUNCTIONS: dict[str, Any] = {
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "min": _np_min,
    "max": _np_max,
    "pow": np.power,
    "gamma": special.gamma,
    "sin": np.sin,
    "cos": np.cos,
    "tanh": np.tanh,
    "clip": np.clip,
}

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}

_CMPOPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Call,
    ast.Compare,
    ast.IfExp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def _parse(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ExpressionError("пустая формула")
    if "\x00" in expression:
        raise UnsafeExpression("недопустимый символ в формуле")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"синтаксическая ошибка: {exc.msg}") from exc
    if not isinstance(tree, ast.Expression):
        raise UnsafeExpression("ожидается выражение, а не набор операторов")
    _reject_unsafe(tree)
    return tree


def _reject_unsafe(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if "__" in node.id:
                raise UnsafeExpression(f"имя «{node.id}» запрещено")
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise UnsafeExpression("разрешены только числовые константы")
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise UnsafeExpression("вызов разрешён только по имени функции из белого списка")
            if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
                raise UnsafeExpression("именованные и распакованные аргументы запрещены")
            if node.func.id not in _FUNCTIONS:
                raise UnsafeExpression(f"функция «{node.func.id}» не разрешена")
            continue
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpression(f"конструкция {type(node).__name__} запрещена")


def free_names(expression: str) -> set[str]:
    """Имена, которые выражение читает из контекста.

    Константы ``pi`` и ``e`` и имена вызванных разрешённых функций сюда не входят.
    """
    tree = _parse(expression)
    names: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    names -= called & set(_FUNCTIONS)
    names -= set(_CONSTANT_VALUES)
    return names


def _compile_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        value = node.value
        return lambda _ctx, _value=value: _value

    if isinstance(node, ast.Name):
        if node.id in _CONSTANT_VALUES:
            value = _CONSTANT_VALUES[node.id]
            return lambda _ctx, _value=value: _value
        name = node.id

        def _load(ctx: Mapping[str, Any], _name: str = name) -> Any:
            try:
                return ctx[_name]
            except KeyError as exc:
                raise ExpressionError(f"не задано имя «{_name}»") from exc

        return _load

    if isinstance(node, ast.UnaryOp):
        operand = _compile_node(node.operand)
        if isinstance(node.op, ast.USub):
            return lambda ctx, _operand=operand: -_operand(ctx)
        if isinstance(node.op, ast.UAdd):
            return lambda ctx, _operand=operand: +_operand(ctx)
        raise UnsafeExpression("унарная операция не разрешена")

    if isinstance(node, ast.BinOp):
        left = _compile_node(node.left)
        right = _compile_node(node.right)
        try:
            op = _BINOPS[type(node.op)]
        except KeyError as exc:
            raise UnsafeExpression("арифметическая операция не разрешена") from exc
        return lambda ctx, _left=left, _right=right, _op=op: _op(_left(ctx), _right(ctx))

    if isinstance(node, ast.Compare):
        left = _compile_node(node.left)
        ops = []
        for op_node in node.ops:
            try:
                ops.append(_CMPOPS[type(op_node)])
            except KeyError as exc:
                raise UnsafeExpression("сравнение не разрешено") from exc
        comparators = [_compile_node(item) for item in node.comparators]

        def _compare(
            ctx: Mapping[str, Any],
            _left: Any = left,
            _ops: list[Any] = ops,
            _comparators: list[Any] = comparators,
        ) -> Any:
            current = _left(ctx)
            accumulated = None
            for op, comp in zip(_ops, _comparators, strict=True):
                nxt = comp(ctx)
                piece = op(current, nxt)
                accumulated = piece if accumulated is None else accumulated & piece
                current = nxt
            return accumulated

        return _compare

    if isinstance(node, ast.IfExp):
        test = _compile_node(node.test)
        body = _compile_node(node.body)
        orelse = _compile_node(node.orelse)

        def _ifexp(
            ctx: Mapping[str, Any],
            _test: Any = test,
            _body: Any = body,
            _orelse: Any = orelse,
        ) -> Any:
            cond = _test(ctx)
            # На массиве считаются обе ветви: np.where не умеет ленивость.
            # На скаляре невыбранная ветвь не считается.
            if isinstance(cond, np.ndarray):
                return np.where(cond, _body(ctx), _orelse(ctx))
            if cond:
                return _body(ctx)
            return _orelse(ctx)

        return _ifexp

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise UnsafeExpression("вызов запрещён")
        func = _FUNCTIONS[node.func.id]
        args = [_compile_node(arg) for arg in node.args]

        def _call(ctx: Mapping[str, Any], _func: Any = func, _args: list[Any] = args) -> Any:
            return _func(*(_arg(ctx) for _arg in _args))

        return _call

    raise UnsafeExpression(f"конструкция {type(node).__name__} запрещена")


def compile_expression(expression: str) -> Any:
    """Скомпилировать формулу в функцию ``ctx -> значение``."""
    with _LOCK:
        cached = _CACHE.get(expression)
        if cached is not None:
            return cached
    tree = _parse(expression)
    function = _compile_node(tree.body)
    with _LOCK:
        _CACHE[expression] = function
    return function


def _finalize(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            value = value.item()
        else:
            return value
    if isinstance(value, np.generic):
        value = value.item()
    return value


def evaluate(expression: str, variables: Mapping[str, Any] | None = None) -> Any:
    """Вычислить формулу. Скалярный результат — число или bool Python, массив — ndarray."""
    context = dict(variables or {})
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        value = compile_expression(expression)(context)
    return _finalize(value)
