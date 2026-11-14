"""Версии формул, единственность активной версии, снимок в результате, JSON."""

from __future__ import annotations

import sqlite3

import pytest

from millrepair.db import Database
from millrepair.engine import calculate
from millrepair.io_json import model_from_document, model_to_document
from millrepair.model import ModelError


def _open(tmp_path) -> Database:
    database = Database(tmp_path / "mill.sqlite")
    database.migrate()
    database.ensure_default()
    return database


def test_seed_loads_once_and_schema_is_versioned(tmp_path) -> None:
    database = _open(tmp_path)
    assert database.schema_version() == 1
    database.migrate()
    assert len(database.list_models()) == 1
    model = database.load_active_model()
    assert model.name == "Базовая"
    assert model.symbol("G") is not None
    assert model.symbol("G").adjustable is True
    assert model.symbol("n").adjustable is False
    database.ensure_default()
    assert len(database.list_models()) == 1
    database.close()


def test_formula_versions_rollback_and_single_active(tmp_path) -> None:
    database = _open(tmp_path)
    model = database.load_active_model()
    symbol = model.symbol("Q")
    assert symbol is not None and symbol.formula is not None
    original = symbol.formula.expression
    first_id = symbol.formula.version_id
    second_id = database.add_formula_version(
        symbol_id=symbol.id,
        role="expression",
        expression="100",
        comment="проверка",
        source="тест",
    )
    assert second_id != first_id
    updated = database.load_active_model().symbol("Q")
    assert updated.formula.expression == "100"
    assert updated.formula.version_id == second_id
    history = database.formula_history(symbol_id=symbol.id, role="expression")
    assert [row["id"] for row in history] == [first_id, second_id]
    assert sum(row["is_active"] for row in history) == 1
    database.rollback_formula(first_id)
    restored = database.load_active_model().symbol("Q")
    assert restored.formula.expression == original
    history = database.formula_history(symbol_id=symbol.id, role="expression")
    assert len(history) == 3
    assert sum(row["is_active"] for row in history) == 1
    with pytest.raises(sqlite3.IntegrityError):
        with database.conn:
            database.conn.execute(
                """
                INSERT INTO formula_versions (
                    symbol_id, failure_mode_id, role, expression, comment, source, created_at, is_active
                ) VALUES (?, NULL, 'expression', '1', '', '', '2026-01-01T00:00:00+00:00', 1)
                """,
                (symbol.id,),
            )
    database.close()


def test_result_keeps_formula_version_after_edit(tmp_path) -> None:
    database = _open(tmp_path)
    model = database.load_active_model()
    mode = model.units[0].failure_modes[0]
    formula = mode.formulas["wear_rate"]
    calc = calculate(model)
    result_id = database.save_result(
        model,
        kind="calc",
        criterion=model.criterion,
        inputs={"regime": calc.regime},
        outputs={"Q": calc.Q, "t": [unit.t for unit in calc.units]},
    )
    stored = database.get_result(result_id)
    key = f"{model.units[0].name}/{mode.name}/wear_rate"
    assert stored["formula_versions"]["failure_modes"][key] == formula.version_id
    assert stored["formula_versions"]["symbols"]["Q"] == model.symbol("Q").formula.version_id
    database.add_formula_version(
        failure_mode_id=mode.id,
        role="wear_rate",
        expression="0.02",
        comment="новая",
        source="",
    )
    again = database.get_result(result_id)
    assert again["formula_versions"]["failure_modes"][key] == formula.version_id
    saved = database.get_formula_version(formula.version_id)
    assert saved["expression"] == formula.expression
    current = database.load_active_model().units[0].failure_modes[0]
    assert current.formulas["wear_rate"].version_id != formula.version_id
    database.close()


def test_export_import_roundtrip(tmp_path) -> None:
    source = _open(tmp_path)
    original = source.load_active_model()
    document = model_to_document(original)
    source.close()
    imported_db = Database(tmp_path / "copy.sqlite")
    imported_db.migrate()
    model = model_from_document(document)
    imported_db.insert_model(model, activate=True)
    loaded = imported_db.load_active_model()
    _assert_same(original, loaded)
    again = calculate(loaded)
    baseline = calculate(original)
    assert again.Q == pytest.approx(baseline.Q)
    assert [unit.t for unit in again.units] == pytest.approx([unit.t for unit in baseline.units])
    imported_db.close()


def test_parameter_version_and_copy(tmp_path) -> None:
    database = _open(tmp_path)
    model = database.load_active_model()
    symbol = model.symbol("k_l")
    assert symbol is not None and symbol.id is not None
    database.set_symbol_value(
        symbol.id,
        symbol.value * 2,
        comment="откалибровано по замерам от 2026-01-01 до 2026-02-01",
        source="замеры",
    )
    updated = database.load_active_model().symbol("k_l")
    assert updated.value == pytest.approx(symbol.value * 2)
    assert updated.value_version_id != symbol.value_version_id
    with pytest.raises(sqlite3.IntegrityError):
        with database.conn:
            database.conn.execute(
                """
                INSERT INTO parameter_versions (symbol_id, value, comment, source, created_at, is_active)
                VALUES (?, 1, '', '', '2026-01-01T00:00:00+00:00', 1)
                """,
                (symbol.id,),
            )
    current = database.load_active_model()
    copy_id = database.copy_model(current.id, "Вариант научника")
    copy = database.load_active_model()
    assert copy.name == "Вариант научника"
    assert copy.id == copy_id
    assert copy.id != current.id
    _assert_same_structure(current, copy)
    with pytest.raises(ModelError):
        database.copy_model(copy.id, "Вариант научника")
    database.close()


def _assert_same(left, right) -> None:
    assert left.name == right.name
    assert left.criterion == right.criterion
    assert left.description == right.description
    _assert_same_structure(left, right)


def _assert_same_structure(left, right) -> None:
    assert [item.name for item in left.symbols] == [item.name for item in right.symbols]
    for old, new in zip(left.symbols, right.symbols, strict=True):
        assert old.kind == new.kind
        assert old.units == new.units
        assert old.adjustable == new.adjustable
        if old.value is not None:
            assert new.value == pytest.approx(old.value)
        if old.formula is not None:
            assert new.formula.expression == old.formula.expression
            assert new.formula.comment == old.formula.comment
            assert new.formula.source == old.formula.source
    assert [unit.name for unit in left.units] == [unit.name for unit in right.units]
    for old_unit, new_unit in zip(left.units, right.units, strict=True):
        assert old_unit.weight == pytest.approx(new_unit.weight)
        assert old_unit.multiplicity == new_unit.multiplicity
        assert [mode.name for mode in old_unit.failure_modes] == [
            mode.name for mode in new_unit.failure_modes
        ]
        for old_mode, new_mode in zip(old_unit.failure_modes, new_unit.failure_modes, strict=True):
            assert old_mode.measurement_quantity == new_mode.measurement_quantity
            assert old_mode.rate_parameter == new_mode.rate_parameter
            for role, formula in old_mode.formulas.items():
                assert new_mode.formulas[role].expression == formula.expression
                assert new_mode.formulas[role].comment == formula.comment
                assert new_mode.formulas[role].source == formula.source
