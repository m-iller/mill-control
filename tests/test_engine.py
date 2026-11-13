"""Движок на формулах из модели, без зашитой физики."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from millrepair.engine import (
    calculate,
    reliability_curve,
    residual_fraction,
)
from millrepair.io_json import load_default_model, model_from_json, model_to_json
from millrepair.model import (
    FailureMode,
    Formula,
    MeasurementPoint,
    Model,
    RegimePeriod,
    Symbol,
    Unit,
    validate_model,
)


def _symbol(
    kind: str, name: str, value: float | None = None, expression: str | None = None
) -> Symbol:
    formula = Formula(expression) if expression is not None else None
    return Symbol(kind=kind, name=name, value=value, formula=formula)


def _mode(name: str, **expressions: str) -> FailureMode:
    return FailureMode(
        name=name,
        formulas={role: Formula(expression) for role, expression in expressions.items()},
    )


def _weibull_model(extra_mode: FailureMode | None = None) -> Model:
    modes = [
        _mode(
            "износ",
            wear_rate="k",
            residual="(measured - consumed) if has_measurement else (R0 - consumed)",
            t_det="R / v",
            eta="t_det / gamma(1 + 1/beta)",
            reliability="exp(-(t/eta)**beta)",
            t_fail="eta * (-log(eps))**(1/beta)",
        )
    ]
    units = [Unit(name="Узел A", failure_modes=modes)]
    if extra_mode is not None:
        units.append(Unit(name="Узел B", failure_modes=[extra_mode]))
    return Model(
        name="синтетика",
        symbols=[
            _symbol("parameter", "k", 0.01),
            _symbol("parameter", "R0", 100),
            _symbol("parameter", "beta", 2),
            _symbol("parameter", "eps", 0.05),
            _symbol("regime", "x", 1),
        ],
        units=units,
    )


def test_t_fail_matches_analytical_weibull() -> None:
    result = calculate(_weibull_model())
    beta = 2.0
    eps = 0.05
    t_det = 100.0 / 0.01
    eta = t_det / math.gamma(1 + 1 / beta)
    expected = eta * (-math.log(eps)) ** (1 / beta)
    mode = result.units[0].modes[0]
    assert mode.error is None
    assert mode.t_det == pytest.approx(t_det)
    assert mode.eta == pytest.approx(eta)
    assert mode.t_fail == pytest.approx(expected)
    assert result.units[0].t == pytest.approx(expected)
    grid = np.array([0.0, expected])
    curve = reliability_curve(mode, grid)
    assert curve is not None
    assert curve[0] == pytest.approx(1.0)
    assert curve[1] == pytest.approx(eps, rel=1e-8)
    fraction = residual_fraction(mode, np.array([0.0, t_det / 2, t_det]))
    assert fraction is not None
    assert fraction[0] == pytest.approx(1.0)
    assert fraction[1] == pytest.approx(0.5)
    assert fraction[2] == pytest.approx(0.0, abs=1e-8)


def test_bad_mode_does_not_stop_the_other() -> None:
    broken = _mode(
        "сломан",
        wear_rate="1 +",
        residual="1",
        t_det="R / v",
        eta="t_det",
        reliability="exp(-t/eta)",
        t_fail="eta",
    )
    result = calculate(_weibull_model(broken))
    assert result.units[0].error is None
    assert result.units[0].t is not None
    assert result.units[1].error
    assert "синтаксическая" in result.units[1].error


def test_measurement_and_history_reduce_residual() -> None:
    model = _weibull_model()
    model.units[0].failure_modes[0].measurement_quantity = "толщина"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=100)
    result = calculate(
        model,
        measurements=[
            MeasurementPoint(
                measured_at=start,
                unit_name="Узел A",
                quantity="толщина",
                value=80,
            )
        ],
        periods=[RegimePeriod(start=start, end=end, values={"x": 1})],
        as_of=end,
    )
    mode = result.units[0].modes[0]
    # v = 0.01, за 100 ч израсходовано 1, замер 80.
    assert mode.consumed == pytest.approx(1.0)
    assert mode.R == pytest.approx(79.0)


def test_seed_file_matches_package_data() -> None:
    from importlib.resources import files

    packaged = files("millrepair.data").joinpath("default_model.json").read_text(encoding="utf-8")
    seed = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("seed", "default_model.json")
        .read_text(encoding="utf-8")
    )
    assert packaged == seed


def test_default_model_is_consistent_and_spread() -> None:
    model = load_default_model()
    assert validate_model(model) == []
    again = model_from_json(model_to_json(model))
    assert [item.name for item in again.symbols] == [item.name for item in model.symbols]
    assert again.units[0].failure_modes[0].formulas["wear_rate"].expression == (
        model.units[0].failure_modes[0].formulas["wear_rate"].expression
    )
    result = calculate(model)
    assert result.errors == []
    times = []
    for unit in result.units:
        assert unit.error is None
        assert unit.t is not None and unit.t > 0
        times.append(unit.t)
    assert max(times) / min(times) >= 1.5
    assert result.Q is not None and result.Q > model.setting("Q_min")
    eps = model.setting("eps")
    mode = result.units[0].modes[0]
    curve = reliability_curve(mode, np.array([0.0, mode.t_fail]))
    assert curve is not None
    assert curve[0] == pytest.approx(1.0, abs=1e-8)
    assert curve[1] == pytest.approx(eps, rel=1e-5)
