"""Подбор режима, момента ремонта и кратностей.

Внешний цикл перебирает кратности kᵢ. Внутри — differential_evolution:
критерий A кусочно-постоянный, градиент ему не помощник. Ограничения
входят штрафом. Если допустимой точки нет, в ответе написано, какое
условие мешает.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product

import numpy as np
from scipy.optimize import differential_evolution

from millrepair.engine import CalcResult, CompiledModel, ModeCalc, calculate
from millrepair.model import MeasurementPoint, Model, RegimePeriod

ProgressCallback = Callable[["OptimizeProgress"], None]
StopCallback = Callable[[], bool]


@dataclass
class OptimizeProgress:
    index: int
    total: int
    iteration: int
    maxiter: int
    multiplicities: dict[str, int]


@dataclass
class UnitOptimum:
    name: str
    t: float | None
    k: int
    replacement: float | None
    utilization: float | None
    in_window: bool
    error: str | None


@dataclass
class OptimizeResult:
    feasible: bool
    message: str
    violations: list[str]
    criterion: str
    T: float | None
    regime: dict[str, float]
    multiplicities: dict[str, int]
    Q: float | None
    P_prod: float | None
    units: list[UnitOptimum] = field(default_factory=list)
    calc: CalcResult | None = None
    evaluations: int = 0
    seed: int | None = None
    objective: float | None = None


def optimize(
    model: Model,
    *,
    measurements: list[MeasurementPoint] | None = None,
    periods: list[RegimePeriod] | None = None,
    cycle_start: datetime | str | None = None,
    as_of: datetime | str | None = None,
    maxiter: int = 10,
    popsize: int = 5,
    seed: int | None = None,
    tol: float = 0.0,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
) -> OptimizeResult:
    """Найти режим u, момент T и кратности.

    ``maxiter`` и ``popsize`` оставлены параметрами, чтобы тесты и интерфейс
    могли урезать поиск. ``seed`` фиксирует генератор differential_evolution.
    """
    rng_seed = (
        int(np.random.default_rng(seed).integers(0, 2**31 - 1)) if seed is None else int(seed)
    )
    names = [item.name for item in model.adjustable_symbols()]
    bounds: list[tuple[float, float]] = []
    x0: list[float] = []
    for item in model.adjustable_symbols():
        if item.min_value is None or item.max_value is None or item.min_value >= item.max_value:
            return _failed(model, f"у «{item.name}» не заданы корректные границы")
        if item.value is None:
            return _failed(model, f"у «{item.name}» нет текущего значения")
        bounds.append((float(item.min_value), float(item.max_value)))
        x0.append(min(max(float(item.value), item.min_value), item.max_value))
    t_min = float(model.setting("T_min"))
    t_max = float(model.setting("T_max"))
    if not math.isfinite(t_min) or not math.isfinite(t_max) or t_min >= t_max:
        return _failed(model, "границы T_min и T_max заданы неверно")
    baseline = calculate(
        model,
        measurements=measurements,
        periods=periods,
        cycle_start=cycle_start,
        as_of=as_of,
    )
    times = [
        unit.t
        for unit in baseline.units
        if unit.t is not None and math.isfinite(unit.t) and unit.t > 0
    ]
    guess = float(np.median(times)) if times else 0.5 * (t_min + t_max)
    bounds.append((t_min, t_max))
    x0.append(min(max(guess, t_min), t_max))

    search = _Search(model, baseline, names)
    combos = list(_multiplicity_grid(model))
    best_score = math.inf
    best_x: np.ndarray | None = None
    best_k: dict[str, int] = {}
    evaluations = 0
    stopped = False
    for index, multiplicities in enumerate(combos):
        if should_stop is not None and should_stop():
            stopped = True
            break
        if progress is not None:
            progress(
                OptimizeProgress(
                    index=index,
                    total=len(combos),
                    iteration=0,
                    maxiter=maxiter,
                    multiplicities=multiplicities,
                )
            )
        iteration = 0

        def callback(
            *_args: object, _index: int = index, _k: dict[str, int] = multiplicities
        ) -> bool:
            nonlocal iteration
            iteration += 1
            if progress is not None:
                progress(
                    OptimizeProgress(
                        index=_index,
                        total=len(combos),
                        iteration=iteration,
                        maxiter=maxiter,
                        multiplicities=_k,
                    )
                )
            return bool(should_stop is not None and should_stop())

        def objective(x: np.ndarray, _k: dict[str, int] = multiplicities) -> np.ndarray | float:
            return search.score(x, _k)

        try:
            solved = differential_evolution(
                objective,
                bounds,
                maxiter=maxiter,
                popsize=popsize,
                seed=rng_seed,
                tol=tol,
                atol=0.0,
                mutation=0.5,
                recombination=0.7,
                polish=False,
                vectorized=True,
                updating="deferred",
                x0=np.asarray(x0, dtype=float),
                callback=callback,
                workers=1,
            )
        except Exception as exc:
            return _failed(model, f"оптимизатор остановился: {exc}")
        evaluations += int(getattr(solved, "nfev", 0))
        score = float(solved.fun)
        if score < best_score:
            best_score = score
            best_x = np.asarray(solved.x, dtype=float)
            best_k = dict(multiplicities)
        if should_stop is not None and should_stop():
            stopped = True
            break

    if best_x is None:
        message = (
            "Поиск остановлен до первой оценки." if stopped else "Оптимизатор не вернул точку."
        )
        return _failed(model, message)

    regime = dict(model.regime())
    for name, value in zip(names, best_x[:-1], strict=True):
        regime[name] = float(value)
    horizon = float(best_x[-1])
    calc = calculate(
        model,
        regime=regime,
        measurements=measurements,
        periods=periods,
        cycle_start=cycle_start,
        as_of=as_of,
    )
    violations = constraint_violations(model, calc, horizon, best_k)
    feasible = not violations
    if feasible:
        message = "Допустимое решение найдено."
    else:
        message = "Допустимого решения нет. Мешает: " + "; ".join(violations)
    if stopped:
        message = "Поиск остановлен. " + message
    return OptimizeResult(
        feasible=feasible,
        message=message,
        violations=violations,
        criterion=model.criterion if model.criterion in {"A", "B"} else "A",
        T=horizon,
        regime=regime,
        multiplicities=best_k,
        Q=calc.Q,
        P_prod=calc.P_prod,
        units=_rows(model, calc, horizon, best_k),
        calc=calc,
        evaluations=evaluations,
        seed=rng_seed,
        objective=None if math.isinf(best_score) else best_score,
    )


def constraint_violations(
    model: Model,
    calc: CalcResult,
    horizon: float,
    multiplicities: dict[str, int],
) -> list[str]:
    """Какие жёсткие условия не выполнены в найденной точке."""
    found: list[str] = []
    q_min = model.setting("Q_min")
    p_min = model.setting("P_min")
    if calc.Q is None or not math.isfinite(calc.Q):
        found.append("Q не посчитан")
    elif calc.Q < q_min - _tol(q_min):
        found.append(f"Q = {_num(calc.Q)} < Q_min = {_num(q_min)}")
    if calc.P_prod is None or not math.isfinite(calc.P_prod):
        found.append("P_prod не посчитан")
    elif calc.P_prod < p_min - _tol(p_min):
        found.append(f"P_prod = {_num(calc.P_prod)} < P_min = {_num(p_min)}")
    for unit in calc.units:
        need = horizon / multiplicities.get(unit.name, 1)
        if unit.error:
            found.append(f"узел {unit.name}: {unit.error}")
            continue
        if unit.t is None or not math.isfinite(unit.t):
            found.append(f"узел {unit.name}: нет времени до отказа")
            continue
        if unit.t < need * (1 - 1e-5):
            found.append(f"узел {unit.name}: t = {_num(unit.t)} ч < T/k = {_num(need)} ч")
    return found


def format_optimize(result: OptimizeResult) -> str:
    lines = [result.message, ""]
    if result.T is not None:
        lines.append(f"T = {_num(result.T)} ч")
    lines.append(f"Критерий {result.criterion}")
    if result.seed is not None:
        lines.append(f"Оценок: {result.evaluations}, зерно: {result.seed}")
    lines.append("Режим:")
    for name, value in result.regime.items():
        lines.append(f"  {name} = {_num(value)}")
    lines.append("")
    lines.append(f"Q = {_num(result.Q)}")
    lines.append(f"P_prod = {_num(result.P_prod)}")
    lines.append("")
    for unit in result.units:
        window = "да" if unit.in_window else "нет"
        lines.append(
            " | ".join(
                [
                    unit.name,
                    f"t={_num(unit.t)} ч",
                    f"k={unit.k}",
                    f"T/k={_num(unit.replacement)} ч",
                    f"использование={_num(unit.utilization)}",
                    f"окно={window}",
                ]
            )
        )
        if unit.error:
            lines.append(f"  ошибка: {unit.error}")
    if result.violations:
        lines.append("")
        lines.append("Ограничения:")
        for item in result.violations:
            lines.append(f"  {item}")
    return "\n".join(lines)


class _Search:
    def __init__(self, model: Model, baseline: CalcResult, names: list[str]) -> None:
        self.model = model
        self.names = names
        self.compiled = CompiledModel(model)
        self.base_regime = dict(model.regime())
        self.delta = float(model.setting("delta"))
        self.q_min = float(model.setting("Q_min"))
        self.p_min = float(model.setting("P_min"))
        self.t_max = float(model.setting("T_max"))
        self.w_T = float(model.setting("w_T"))
        self.criterion = model.criterion if model.criterion in {"A", "B"} else "A"
        self.modes = []
        by_key = {(mode.unit, mode.mode): mode for unit in baseline.units for mode in unit.modes}
        for prepared in self.compiled.modes:
            saved = by_key.get((prepared.unit.name, prepared.mode.name))
            self.modes.append((prepared, saved))

    def score(self, x: np.ndarray, multiplicities: dict[str, int]) -> np.ndarray | float:
        array = np.asarray(x, dtype=float)
        squeeze = array.ndim == 1
        if squeeze:
            array = array.reshape(-1, 1)
        count = array.shape[1]
        regime = dict(self.base_regime)
        for index, name in enumerate(self.names):
            regime[name] = array[index]
        horizon = np.asarray(array[-1], dtype=float)
        try:
            context, errors = self.compiled.context(regime)
        except Exception:
            errors = ["контекст не посчитан"]
            context = {}
        if errors:
            values = np.full(count, 1e12)
            return float(values[0]) if squeeze else values
        penalty = np.zeros(count)
        lives: dict[str, np.ndarray] = {}
        broken: dict[str, bool] = {}
        for prepared, saved in self.modes:
            try:
                life = self._life(prepared, saved, context, count)
            except Exception:
                life = np.full(count, np.nan)
                broken[prepared.unit.name] = True
            previous = lives.get(prepared.unit.name)
            lives[prepared.unit.name] = life if previous is None else np.minimum(previous, life)
        q_value = _align(context.get("Q", np.nan), count)
        p_value = _align(context.get("P_prod", np.nan), count)
        penalty += _shortfall(q_value, self.q_min)
        penalty += _shortfall(p_value, self.p_min)
        in_window = np.zeros(count)
        unused = np.zeros(count)
        exact_unused = np.zeros(count)
        for unit in self.model.units:
            life = lives.get(unit.name, np.full(count, np.nan))
            need = horizon / float(multiplicities[unit.name])
            bad = (~np.isfinite(life)) | (life < 0) | broken.get(unit.name, False)
            penalty += np.where(bad, 10.0, np.maximum(0.0, need - life) / np.maximum(need, 1e-9))
            ratio = np.where(bad, np.nan, (life - need) / np.maximum(need, 1e-9))
            squared = np.where(np.isfinite(ratio), ratio**2, 100.0)
            exact_unused += unit.weight * squared
            unused += unit.weight * np.minimum(squared, 100.0)
            inside = (~bad) & (life + 1e-6 >= need) & ((life - need) <= self.delta)
            in_window += inside.astype(float)
        penalty_amount = np.where(penalty > 0, 1e9 + penalty * 1e6, 0.0)
        bonus = self.w_T * horizon / max(self.t_max, 1.0)
        if self.criterion == "B":
            objective = exact_unused + penalty_amount - bonus
        else:
            objective = -in_window * 1e6 + unused + penalty_amount - bonus
        objective = np.where(np.isfinite(objective), objective, 1e12)
        if squeeze:
            return float(objective[0])
        return objective

    def _life(self, prepared, saved: ModeCalc | None, context: dict, count: int) -> np.ndarray:
        if prepared.error or "wear_rate" not in prepared.compiled:
            return np.full(count, np.nan)
        local = dict(context)
        local["consumed"] = 0.0 if saved is None else saved.consumed
        local["measured"] = 0.0 if saved is None else saved.curve_context.get("measured", 0.0)
        has = 0.0 if saved is None else saved.curve_context.get("has_measurement", 0.0)
        local["has_measurement"] = has
        wear = _align(prepared.compiled["wear_rate"](local), count)
        local["v"] = wear
        residual = _align(prepared.compiled["residual"](local), count)
        local["R"] = residual
        t_det = _align(prepared.compiled["t_det"](local), count)
        local["t_det"] = np.where(residual <= 0, 0.0, t_det)
        eta = _align(prepared.compiled["eta"](local), count)
        local["eta"] = np.where(residual <= 0, 0.0, eta)
        t_fail = _align(prepared.compiled["t_fail"](local), count)
        t_fail = np.where(residual <= 0, 0.0, t_fail)
        t_fail = np.where((wear <= 0) | ~np.isfinite(wear), np.nan, t_fail)
        return np.where(np.isfinite(t_fail) & (t_fail >= 0), t_fail, np.nan)


def _multiplicity_grid(model: Model) -> list[dict[str, int]]:
    axes: list[list[int]] = []
    for unit in model.units:
        if unit.multiplicity is None:
            axes.append([1, 2, 3, 4])
        else:
            axes.append([int(unit.multiplicity)])
    names = [unit.name for unit in model.units]
    return [dict(zip(names, combo, strict=True)) for combo in product(*axes)]


def _rows(
    model: Model, calc: CalcResult, horizon: float, multiplicities: dict[str, int]
) -> list[UnitOptimum]:
    delta = model.setting("delta")
    rows = []
    for unit in calc.units:
        k = multiplicities.get(unit.name, 1)
        replacement = horizon / k
        utilization = None
        if unit.t is not None and unit.t > 0 and math.isfinite(unit.t):
            utilization = replacement / unit.t
        in_window = False
        if unit.error is None and unit.t is not None and math.isfinite(unit.t):
            in_window = unit.t >= replacement * (1 - 1e-5) and (unit.t - replacement) <= delta
        rows.append(
            UnitOptimum(
                name=unit.name,
                t=unit.t,
                k=k,
                replacement=replacement,
                utilization=utilization,
                in_window=in_window,
                error=unit.error,
            )
        )
    return rows


def _align(value, count: int) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return np.full(count, float(array))
    return np.broadcast_to(array, (count,)).astype(float, copy=True)


def _shortfall(value: np.ndarray, minimum: float) -> np.ndarray:
    missing = ~np.isfinite(value)
    scale = abs(minimum) if abs(minimum) > 1e-9 else 1.0
    gap = np.maximum(0.0, minimum - np.where(missing, minimum - 1.0, value)) / scale
    return np.where(missing, 10.0, gap)


def _tol(limit: float) -> float:
    return max(1e-6, 1e-6 * abs(limit))


def _num(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.6g}"


def _failed(model: Model, message: str) -> OptimizeResult:
    return OptimizeResult(
        feasible=False,
        message=message,
        violations=[message],
        criterion=model.criterion if model.criterion in {"A", "B"} else "A",
        T=None,
        regime=dict(model.regime()),
        multiplicities={},
        Q=None,
        P_prod=None,
    )
