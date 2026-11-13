"""Расчёт времён отказа, вероятности безотказной работы и технологических показателей.

Все формулы приходят из модели. Движок подставляет режим, считает производные
величины по топологическому порядку и для каждого вида отказа вычисляет
v, R, t_det, eta, P(t) и t_fail. Ошибка одной формулы помечает узел и не
останавливает остальные.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from millrepair.expr import ExpressionError, compile_expression, evaluate
from millrepair.model import (
    FORMULA_ROLES,
    DependencyError,
    FailureMode,
    MeasurementPoint,
    Model,
    RegimePeriod,
    Unit,
    analyze_dependencies,
)
from millrepair.util import as_float, hours_between, parse_datetime

_NUMERIC_CONTEXT_SKIP = {"t"}


@dataclass
class ModeCalc:
    unit: str
    mode: str
    v: float | None = None
    R: float | None = None
    t_det: float | None = None
    eta: float | None = None
    t_fail: float | None = None
    consumed: float = 0.0
    error: str | None = None
    exhausted: bool = False
    residual_expression: str = ""
    reliability_expression: str = ""
    curve_context: dict[str, float] = field(default_factory=dict)


@dataclass
class UnitCalc:
    name: str
    weight: float
    multiplicity: int | None
    t: float | None = None
    error: str | None = None
    modes: list[ModeCalc] = field(default_factory=list)


@dataclass
class CalcResult:
    regime: dict[str, float]
    Q: float | None = None
    P_prod: float | None = None
    units: list[UnitCalc] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def unit(self, name: str) -> UnitCalc | None:
        for item in self.units:
            if item.name == name:
                return item
        return None


@dataclass
class _PreparedMode:
    unit: Unit
    mode: FailureMode
    expressions: dict[str, str]
    compiled: dict[str, Any]
    error: str | None = None


class CompiledModel:
    """Формулы модели, разобранные один раз."""

    def __init__(self, model: Model) -> None:
        self.model = model
        report = analyze_dependencies(model)
        self.order = report.order
        self.graph_errors = list(report.errors)
        self._compiled: dict[str, Any] = {}
        for item in model.symbols:
            if item.kind not in {"derived", "technology"} or item.formula is None:
                continue
            try:
                self._compiled[item.name] = compile_expression(item.formula.expression)
            except ExpressionError as exc:
                message = f"{item.name}: {exc}"
                if message not in self.graph_errors:
                    self.graph_errors.append(message)
        self.modes: list[_PreparedMode] = []
        for unit in model.units:
            for mode in unit.failure_modes:
                self.modes.append(_prepare_mode(unit, mode))

    def context(
        self,
        regime: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        ctx: dict[str, Any] = {}
        errors: list[str] = []
        for item in self.model.symbols:
            if item.kind in {"regime", "parameter"} and item.value is not None:
                ctx[item.name] = item.value
        ctx.update(regime)
        if overrides:
            ctx.update(overrides)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            for name in self.order:
                function = self._compiled.get(name)
                if function is None:
                    continue
                try:
                    ctx[name] = function(ctx)
                except Exception as exc:  # формула пользователя может упасть на числах
                    errors.append(f"{name}: {exc}")
        return ctx, errors

    def wear_rate(
        self,
        prepared: _PreparedMode,
        regime: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> float:
        if prepared.error or "wear_rate" not in prepared.compiled:
            raise ExpressionError(prepared.error or "нет формулы скорости износа")
        ctx, _errors = self.context(regime, overrides)
        value = as_float(prepared.compiled["wear_rate"](ctx), "v")
        if value <= 0:
            raise ExpressionError("скорость расходования ресурса должна быть положительной")
        return value


def calculate(
    model: Model,
    *,
    regime: dict[str, float] | None = None,
    measurements: list[MeasurementPoint] | None = None,
    periods: list[RegimePeriod] | None = None,
    cycle_start: datetime | str | None = None,
    as_of: datetime | str | None = None,
) -> CalcResult:
    """Посчитать показатели при заданном режиме.

    ``regime`` заменяет текущие значения переменных режима. История замеров и
    периодов нужна для остаточного ресурса: износ интегрируется от последнего
    замера или от начала цикла до ``as_of``.
    """
    point = dict(model.regime())
    if regime:
        point.update({key: float(value) for key, value in regime.items()})
    result = CalcResult(regime=point)
    try:
        compiled = CompiledModel(model)
    except Exception as exc:
        result.errors.append(str(exc))
        return result
    result.errors.extend(compiled.graph_errors)
    moment = _as_datetime(as_of) if as_of is not None else datetime.now(timezone.utc)
    start = _as_datetime(cycle_start) if cycle_start is not None else _cycle_from_model(model)
    history = periods or []
    measures = measurements or []
    try:
        ctx, ctx_errors = compiled.context(point)
    except DependencyError as exc:
        result.errors.append(str(exc))
        ctx, ctx_errors = {}, []
    result.errors.extend(ctx_errors)
    result.Q = _optional_metric(ctx, "Q", result.errors)
    result.P_prod = _optional_metric(ctx, "P_prod", result.errors)

    for prepared in compiled.modes:
        consumed, measured, has_measurement = _resource_inputs(
            compiled,
            prepared,
            measures,
            history,
            point,
            start,
            moment,
            result.errors,
        )
        mode_result = _evaluate_mode(prepared, ctx, consumed, measured, has_measurement)
        unit_result = _ensure_unit(result, prepared.unit)
        unit_result.modes.append(mode_result)

    for unit_result in result.units:
        good = [
            mode.t_fail
            for mode in unit_result.modes
            if mode.error is None and mode.t_fail is not None
        ]
        unit_result.t = min(good) if good else None
        messages = [f"{mode.mode}: {mode.error}" for mode in unit_result.modes if mode.error]
        unit_result.error = "; ".join(messages) if messages else None
    return result


def reliability_curve(mode: ModeCalc, time: np.ndarray) -> np.ndarray | None:
    """P(t) по формуле вида отказа. ``time`` — массив часов."""
    if mode.error or not mode.reliability_expression or not mode.curve_context:
        return None
    context = dict(mode.curve_context)
    context["t"] = np.asarray(time, dtype=float)
    try:
        values = np.asarray(evaluate(mode.reliability_expression, context), dtype=float)
    except Exception:
        return None
    return values


def unit_reliability(unit: UnitCalc, time: np.ndarray) -> np.ndarray | None:
    """Вероятность узла — минимум P по видам отказа: узел жив, пока жив каждый вид."""
    curves = []
    for mode in unit.modes:
        curve = reliability_curve(mode, time)
        if curve is not None:
            curves.append(curve)
    if not curves:
        return None
    return np.min(np.vstack(curves), axis=0)


def residual_fraction(mode: ModeCalc, time: np.ndarray) -> np.ndarray | None:
    """Доля остаточного ресурса при продолжении текущего режима.

    Износ за будущее время добавляется к уже накопленному ``consumed``, остаток
    снова считается формулой модели, затем делится на остаток в нулевой момент.
    """
    if mode.error or mode.R is None or mode.R <= 0 or mode.v is None:
        return None
    if not mode.residual_expression or not mode.curve_context:
        return None
    grid = np.asarray(time, dtype=float)
    context = dict(mode.curve_context)
    context["consumed"] = mode.consumed + mode.v * grid
    context["v"] = mode.v
    try:
        remaining = np.asarray(evaluate(mode.residual_expression, context), dtype=float)
    except Exception:
        return None
    fraction = remaining / mode.R
    return np.clip(fraction, 0.0, 1.0)


def unit_residual_fraction(unit: UnitCalc, time: np.ndarray) -> np.ndarray | None:
    curves = []
    for mode in unit.modes:
        curve = residual_fraction(mode, time)
        if curve is not None:
            curves.append(curve)
    if not curves:
        return None
    return np.min(np.vstack(curves), axis=0)


def format_calc(model: Model, result: CalcResult) -> str:
    units = {item.name: item.units for item in model.symbols}
    lines = ["Расчёт при текущем режиме", "", "Режим:"]
    for name, value in result.regime.items():
        suffix = f" {units[name]}" if units.get(name) else ""
        lines.append(f"  {name} = {_fmt(value)}{suffix}")
    lines.append("")
    lines.append(f"Q = {_fmt(result.Q)}")
    lines.append(f"P_prod = {_fmt(result.P_prod)}")
    lines.append("")
    for unit in result.units:
        lines.append(f"Узел {unit.name}: t = {_fmt(unit.t)} ч")
        if unit.error:
            lines.append(f"  ошибка: {unit.error}")
        for mode in unit.modes:
            if mode.error and mode.t_fail is None:
                lines.append(f"  {mode.mode}: ошибка: {mode.error}")
                continue
            note = " ресурс исчерпан" if mode.exhausted else ""
            lines.append(
                "  "
                + " | ".join(
                    [
                        mode.mode,
                        f"v={_fmt(mode.v)}",
                        f"R={_fmt(mode.R)}",
                        f"t_det={_fmt(mode.t_det)} ч",
                        f"t_fail={_fmt(mode.t_fail)} ч",
                    ]
                )
                + note
            )
            if mode.error:
                lines.append(f"    ошибка: {mode.error}")
    if result.errors:
        lines.append("")
        lines.append("Замечания модели:")
        for error in result.errors:
            lines.append(f"  {error}")
    return "\n".join(lines)


def _prepare_mode(unit: Unit, mode: FailureMode) -> _PreparedMode:
    expressions = {role: formula.expression for role, formula in mode.formulas.items()}
    compiled: dict[str, Any] = {}
    error = None
    for role in FORMULA_ROLES:
        expression = expressions.get(role)
        if not expression or not expression.strip():
            error = f"нет формулы {role}"
            break
        try:
            compiled[role] = compile_expression(expression)
        except ExpressionError as exc:
            error = str(exc)
            break
    return _PreparedMode(
        unit=unit, mode=mode, expressions=expressions, compiled=compiled, error=error
    )


def _evaluate_mode(
    prepared: _PreparedMode,
    ctx: dict[str, Any],
    consumed: float,
    measured: float,
    has_measurement: bool,
) -> ModeCalc:
    result = ModeCalc(unit=prepared.unit.name, mode=prepared.mode.name, consumed=consumed)
    result.residual_expression = prepared.expressions.get("residual", "")
    result.reliability_expression = prepared.expressions.get("reliability", "")
    if prepared.error:
        result.error = prepared.error
        return result
    local = dict(ctx)
    local["consumed"] = consumed
    local["measured"] = measured
    local["has_measurement"] = 1.0 if has_measurement else 0.0
    try:
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            return _evaluate_mode_numbers(prepared, result, local)
    except Exception as exc:
        result.error = str(exc)
        return result


def _evaluate_mode_numbers(
    prepared: _PreparedMode,
    result: ModeCalc,
    local: dict[str, Any],
) -> ModeCalc:
    try:
        wear = as_float(prepared.compiled["wear_rate"](local), "v")
        if wear <= 0:
            raise ExpressionError("скорость расходования ресурса должна быть положительной")
        local["v"] = wear
        result.v = wear
        residual = as_float(prepared.compiled["residual"](local), "R")
        result.R = residual
        local["R"] = residual
        result.curve_context = _numeric_context(local)
        if residual <= 0:
            result.t_det = 0.0
            result.eta = 0.0
            result.t_fail = 0.0
            result.exhausted = True
            return result
        t_det = as_float(prepared.compiled["t_det"](local), "t_det")
        if t_det <= 0:
            raise ExpressionError("t_det должно быть положительным")
        local["t_det"] = t_det
        result.t_det = t_det
        eta = as_float(prepared.compiled["eta"](local), "eta")
        if eta <= 0:
            raise ExpressionError("eta должно быть положительным")
        local["eta"] = eta
        result.eta = eta
        t_fail = as_float(prepared.compiled["t_fail"](local), "t_fail")
        if t_fail < 0:
            raise ExpressionError("t_fail не может быть отрицательным")
        result.t_fail = t_fail
        result.curve_context = _numeric_context(local)
    except Exception as exc:
        result.error = str(exc)
    return result


def _resource_inputs(
    compiled: CompiledModel,
    prepared: _PreparedMode,
    measurements: list[MeasurementPoint],
    periods: list[RegimePeriod],
    regime: dict[str, float],
    cycle_start: datetime | None,
    as_of: datetime,
    errors: list[str],
) -> tuple[float, float, bool]:
    quantity = prepared.mode.measurement_quantity
    relevant = [
        item
        for item in measurements
        if item.unit_name == prepared.unit.name
        and item.quantity == quantity
        and item.measured_at <= as_of
    ]
    relevant.sort(key=lambda item: item.measured_at)
    if relevant:
        last = relevant[-1]
        origin = last.measured_at
        measured = float(last.value)
        has_measurement = True
    else:
        origin = cycle_start
        measured = 0.0
        has_measurement = False
    consumed = 0.0
    if origin is not None and origin < as_of and prepared.error is None:
        try:
            consumed = _integrate_wear(compiled, prepared, origin, as_of, periods, regime)
        except Exception as exc:
            errors.append(f"{prepared.unit.name}/{prepared.mode.name}: износ по истории: {exc}")
            consumed = 0.0
    return consumed, measured, has_measurement


def consumed_between(
    model: Model,
    unit_name: str,
    mode_name: str,
    origin: datetime,
    as_of: datetime,
    periods: list[RegimePeriod] | None = None,
    *,
    overrides: dict[str, float] | None = None,
) -> float:
    """Износ одного вида отказа за интервал. ``overrides`` подменяет параметры."""
    compiled = CompiledModel(model)
    prepared = next(
        (
            item
            for item in compiled.modes
            if item.unit.name == unit_name and item.mode.name == mode_name
        ),
        None,
    )
    if prepared is None or prepared.error:
        raise ExpressionError(prepared.error if prepared is not None else "вид отказа не найден")
    return _integrate_wear(
        compiled,
        prepared,
        origin,
        as_of,
        periods or [],
        dict(model.regime()),
        overrides,
    )


def _integrate_wear(
    compiled: CompiledModel,
    prepared: _PreparedMode,
    origin: datetime,
    as_of: datetime,
    periods: list[RegimePeriod],
    current: dict[str, float],
    overrides: dict[str, float] | None = None,
) -> float:
    """Интеграл v(u) dt. Пропуск в журнале режима считается по текущему режиму."""
    edges = {origin, as_of}
    for period in periods:
        if period.end <= origin or period.start >= as_of:
            continue
        edges.add(max(origin, period.start))
        edges.add(min(as_of, period.end))
    points = sorted(edges)
    total = 0.0
    for left, right in zip(points, points[1:], strict=False):
        if right <= left:
            continue
        regime = dict(current)
        covering = [period for period in periods if period.start <= left and period.end >= right]
        if covering:
            chosen = max(covering, key=lambda period: period.start)
            regime.update(chosen.values)
        wear = compiled.wear_rate(prepared, regime, overrides)
        total += wear * hours_between(left, right)
    return total


def _ensure_unit(result: CalcResult, unit: Unit) -> UnitCalc:
    existing = result.unit(unit.name)
    if existing is not None:
        return existing
    created = UnitCalc(name=unit.name, weight=unit.weight, multiplicity=unit.multiplicity)
    result.units.append(created)
    return created


def _optional_metric(ctx: dict[str, Any], name: str, errors: list[str]) -> float | None:
    if name not in ctx:
        return None
    try:
        return as_float(ctx[name], name)
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
        return None


def _numeric_context(ctx: dict[str, Any]) -> dict[str, float]:
    numeric: dict[str, float] = {}
    for key, value in ctx.items():
        if key in _NUMERIC_CONTEXT_SKIP:
            continue
        if isinstance(value, np.ndarray):
            continue
        try:
            numeric[key] = as_float(value, key)
        except (TypeError, ValueError):
            continue
    return numeric


def _cycle_from_model(model: Model) -> datetime | None:
    if not model.cycle_start:
        return None
    return parse_datetime(model.cycle_start)


def _as_datetime(value: datetime | str) -> datetime:
    return parse_datetime(value)


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if not math.isfinite(value):
        return "∞" if value > 0 else "—"
    return f"{value:.6g}"
