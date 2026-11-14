"""Калибровка коэффициента износа по двум замерам."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pytest import approx

from millrepair.calibration import calibrate_rate
from millrepair.model import (
    FailureMode,
    Formula,
    MeasurementPoint,
    Model,
    RegimePeriod,
    Symbol,
    Unit,
)


def _model() -> Model:
    formulas = {
        "wear_rate": "k * G",
        "residual": "R0 - consumed",
        "t_det": "R / v",
        "eta": "t_det",
        "reliability": "exp(-(t/eta))",
        "t_fail": "eta",
    }
    return Model(
        name="калибровка",
        symbols=[
            Symbol(kind="regime", name="G", value=10),
            Symbol(kind="parameter", name="k", value=0.001),
            Symbol(kind="parameter", name="R0", value=50),
        ],
        units=[
            Unit(
                name="Узел",
                failure_modes=[
                    FailureMode(
                        name="износ",
                        measurement_quantity="толщина",
                        rate_parameter="k",
                        formulas={
                            role: Formula(expression) for role, expression in formulas.items()
                        },
                    )
                ],
            )
        ],
    )


def test_least_squares_recovers_linear_coefficient() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=100)
    result = calibrate_rate(
        _model(),
        "Узел",
        "износ",
        [
            MeasurementPoint(start, "Узел", "толщина", 50),
            MeasurementPoint(end, "Узел", "толщина", 30),
        ],
        [RegimePeriod(start, end, {"G": 10})],
    )
    assert result.ok, result.message
    assert result.parameter == "k"
    assert result.value == approx(0.02, rel=1e-4)
    assert result.comment == "откалибровано по замерам от 2026-01-01 до 2026-01-05"


def test_calibration_needs_two_measurements() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = calibrate_rate(
        _model(),
        "Узел",
        "износ",
        [MeasurementPoint(start, "Узел", "толщина", 50)],
        [],
    )
    assert result.ok is False
    assert "два" in result.message
