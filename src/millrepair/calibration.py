"""Калибровка коэффициента скорости износа по истории замеров.

Коэффициент ищется методом наименьших квадратов: предсказанное падение
измеряемой величины между соседними замерами сравнивается с фактом.
Новая версия параметра создаётся вызывающим кодом.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from millrepair.engine import consumed_between
from millrepair.expr import free_names
from millrepair.model import MeasurementPoint, Model, RegimePeriod

# Коэффициент ищется в пределах exp(±_LOG_SPAN) от текущего значения.
_LOG_SPAN = 30.0


@dataclass
class CalibrationResult:
    ok: bool
    message: str
    parameter: str = ""
    value: float | None = None
    previous: float | None = None
    comment: str = ""


def calibrate_rate(
    model: Model,
    unit_name: str,
    mode_name: str,
    measurements: list[MeasurementPoint],
    periods: list[RegimePeriod] | None = None,
) -> CalibrationResult:
    mode = _find_mode(model, unit_name, mode_name)
    if mode is None:
        return CalibrationResult(False, "Вид отказа не найден.")
    parameter_name = mode.rate_parameter.strip()
    if not parameter_name:
        return CalibrationResult(False, "У вида отказа не задан коэффициент скорости износа.")
    symbol = model.symbol(parameter_name)
    if symbol is None or symbol.value is None:
        return CalibrationResult(False, f"В модели нет параметра «{parameter_name}».")
    wear = mode.formulas.get("wear_rate")
    if wear is None:
        return CalibrationResult(False, "Нет формулы скорости износа.")
    try:
        names = free_names(wear.expression)
    except Exception as exc:
        return CalibrationResult(False, str(exc))
    if parameter_name not in names:
        return CalibrationResult(
            False,
            f"Коэффициент «{parameter_name}» не входит в формулу скорости износа.",
        )
    points = [
        item
        for item in measurements
        if item.unit_name == unit_name and item.quantity == mode.measurement_quantity
    ]
    points.sort(key=lambda item: item.measured_at)
    # Рост величины между замерами означает замену детали: такой промежуток
    # износ не описывает и в подгонку не входит.
    pairs = [
        (left, right)
        for left, right in zip(points, points[1:], strict=False)
        if right.measured_at > left.measured_at and right.value <= left.value
    ]
    if len(pairs) < 1:
        return CalibrationResult(
            False,
            "Нужны хотя бы два замера одной величины в разные моменты, "
            "между которыми величина не выросла.",
        )
    initial = float(symbol.value)
    if not np.isfinite(initial) or initial <= 0:
        return CalibrationResult(
            False, f"Коэффициент «{parameter_name}» должен быть положительным числом."
        )

    # Подгоняется не сам коэффициент, а логарифм его отношения к текущему
    # значению. Иначе шаг и допуски least_squares не зависят от масштаба, и
    # коэффициенты порядка 1e7 (N0) или 1e-9 (k_b) подгоняются неточно или
    # не сдвигаются вовсе.
    def residuals(candidate: np.ndarray) -> np.ndarray:
        coefficient = initial * float(np.exp(candidate[0]))
        errors = []
        for left, right in pairs:
            consumed = consumed_between(
                model,
                unit_name,
                mode_name,
                left.measured_at,
                right.measured_at,
                periods,
                overrides={parameter_name: coefficient},
            )
            predicted = left.value - consumed
            errors.append(predicted - right.value)
        return np.asarray(errors, dtype=float)

    try:
        fitted = least_squares(
            residuals,
            x0=np.array([0.0], dtype=float),
            bounds=(-_LOG_SPAN, _LOG_SPAN),
            x_scale=1.0,
            ftol=1e-14,
            xtol=1e-14,
            gtol=1e-14,
        )
    except Exception as exc:
        return CalibrationResult(False, f"Калибровка не сошлась: {exc}")
    if not fitted.success or not np.all(np.isfinite(fitted.fun)):
        return CalibrationResult(False, "Калибровка не сошлась.")
    value = initial * float(np.exp(fitted.x[0]))
    start = points[0].measured_at.date().isoformat()
    finish = points[-1].measured_at.date().isoformat()
    comment = f"откалибровано по замерам от {start} до {finish}"
    return CalibrationResult(
        ok=True,
        message=(f"{parameter_name}: {symbol.value:.6g} → {value:.6g}. {comment}."),
        parameter=parameter_name,
        value=value,
        previous=float(symbol.value),
        comment=comment,
    )


def _find_mode(model: Model, unit_name: str, mode_name: str):
    for unit in model.units:
        if unit.name != unit_name:
            continue
        for mode in unit.failure_modes:
            if mode.name == mode_name:
                return mode
    return None
