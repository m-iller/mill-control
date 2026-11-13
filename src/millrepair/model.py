"""Модель мельницы в памяти: величины, узлы, граф зависимостей формул.

Физических формул здесь нет — только структура и проверка ссылок.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from millrepair.expr import ExpressionError, free_names
from millrepair.util import unknown_names_message

FORMULA_ROLES: tuple[str, ...] = (
    "wear_rate",
    "residual",
    "t_det",
    "eta",
    "reliability",
    "t_fail",
)

ROLE_TITLES: dict[str, str] = {
    "wear_rate": "Скорость расходования ресурса v",
    "residual": "Остаточный ресурс R",
    "t_det": "Детерминированное время t_det",
    "eta": "Масштаб Вейбулла eta",
    "reliability": "Вероятность безотказной работы P(t)",
    "t_fail": "Время гарантированного отказа t_fail",
}

# Имена, которые движок подставляет при расчёте вида отказа. В глобальном
# графе производных величин их нет.
ROLE_LOCAL_NAMES: dict[str, frozenset[str]] = {
    "wear_rate": frozenset(),
    "residual": frozenset({"measured", "has_measurement", "consumed"}),
    "t_det": frozenset({"R", "v"}),
    "eta": frozenset({"R", "v", "t_det"}),
    "reliability": frozenset({"R", "v", "t_det", "eta", "t"}),
    "t_fail": frozenset({"R", "v", "t_det", "eta"}),
}

SYMBOL_KINDS: tuple[str, ...] = ("regime", "parameter", "derived", "technology")
FORMULA_KINDS: tuple[str, ...] = ("derived", "technology")

SETTING_DEFAULTS: dict[str, float] = {
    "eps": 0.05,
    "delta": 1000.0,
    "Q_min": 0.0,
    "P_min": 0.0,
    "T_min": 1000.0,
    "T_max": 40000.0,
    "w_T": 0.0,
}


class ModelError(ValueError):
    """Документ модели неполон или противоречив."""


class DependencyError(ModelError):
    """Цикл зависимостей или неизвестное имя в формуле."""

    def __init__(
        self,
        message: str,
        *,
        unknown: set[str] | None = None,
        cycle: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.unknown = unknown or set()
        self.cycle = cycle or []


@dataclass
class Formula:
    expression: str
    comment: str = ""
    source: str = ""
    version_id: int | None = None
    created_at: str | None = None


@dataclass
class Symbol:
    kind: str
    name: str
    units: str = ""
    description: str = ""
    value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    adjustable: bool = False
    formula: Formula | None = None
    comment: str = ""
    source: str = ""
    sort_order: int = 0
    id: int | None = None
    value_version_id: int | None = None


@dataclass
class FailureMode:
    name: str
    description: str = ""
    measurement_quantity: str = ""
    rate_parameter: str = ""
    formulas: dict[str, Formula] = field(default_factory=dict)
    sort_order: int = 0
    id: int | None = None
    unit_id: int | None = None


@dataclass
class Unit:
    name: str
    description: str = ""
    weight: float = 1.0
    multiplicity: int | None = None
    failure_modes: list[FailureMode] = field(default_factory=list)
    sort_order: int = 0
    id: int | None = None


@dataclass
class MeasurementPoint:
    measured_at: datetime
    unit_name: str
    quantity: str
    value: float
    comment: str = ""
    id: int | None = None


@dataclass
class RegimePeriod:
    start: datetime
    end: datetime
    values: dict[str, float]
    comment: str = ""
    id: int | None = None


@dataclass
class Model:
    name: str
    description: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    criterion: str = "A"
    cycle_start: str | None = None
    id: int | None = None

    def symbol(self, name: str) -> Symbol | None:
        for item in self.symbols:
            if item.name == name:
                return item
        return None

    def setting(self, name: str) -> float:
        item = self.symbol(name)
        if item is not None and item.value is not None:
            return float(item.value)
        if name not in SETTING_DEFAULTS:
            raise KeyError(name)
        return SETTING_DEFAULTS[name]

    def regime(self) -> dict[str, float]:
        values: dict[str, float] = {}
        for item in self.symbols:
            if item.kind == "regime" and item.value is not None:
                values[item.name] = float(item.value)
        return values

    def adjustable_symbols(self) -> list[Symbol]:
        return [item for item in self.symbols if item.kind == "regime" and item.adjustable]


@dataclass
class DependencyReport:
    order: list[str]
    errors: list[str]
    unknown: dict[str, set[str]]
    cycle: list[str]


def _formula_symbols(model: Model) -> list[Symbol]:
    return [item for item in model.symbols if item.kind in FORMULA_KINDS]


def analyze_dependencies(model: Model) -> DependencyReport:
    """Топологический порядок производных и технологических формул.

    Ошибки синтаксиса, неизвестных имён и циклов собираются в отчёт и не
    роняют процесс: вызывающий код решает, прерывать расчёт или пометить узел.
    """
    errors: list[str] = []
    names = [item.name for item in model.symbols]
    known = set(names)
    if len(names) != len(known):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        errors.append("повторяются имена величин: " + ", ".join(duplicates))

    formula_names: list[str] = []
    parsed: dict[str, set[str]] = {}
    unknown: dict[str, set[str]] = {}
    for item in _formula_symbols(model):
        if item.formula is None or not item.formula.expression.strip():
            errors.append(f"{item.name}: нет формулы")
            continue
        try:
            free = free_names(item.formula.expression)
        except ExpressionError as exc:
            errors.append(f"{item.name}: {exc}")
            continue
        formula_names.append(item.name)
        missing = free - known
        if missing:
            unknown[item.name] = set(missing)
            errors.append(unknown_names_message(item.name, missing, known))
        parsed[item.name] = free

    node_set = set(parsed)
    deps = {name: free & node_set for name, free in parsed.items()}
    order, cycle = _toposort(deps)
    if cycle:
        text = " → ".join(cycle)
        errors.append(f"цикл зависимостей: {text}")
    return DependencyReport(order=order, errors=errors, unknown=unknown, cycle=cycle)


def topological_order(model: Model) -> list[str]:
    """Порядок вычисления формул. При цикле или неизвестном имени — ошибка."""
    report = analyze_dependencies(model)
    if report.errors:
        raise DependencyError(
            report.errors[0],
            unknown=set().union(*report.unknown.values()) if report.unknown else set(),
            cycle=report.cycle,
        )
    return report.order


def _toposort(deps: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    incoming = {name: set(depends) for name, depends in deps.items()}
    dependents: dict[str, set[str]] = {name: set() for name in deps}
    for name, depends in incoming.items():
        for parent in depends:
            dependents[parent].add(name)
    ready = sorted(name for name, depends in incoming.items() if not depends)
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for child in sorted(dependents[name]):
            incoming[child].discard(name)
            if not incoming[child]:
                ready.append(child)
        ready.sort()
    if len(order) == len(deps):
        return order, []
    remaining = {name for name, depends in incoming.items() if depends}
    cycle = _find_cycle(remaining, incoming)
    return order, cycle


def _find_cycle(remaining: set[str], incoming: dict[str, set[str]]) -> list[str]:
    visiting: set[str] = set()
    stack: list[str] = []

    def walk(name: str) -> list[str] | None:
        if name in visiting:
            index = stack.index(name)
            return stack[index:] + [name]
        visiting.add(name)
        stack.append(name)
        for parent in sorted(incoming.get(name, ())):
            if parent not in remaining and parent not in visiting:
                continue
            found = walk(parent)
            if found:
                return found
        stack.pop()
        visiting.discard(name)
        return None

    for start in sorted(remaining):
        if start in visiting:
            continue
        found = walk(start)
        if found:
            return found
    return sorted(remaining)


def formula_problems(
    model: Model,
    expression: str,
    *,
    extra_names: frozenset[str] | set[str] = frozenset(),
    owner: str = "формула",
) -> list[str]:
    """Синтаксис и неизвестные имена одной формулы. Циклы здесь не ищутся."""
    try:
        free = free_names(expression)
    except ExpressionError as exc:
        return [str(exc)]
    known = {item.name for item in model.symbols} | set(extra_names)
    missing = free - known
    if not missing:
        return []
    return [unknown_names_message(owner, missing, known)]


def validate_model(model: Model) -> list[str]:
    """Полная проверка модели перед сохранением и расчётом."""
    errors = list(analyze_dependencies(model).errors)
    if model.criterion not in {"A", "B"}:
        errors.append(f"неизвестный критерий «{model.criterion}»")
    seen_units: set[str] = set()
    for unit in model.units:
        if unit.name in seen_units:
            errors.append(f"повторяется узел «{unit.name}»")
        seen_units.add(unit.name)
        if unit.weight < 0:
            errors.append(f"{unit.name}: вес не может быть отрицательным")
        if unit.multiplicity is not None and unit.multiplicity not in {1, 2, 3, 4}:
            errors.append(f"{unit.name}: кратность должна быть 1, 2, 3, 4 или подбираться")
        seen_modes: set[str] = set()
        for mode in unit.failure_modes:
            if mode.name in seen_modes:
                errors.append(f"{unit.name}: повторяется вид отказа «{mode.name}»")
            seen_modes.add(mode.name)
            label = f"{unit.name}/{mode.name}"
            for role in FORMULA_ROLES:
                formula = mode.formulas.get(role)
                if formula is None or not formula.expression.strip():
                    errors.append(f"{label}: нет формулы «{ROLE_TITLES[role]}»")
                    continue
                errors.extend(
                    formula_problems(
                        model,
                        formula.expression,
                        extra_names=ROLE_LOCAL_NAMES[role],
                        owner=f"{label}, {ROLE_TITLES[role]}",
                    )
                )
    for item in model.symbols:
        if item.kind in ("regime", "parameter") and item.value is None:
            errors.append(f"{item.name}: не задано числовое значение")
        if item.kind == "regime" and item.adjustable:
            if item.min_value is None or item.max_value is None:
                errors.append(f"{item.name}: у регулируемой переменной нужны минимум и максимум")
            elif item.min_value >= item.max_value:
                errors.append(f"{item.name}: минимум должен быть меньше максимума")
            elif item.value is not None and not (item.min_value <= item.value <= item.max_value):
                errors.append(f"{item.name}: текущее значение вне границ")
    return errors
