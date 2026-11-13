"""Граф зависимостей и проверка модели."""

from __future__ import annotations

from millrepair.model import (
    DependencyError,
    FailureMode,
    Formula,
    Model,
    Symbol,
    Unit,
    analyze_dependencies,
    topological_order,
    validate_model,
)


def _derived(name: str, expression: str) -> Symbol:
    return Symbol(kind="derived", name=name, formula=Formula(expression))


def test_topological_order() -> None:
    model = Model(
        name="порядок",
        symbols=[
            Symbol(kind="regime", name="G", value=80),
            Symbol(kind="parameter", name="rho", value=2),
            Symbol(kind="parameter", name="F", value=4),
            _derived("Qv", "G / rho"),
            _derived("w", "Qv / F"),
        ],
    )
    order = topological_order(model)
    assert order.index("Qv") < order.index("w")


def test_cycle_is_reported() -> None:
    model = Model(
        name="цикл",
        symbols=[
            _derived("a", "b + 1"),
            _derived("b", "a + 2"),
        ],
    )
    try:
        topological_order(model)
    except DependencyError as exc:
        assert "цикл" in str(exc)
        assert "a" in exc.cycle
        assert "b" in exc.cycle
    else:
        raise AssertionError("цикл не обнаружен")


def test_unknown_name_hint() -> None:
    model = Model(
        name="имена",
        symbols=[
            Symbol(kind="parameter", name="F_nozzle", value=1),
            _derived("w", "Qv / F_noz"),
        ],
    )
    try:
        topological_order(model)
    except DependencyError as exc:
        text = str(exc)
    else:
        raise AssertionError("неизвестное имя пропущено")
    assert "Qv" in text
    assert "F_noz" in text
    assert "F_nozzle" in text
    report = analyze_dependencies(model)
    assert "Qv" in report.unknown["w"]


def test_validate_rejects_bad_multiplicity_and_bounds() -> None:
    model = Model(
        name="проверка",
        symbols=[
            Symbol(kind="regime", name="G", value=1, min_value=0, max_value=2, adjustable=True),
        ],
        units=[
            Unit(
                name="Узел",
                weight=-1,
                multiplicity=5,
                failure_modes=[FailureMode(name="отказ")],
            )
        ],
    )
    errors = validate_model(model)
    assert any("вес" in item for item in errors)
    assert any("кратность" in item for item in errors)
    assert any("нет формулы" in item for item in errors)
