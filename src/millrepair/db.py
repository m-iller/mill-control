"""SQLite: модели, версии формул и параметров, замеры, результаты.

Одно соединение принадлежит потоку интерфейса. Долгий расчёт получает уже
собранный объект Model и базу не трогает.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from millrepair.io_json import load_default_model
from millrepair.model import (
    FORMULA_ROLES,
    FailureMode,
    Formula,
    MeasurementPoint,
    Model,
    ModelError,
    RegimePeriod,
    Symbol,
    Unit,
)
from millrepair.util import parse_datetime, utcnow_iso

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE models (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    criterion TEXT NOT NULL DEFAULT 'A',
    cycle_start TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_models_active ON models(is_active) WHERE is_active = 1;

CREATE TABLE units (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1,
    multiplicity INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(model_id, name)
);

CREATE TABLE failure_modes (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    measurement_quantity TEXT NOT NULL DEFAULT '',
    rate_parameter TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(unit_id, name)
);

CREATE TABLE symbols (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('regime', 'parameter', 'derived', 'technology')),
    name TEXT NOT NULL,
    units TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    value REAL,
    min_value REAL,
    max_value REAL,
    adjustable INTEGER NOT NULL DEFAULT 0,
    comment TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(model_id, name)
);

CREATE TABLE formula_versions (
    id INTEGER PRIMARY KEY,
    symbol_id INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    failure_mode_id INTEGER REFERENCES failure_modes(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    expression TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    CHECK (
        (symbol_id IS NOT NULL AND failure_mode_id IS NULL)
        OR (symbol_id IS NULL AND failure_mode_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX ux_formula_symbol_active
    ON formula_versions(symbol_id, role)
    WHERE is_active = 1 AND symbol_id IS NOT NULL;

CREATE UNIQUE INDEX ux_formula_mode_active
    ON formula_versions(failure_mode_id, role)
    WHERE is_active = 1 AND failure_mode_id IS NOT NULL;

CREATE TABLE parameter_versions (
    id INTEGER PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    value REAL NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX ux_parameter_active
    ON parameter_versions(symbol_id)
    WHERE is_active = 1;

CREATE TABLE measurements (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    measured_at TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    quantity TEXT NOT NULL,
    value REAL NOT NULL,
    comment TEXT NOT NULL DEFAULT ''
);

CREATE TABLE regime_periods (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    regime_json TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT ''
);

CREATE TABLE results (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    criterion TEXT NOT NULL DEFAULT '',
    inputs_json TEXT NOT NULL,
    outputs_json TEXT NOT NULL,
    formula_versions_json TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT ''
);
"""

_SYMBOL_META = {
    "name",
    "units",
    "description",
    "min_value",
    "max_value",
    "adjustable",
    "comment",
    "source",
}


def default_db_path() -> Path:
    directory = Path(user_data_dir("millrepair", "MillRepair"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "millrepair.sqlite"


def version_snapshot(model: Model) -> dict[str, Any]:
    """Ссылки на версии, по которым посчитан результат."""
    return {
        "symbols": {
            item.name: item.formula.version_id
            for item in model.symbols
            if item.formula is not None and item.formula.version_id is not None
        },
        "parameters": {
            item.name: item.value_version_id
            for item in model.symbols
            if item.value_version_id is not None
        },
        "failure_modes": {
            f"{unit.name}/{mode.name}/{role}": formula.version_id
            for unit in model.units
            for mode in unit.failure_modes
            for role, formula in mode.formulas.items()
            if formula.version_id is not None
        },
    }


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def migrate(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT INTO schema_version(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            self.conn.commit()
        elif int(row["version"]) > SCHEMA_VERSION:
            raise ModelError(f"база новее программы: версия схемы {row['version']}")

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            return 0
        return int(row["version"])

    def ensure_default(self) -> None:
        self.migrate()
        count = self.conn.execute("SELECT COUNT(*) AS n FROM models").fetchone()["n"]
        if count == 0:
            self.insert_model(load_default_model(), activate=True)

    def list_models(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, description, criterion, is_active FROM models ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def active_model_id(self) -> int | None:
        row = self.conn.execute("SELECT id FROM models WHERE is_active = 1").fetchone()
        if row is None:
            return None
        return int(row["id"])

    def set_active_model(self, model_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE models SET is_active = 0")
            updated = self.conn.execute(
                "UPDATE models SET is_active = 1 WHERE id = ?",
                (model_id,),
            )
            if updated.rowcount != 1:
                raise ModelError("модель не найдена")

    def load_active_model(self) -> Model:
        model_id = self.active_model_id()
        if model_id is None:
            raise ModelError("нет активной модели")
        return self.load_model(model_id)

    def load_model(self, model_id: int) -> Model:
        row = self.conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if row is None:
            raise ModelError("модель не найдена")
        symbols = [
            self._symbol_from_row(item)
            for item in self.conn.execute(
                "SELECT * FROM symbols WHERE model_id = ? ORDER BY sort_order, id",
                (model_id,),
            )
        ]
        units = []
        for unit_row in self.conn.execute(
            "SELECT * FROM units WHERE model_id = ? ORDER BY sort_order, id",
            (model_id,),
        ):
            modes = []
            for mode_row in self.conn.execute(
                "SELECT * FROM failure_modes WHERE unit_id = ? ORDER BY sort_order, id",
                (unit_row["id"],),
            ):
                formulas = {}
                for role in FORMULA_ROLES:
                    formula = self._active_formula(failure_mode_id=int(mode_row["id"]), role=role)
                    if formula is not None:
                        formulas[role] = formula
                modes.append(
                    FailureMode(
                        id=int(mode_row["id"]),
                        unit_id=int(unit_row["id"]),
                        name=mode_row["name"],
                        description=mode_row["description"],
                        measurement_quantity=mode_row["measurement_quantity"],
                        rate_parameter=mode_row["rate_parameter"],
                        formulas=formulas,
                        sort_order=int(mode_row["sort_order"]),
                    )
                )
            units.append(
                Unit(
                    id=int(unit_row["id"]),
                    name=unit_row["name"],
                    description=unit_row["description"],
                    weight=float(unit_row["weight"]),
                    multiplicity=unit_row["multiplicity"],
                    failure_modes=modes,
                    sort_order=int(unit_row["sort_order"]),
                )
            )
        return Model(
            id=int(row["id"]),
            name=row["name"],
            description=row["description"],
            criterion=row["criterion"],
            cycle_start=row["cycle_start"],
            symbols=symbols,
            units=units,
        )

    def insert_model(self, model: Model, *, activate: bool = True) -> int:
        if self.conn.execute("SELECT 1 FROM models WHERE name = ?", (model.name,)).fetchone():
            raise ModelError(f"модель «{model.name}» уже есть")
        with self.conn:
            if activate:
                self.conn.execute("UPDATE models SET is_active = 0")
            cursor = self.conn.execute(
                """
                INSERT INTO models (name, description, criterion, cycle_start, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    model.name,
                    model.description,
                    model.criterion,
                    model.cycle_start,
                    1 if activate else 0,
                    utcnow_iso(),
                ),
            )
            model_id = int(cursor.lastrowid)
            for index, symbol in enumerate(model.symbols):
                self._insert_symbol(model_id, symbol, index)
            for index, unit in enumerate(model.units):
                self._insert_unit(model_id, unit, index)
        return model_id

    def copy_model(self, model_id: int, new_name: str) -> int:
        source = self.load_model(model_id)
        source.name = new_name
        source.id = None
        return self.insert_model(source, activate=True)

    def set_criterion(self, model_id: int, criterion: str) -> None:
        if criterion not in {"A", "B"}:
            raise ModelError("критерий должен быть A или B")
        with self.conn:
            self.conn.execute(
                "UPDATE models SET criterion = ? WHERE id = ?",
                (criterion, model_id),
            )

    def set_cycle_start(self, model_id: int, cycle_start: str | None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE models SET cycle_start = ? WHERE id = ?",
                (cycle_start, model_id),
            )

    def add_formula_version(
        self,
        *,
        expression: str,
        comment: str,
        source: str,
        role: str,
        symbol_id: int | None = None,
        failure_mode_id: int | None = None,
    ) -> int:
        if (symbol_id is None) == (failure_mode_id is None):
            raise ModelError("формула должна ссылаться либо на величину, либо на вид отказа")
        with self.conn:
            if symbol_id is not None:
                self.conn.execute(
                    """
                    UPDATE formula_versions SET is_active = 0
                    WHERE symbol_id = ? AND role = ? AND is_active = 1
                    """,
                    (symbol_id, role),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE formula_versions SET is_active = 0
                    WHERE failure_mode_id = ? AND role = ? AND is_active = 1
                    """,
                    (failure_mode_id, role),
                )
            cursor = self.conn.execute(
                """
                INSERT INTO formula_versions (
                    symbol_id, failure_mode_id, role, expression, comment, source, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    symbol_id,
                    failure_mode_id,
                    role,
                    expression,
                    comment,
                    source,
                    utcnow_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def formula_history(
        self,
        *,
        symbol_id: int | None = None,
        failure_mode_id: int | None = None,
        role: str,
    ) -> list[dict[str, Any]]:
        if symbol_id is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM formula_versions
                WHERE symbol_id = ? AND role = ?
                ORDER BY id
                """,
                (symbol_id, role),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM formula_versions
                WHERE failure_mode_id = ? AND role = ?
                ORDER BY id
                """,
                (failure_mode_id, role),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_formula_version(self, version_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM formula_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ModelError("версия формулы не найдена")
        return dict(row)

    def rollback_formula(self, version_id: int) -> int:
        row = self.get_formula_version(version_id)
        comment = f"Откат к версии от {row['created_at']}. {row['comment']}".strip()
        return self.add_formula_version(
            symbol_id=row["symbol_id"],
            failure_mode_id=row["failure_mode_id"],
            role=row["role"],
            expression=row["expression"],
            comment=comment,
            source=row["source"] or "",
        )

    def set_symbol_value(
        self,
        symbol_id: int,
        value: float,
        *,
        comment: str = "",
        source: str = "",
    ) -> int:
        symbol = self._require_symbol(symbol_id)
        if symbol["kind"] not in {"regime", "parameter"}:
            raise ModelError("числовую версию можно сохранить только у переменной или параметра")
        with self.conn:
            self.conn.execute(
                "UPDATE parameter_versions SET is_active = 0 WHERE symbol_id = ? AND is_active = 1",
                (symbol_id,),
            )
            cursor = self.conn.execute(
                """
                INSERT INTO parameter_versions (symbol_id, value, comment, source, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (symbol_id, float(value), comment, source, utcnow_iso()),
            )
            self.conn.execute(
                "UPDATE symbols SET value = ?, comment = ?, source = ? WHERE id = ?",
                (float(value), comment, source, symbol_id),
            )
            return int(cursor.lastrowid)

    def update_symbol_meta(self, symbol_id: int, fields: dict[str, Any]) -> None:
        unknown = set(fields) - _SYMBOL_META
        if unknown:
            raise ModelError("нельзя менять поля: " + ", ".join(sorted(unknown)))
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self.conn:
            self.conn.execute(
                f"UPDATE symbols SET {assignments} WHERE id = ?",
                (*fields.values(), symbol_id),
            )

    def update_unit(
        self,
        unit_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        weight: float | None = None,
        multiplicity: int | None = None,
        multiplicity_set: bool = False,
    ) -> None:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if description is not None:
            fields["description"] = description
        if weight is not None:
            fields["weight"] = weight
        if multiplicity_set:
            fields["multiplicity"] = multiplicity
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.conn:
            self.conn.execute(
                f"UPDATE units SET {assignments} WHERE id = ?",
                (*fields.values(), unit_id),
            )

    def update_failure_mode(self, mode_id: int, fields: dict[str, Any]) -> None:
        allowed = {"name", "description", "measurement_quantity", "rate_parameter"}
        if set(fields) - allowed:
            raise ModelError("нельзя менять эти поля вида отказа")
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.conn:
            self.conn.execute(
                f"UPDATE failure_modes SET {assignments} WHERE id = ?",
                (*fields.values(), mode_id),
            )

    def add_symbol(self, model_id: int, symbol: Symbol) -> int:
        order = self._next_sort("symbols", "model_id", model_id)
        with self.conn:
            return self._insert_symbol(model_id, symbol, order)

    def delete_symbol(self, symbol_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM symbols WHERE id = ?", (symbol_id,))

    def add_unit(self, model_id: int, name: str, description: str = "", weight: float = 1.0) -> int:
        order = self._next_sort("units", "model_id", model_id)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO units (model_id, name, description, weight, multiplicity, sort_order)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (model_id, name, description, weight, order),
            )
            return int(cursor.lastrowid)

    def delete_unit(self, unit_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM units WHERE id = ?", (unit_id,))

    def add_failure_mode(
        self,
        unit_id: int,
        name: str,
        *,
        description: str = "",
        measurement_quantity: str = "",
        rate_parameter: str = "",
        formulas: dict[str, Formula] | None = None,
    ) -> int:
        order = self._next_sort("failure_modes", "unit_id", unit_id)
        prepared = formulas if formulas is not None else _default_mode_formulas()
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO failure_modes (
                    unit_id, name, description, measurement_quantity, rate_parameter, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (unit_id, name, description, measurement_quantity, rate_parameter, order),
            )
            mode_id = int(cursor.lastrowid)
            for role, formula in prepared.items():
                self._insert_formula_row(
                    symbol_id=None,
                    failure_mode_id=mode_id,
                    role=role,
                    formula=formula,
                )
            return mode_id

    def delete_failure_mode(self, mode_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM failure_modes WHERE id = ?", (mode_id,))

    def list_measurements(self, model_id: int) -> list[MeasurementPoint]:
        rows = self.conn.execute(
            """
            SELECT * FROM measurements WHERE model_id = ?
            ORDER BY measured_at, id
            """,
            (model_id,),
        ).fetchall()
        return [
            MeasurementPoint(
                id=int(row["id"]),
                measured_at=parse_datetime(row["measured_at"]),
                unit_name=row["unit_name"],
                quantity=row["quantity"],
                value=float(row["value"]),
                comment=row["comment"],
            )
            for row in rows
        ]

    def add_measurement(
        self,
        model_id: int,
        *,
        measured_at: str,
        unit_name: str,
        quantity: str,
        value: float,
        comment: str = "",
    ) -> int:
        stamp = parse_datetime(measured_at).isoformat()
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO measurements (model_id, measured_at, unit_name, quantity, value, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (model_id, stamp, unit_name, quantity, float(value), comment),
            )
            return int(cursor.lastrowid)

    def delete_measurement(self, measurement_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))

    def list_periods(self, model_id: int) -> list[RegimePeriod]:
        rows = self.conn.execute(
            "SELECT * FROM regime_periods WHERE model_id = ? ORDER BY start_at, id",
            (model_id,),
        ).fetchall()
        periods = []
        for row in rows:
            raw = json.loads(row["regime_json"])
            periods.append(
                RegimePeriod(
                    id=int(row["id"]),
                    start=parse_datetime(row["start_at"]),
                    end=parse_datetime(row["end_at"]),
                    values={key: float(value) for key, value in raw.items()},
                    comment=row["comment"],
                )
            )
        return periods

    def add_period(
        self,
        model_id: int,
        *,
        start_at: str,
        end_at: str,
        values: dict[str, float],
        comment: str = "",
    ) -> int:
        start = parse_datetime(start_at)
        end = parse_datetime(end_at)
        if end <= start:
            raise ModelError("конец периода должен быть позже начала")
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO regime_periods (model_id, start_at, end_at, regime_json, comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    start.isoformat(),
                    end.isoformat(),
                    json.dumps(values, ensure_ascii=False),
                    comment,
                ),
            )
            return int(cursor.lastrowid)

    def delete_period(self, period_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM regime_periods WHERE id = ?", (period_id,))

    def save_result(
        self,
        model: Model,
        *,
        kind: str,
        criterion: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        comment: str = "",
    ) -> int:
        if model.id is None:
            raise ModelError("у модели нет идентификатора базы")
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO results (
                    model_id, created_at, kind, criterion, inputs_json, outputs_json,
                    formula_versions_json, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model.id,
                    utcnow_iso(),
                    kind,
                    criterion,
                    json.dumps(inputs, ensure_ascii=False),
                    json.dumps(outputs, ensure_ascii=False),
                    json.dumps(version_snapshot(model), ensure_ascii=False),
                    comment,
                ),
            )
            return int(cursor.lastrowid)

    def list_results(self, model_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, created_at, kind, criterion, comment
            FROM results WHERE model_id = ? ORDER BY id DESC
            """,
            (model_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_result(self, result_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM results WHERE id = ?", (result_id,)).fetchone()
        if row is None:
            raise ModelError("результат не найден")
        payload = dict(row)
        payload["inputs"] = json.loads(payload.pop("inputs_json"))
        payload["outputs"] = json.loads(payload.pop("outputs_json"))
        payload["formula_versions"] = json.loads(payload.pop("formula_versions_json"))
        return payload

    def _insert_symbol(self, model_id: int, symbol: Symbol, order: int) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO symbols (
                model_id, kind, name, units, description, value, min_value, max_value,
                adjustable, comment, source, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_id,
                symbol.kind,
                symbol.name,
                symbol.units,
                symbol.description,
                symbol.value,
                symbol.min_value,
                symbol.max_value,
                1 if symbol.adjustable else 0,
                symbol.comment if symbol.formula is None else symbol.formula.comment,
                symbol.source if symbol.formula is None else symbol.formula.source,
                order,
            ),
        )
        symbol_id = int(cursor.lastrowid)
        if symbol.kind in {"regime", "parameter"} and symbol.value is not None:
            self.conn.execute(
                """
                INSERT INTO parameter_versions (symbol_id, value, comment, source, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (symbol_id, float(symbol.value), symbol.comment, symbol.source, utcnow_iso()),
            )
        if symbol.formula is not None:
            self._insert_formula_row(
                symbol_id=symbol_id,
                failure_mode_id=None,
                role="expression",
                formula=symbol.formula,
            )
        return symbol_id

    def _insert_unit(self, model_id: int, unit: Unit, order: int) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO units (model_id, name, description, weight, multiplicity, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (model_id, unit.name, unit.description, unit.weight, unit.multiplicity, order),
        )
        unit_id = int(cursor.lastrowid)
        for index, mode in enumerate(unit.failure_modes):
            mode_cursor = self.conn.execute(
                """
                INSERT INTO failure_modes (
                    unit_id, name, description, measurement_quantity, rate_parameter, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_id,
                    mode.name,
                    mode.description,
                    mode.measurement_quantity,
                    mode.rate_parameter,
                    index,
                ),
            )
            mode_id = int(mode_cursor.lastrowid)
            for role, formula in mode.formulas.items():
                self._insert_formula_row(
                    symbol_id=None,
                    failure_mode_id=mode_id,
                    role=role,
                    formula=formula,
                )
        return unit_id

    def _insert_formula_row(
        self,
        *,
        symbol_id: int | None,
        failure_mode_id: int | None,
        role: str,
        formula: Formula,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO formula_versions (
                symbol_id, failure_mode_id, role, expression, comment, source, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                symbol_id,
                failure_mode_id,
                role,
                formula.expression,
                formula.comment,
                formula.source,
                utcnow_iso(),
            ),
        )
        return int(cursor.lastrowid)

    def _symbol_from_row(self, row: sqlite3.Row) -> Symbol:
        value_row = self.conn.execute(
            """
            SELECT * FROM parameter_versions
            WHERE symbol_id = ? AND is_active = 1
            """,
            (row["id"],),
        ).fetchone()
        formula = self._active_formula(symbol_id=int(row["id"]), role="expression")
        value = row["value"]
        comment = row["comment"]
        source = row["source"]
        value_version_id = None
        if value_row is not None:
            value = value_row["value"]
            comment = value_row["comment"]
            source = value_row["source"]
            value_version_id = int(value_row["id"])
        return Symbol(
            id=int(row["id"]),
            kind=row["kind"],
            name=row["name"],
            units=row["units"],
            description=row["description"],
            value=None if value is None else float(value),
            min_value=None if row["min_value"] is None else float(row["min_value"]),
            max_value=None if row["max_value"] is None else float(row["max_value"]),
            adjustable=bool(row["adjustable"]),
            formula=formula,
            comment=comment,
            source=source,
            sort_order=int(row["sort_order"]),
            value_version_id=value_version_id,
        )

    def _active_formula(
        self, *, role: str, symbol_id: int | None = None, failure_mode_id: int | None = None
    ) -> Formula | None:
        if symbol_id is not None:
            row = self.conn.execute(
                """
                SELECT * FROM formula_versions
                WHERE symbol_id = ? AND role = ? AND is_active = 1
                """,
                (symbol_id, role),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT * FROM formula_versions
                WHERE failure_mode_id = ? AND role = ? AND is_active = 1
                """,
                (failure_mode_id, role),
            ).fetchone()
        if row is None:
            return None
        return Formula(
            expression=row["expression"],
            comment=row["comment"],
            source=row["source"],
            version_id=int(row["id"]),
            created_at=row["created_at"],
        )

    def _require_symbol(self, symbol_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        if row is None:
            raise ModelError("величина не найдена")
        return row

    def _next_sort(self, table: str, column: str, owner_id: int) -> int:
        row = self.conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) AS n FROM {table} WHERE {column} = ?",
            (owner_id,),
        ).fetchone()
        return int(row["n"]) + 1


def _default_mode_formulas() -> dict[str, Formula]:
    note = "формула по умолчанию для нового вида отказа"
    expressions = {
        "wear_rate": "0.001",
        "residual": "(measured - consumed) if has_measurement else (1 - consumed)",
        "t_det": "R / v",
        "eta": "t_det / gamma(1 + 1/2)",
        "reliability": "exp(-(t/eta)**2)",
        "t_fail": "eta * (-log(eps))**(1/2)",
    }
    return {role: Formula(expression, note, "") for role, expression in expressions.items()}
