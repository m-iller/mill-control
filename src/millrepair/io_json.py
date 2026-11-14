"""Чтение и запись модели в JSON.

Файл можно хранить в git и отправлять руководителю. Идентификаторы версий
базы в документ не входят: при импорте создаются новые версии.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from millrepair.model import FORMULA_ROLES, FailureMode, Formula, Model, Symbol, Unit

FORMAT_VERSION = 1


class ModelImportError(ValueError):
    """JSON модели не удалось прочитать."""


def model_to_document(model: Model) -> dict[str, Any]:
    return {
        "format": FORMAT_VERSION,
        "name": model.name,
        "description": model.description,
        "criterion": model.criterion,
        "cycle_start": model.cycle_start,
        "symbols": [_symbol_to_json(item) for item in model.symbols],
        "units": [_unit_to_json(item) for item in model.units],
    }


def model_to_json(model: Model) -> str:
    return json.dumps(model_to_document(model), ensure_ascii=False, indent=2) + "\n"


def model_from_json(text: str) -> Model:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelImportError(f"JSON повреждён: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ModelImportError("корень JSON должен быть объектом")
    return model_from_document(payload)


def model_from_document(payload: dict[str, Any]) -> Model:
    version = payload.get("format", FORMAT_VERSION)
    if version != FORMAT_VERSION:
        raise ModelImportError(f"неподдерживаемая версия формата: {version}")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ModelImportError("у модели нет имени")
    symbols_raw = payload.get("symbols", [])
    units_raw = payload.get("units", [])
    if not isinstance(symbols_raw, list) or not isinstance(units_raw, list):
        raise ModelImportError("symbols и units должны быть списками")
    criterion = payload.get("criterion", "A")
    if criterion not in {"A", "B"}:
        raise ModelImportError(f"критерий должен быть A или B, получено «{criterion}»")
    model = Model(
        name=name.strip(),
        description=_text(payload.get("description", "")),
        criterion=criterion,
        cycle_start=payload.get("cycle_start") or None,
        symbols=[_symbol_from_json(item, index) for index, item in enumerate(symbols_raw)],
        units=[_unit_from_json(item, index) for index, item in enumerate(units_raw)],
    )
    return model


def load_model_file(path: Path) -> Model:
    return model_from_json(Path(path).read_text(encoding="utf-8"))


def save_model_file(model: Model, path: Path) -> None:
    Path(path).write_text(model_to_json(model), encoding="utf-8")


def read_default_model_text() -> str:
    """Текст seed-модели.

    Сначала пакетный ресурс через importlib.resources — так файл находится
    и в исходниках, и в сборке. Если упаковщик положил его рядом с программой
    не как ресурс пакета, читается тот же JSON из каталога данных сборки или
    из ``seed/default_model.json`` в репозитории.
    """
    import sys
    from importlib.resources import files

    try:
        resource = files("millrepair.data").joinpath("default_model.json")
        text = resource.read_text(encoding="utf-8")
        if text.strip():
            return text
    except (FileNotFoundError, OSError, TypeError, ModuleNotFoundError):
        pass
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.append(base / "millrepair" / "data" / "default_model.json")
        candidates.append(base / "seed" / "default_model.json")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "seed" / "default_model.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError("Не найден seed/default_model.json")


def load_default_model() -> Model:
    return model_from_json(read_default_model_text())


def _symbol_to_json(item: Symbol) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": item.kind,
        "name": item.name,
        "units": item.units,
        "description": item.description,
    }
    if item.kind in {"regime", "parameter"}:
        payload["value"] = item.value
        payload["comment"] = item.comment
        payload["source"] = item.source
    if item.kind == "regime":
        payload["min"] = item.min_value
        payload["max"] = item.max_value
        payload["adjustable"] = item.adjustable
    if item.formula is not None:
        payload["expression"] = item.formula.expression
        payload["comment"] = item.formula.comment
        payload["source"] = item.formula.source
    return payload


def _symbol_from_json(payload: Any, index: int) -> Symbol:
    if not isinstance(payload, dict):
        raise ModelImportError(f"символ #{index} должен быть объектом")
    kind = payload.get("kind")
    name = payload.get("name")
    if kind not in {"regime", "parameter", "derived", "technology"}:
        raise ModelImportError(f"символ «{name}»: неизвестный тип «{kind}»")
    if not isinstance(name, str) or not name.strip():
        raise ModelImportError(f"символ #{index}: нет имени")
    formula = None
    comment = _text(payload.get("comment", ""))
    source = _text(payload.get("source", ""))
    if kind in {"derived", "technology"}:
        expression = payload.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ModelImportError(f"{name}: нет формулы")
        formula = Formula(expression=expression, comment=comment, source=source)
    value = payload.get("value")
    if kind in {"regime", "parameter"}:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ModelImportError(f"{name}: нужно числовое значение")
    return Symbol(
        kind=kind,
        name=name.strip(),
        units=_text(payload.get("units", "")),
        description=_text(payload.get("description", "")),
        value=None if value is None else float(value),
        min_value=_optional_float(payload.get("min"), name),
        max_value=_optional_float(payload.get("max"), name),
        adjustable=bool(payload.get("adjustable", False)),
        formula=formula,
        comment=comment,
        source=source,
        sort_order=index,
    )


def _unit_to_json(item: Unit) -> dict[str, Any]:
    return {
        "name": item.name,
        "description": item.description,
        "weight": item.weight,
        "multiplicity": item.multiplicity,
        "failure_modes": [_mode_to_json(mode) for mode in item.failure_modes],
    }


def _unit_from_json(payload: Any, index: int) -> Unit:
    if not isinstance(payload, dict):
        raise ModelImportError(f"узел #{index} должен быть объектом")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ModelImportError(f"узел #{index}: нет имени")
    multiplicity = payload.get("multiplicity")
    if multiplicity is not None:
        if not isinstance(multiplicity, int) or isinstance(multiplicity, bool):
            raise ModelImportError(f"{name}: кратность должна быть целым числом или null")
        if multiplicity not in {1, 2, 3, 4}:
            raise ModelImportError(f"{name}: кратность должна быть от 1 до 4")
    weight = payload.get("weight", 1.0)
    if not isinstance(weight, (int, float)) or isinstance(weight, bool):
        raise ModelImportError(f"{name}: вес должен быть числом")
    modes_raw = payload.get("failure_modes", [])
    if not isinstance(modes_raw, list):
        raise ModelImportError(f"{name}: failure_modes должен быть списком")
    return Unit(
        name=name.strip(),
        description=_text(payload.get("description", "")),
        weight=float(weight),
        multiplicity=multiplicity,
        failure_modes=[_mode_from_json(item, name, i) for i, item in enumerate(modes_raw)],
        sort_order=index,
    )


def _mode_to_json(mode: FailureMode) -> dict[str, Any]:
    formulas = {}
    for role in FORMULA_ROLES:
        formula = mode.formulas.get(role)
        if formula is None:
            continue
        formulas[role] = {
            "expression": formula.expression,
            "comment": formula.comment,
            "source": formula.source,
        }
    return {
        "name": mode.name,
        "description": mode.description,
        "measurement_quantity": mode.measurement_quantity,
        "rate_parameter": mode.rate_parameter,
        "formulas": formulas,
    }


def _mode_from_json(payload: Any, unit_name: str, index: int) -> FailureMode:
    if not isinstance(payload, dict):
        raise ModelImportError(f"{unit_name}: вид отказа #{index} должен быть объектом")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ModelImportError(f"{unit_name}: вид отказа #{index} без имени")
    raw_formulas = payload.get("formulas", {})
    if not isinstance(raw_formulas, dict):
        raise ModelImportError(f"{unit_name}/{name}: formulas должен быть объектом")
    formulas: dict[str, Formula] = {}
    for role, body in raw_formulas.items():
        if role not in FORMULA_ROLES:
            raise ModelImportError(f"{unit_name}/{name}: неизвестная роль формулы «{role}»")
        if not isinstance(body, dict):
            raise ModelImportError(f"{unit_name}/{name}: формула {role} должна быть объектом")
        expression = body.get("expression")
        if not isinstance(expression, str):
            raise ModelImportError(f"{unit_name}/{name}: у формулы {role} нет выражения")
        formulas[role] = Formula(
            expression=expression,
            comment=_text(body.get("comment", "")),
            source=_text(body.get("source", "")),
        )
    return FailureMode(
        name=name.strip(),
        description=_text(payload.get("description", "")),
        measurement_quantity=_text(payload.get("measurement_quantity", "")),
        rate_parameter=_text(payload.get("rate_parameter", "")),
        formulas=formulas,
        sort_order=index,
    )


def _optional_float(value: Any, owner: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelImportError(f"{owner}: граница должна быть числом")
    return float(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ModelImportError("текстовое поле должно быть строкой")
    return value
