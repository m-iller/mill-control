"""Синтетические задачи оптимизатора: синхронизация и недопустимость."""

from __future__ import annotations

import pytest

from millrepair.model import FailureMode, Formula, Model, Symbol, Unit
from millrepair.optimize import optimize

pytestmark = pytest.mark.slow


def _mode(name: str, wear: str) -> FailureMode:
    expressions = {
        "wear_rate": wear,
        "residual": "10",
        "t_det": "R / v",
        "eta": "t_det",
        "reliability": "exp(-(t/eta))",
        "t_fail": "eta",
    }
    return FailureMode(
        name=name,
        formulas={role: Formula(expression) for role, expression in expressions.items()},
    )


def _sync_model() -> Model:
    return Model(
        name="синхронизация",
        criterion="B",
        symbols=[
            Symbol(
                kind="regime", name="u", value=0.3, min_value=0.2, max_value=0.8, adjustable=True
            ),
            Symbol(kind="parameter", name="delta", value=2000),
            Symbol(kind="parameter", name="Q_min", value=0),
            Symbol(kind="parameter", name="P_min", value=0),
            Symbol(kind="parameter", name="T_min", value=6000),
            Symbol(kind="parameter", name="T_max", value=14000),
            Symbol(kind="parameter", name="w_T", value=0),
            Symbol(kind="technology", name="Q", formula=Formula("1")),
            Symbol(kind="technology", name="P_prod", formula=Formula("Q")),
        ],
        units=[
            Unit(name="A", multiplicity=1, failure_modes=[_mode("a", "0.002 * u")]),
            Unit(name="B", multiplicity=1, failure_modes=[_mode("b", "0.002 * (1 - u)")]),
            Unit(name="C", multiplicity=1, failure_modes=[_mode("c", "0.001")]),
        ],
    )


def test_optimizer_reaches_known_synchronization() -> None:
    result = optimize(_sync_model(), maxiter=25, popsize=8, seed=1)
    assert result.feasible, result.message
    assert result.regime["u"] == pytest.approx(0.5, abs=0.04)
    assert result.T == pytest.approx(10000, rel=0.04)
    assert len(result.units) == 3
    assert all(unit.in_window for unit in result.units)
    assert all(unit.utilization == pytest.approx(1.0, abs=0.05) for unit in result.units)


def test_optimizer_reports_q_min_infeasible() -> None:
    model = _sync_model()
    model.criterion = "A"
    model.symbol("Q").formula = Formula("u")
    model.symbol("Q_min").value = 5
    result = optimize(model, maxiter=4, popsize=4, seed=0)
    assert result.feasible is False
    assert any("Q" in item for item in result.violations)
    assert "Допустимого решения нет" in result.message


def test_multiplicity_grid_is_enumerated() -> None:
    model = _sync_model()
    for unit in model.units:
        unit.multiplicity = None
    seen: set[int] = set()

    def progress(event) -> None:
        seen.add(event.index)

    optimize(model, maxiter=1, popsize=2, seed=0, progress=progress)
    assert seen == set(range(4**3))
