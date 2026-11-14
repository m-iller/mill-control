"""Вкладка модели: дерево формул, редактор и история версий."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from millrepair.engine import CompiledModel, calculate, reliability_curve
from millrepair.expr import evaluate
from millrepair.io_json import ModelImportError, load_model_file, save_model_file
from millrepair.model import (
    FORMULA_ROLES,
    ROLE_LOCAL_NAMES,
    ROLE_TITLES,
    analyze_dependencies,
    formula_problems,
)
from millrepair.ui.formula_editor import FormulaEditor
from millrepair.ui.history_dialog import HistoryDialog
from millrepair.util import format_number


class ModelTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.payload: dict[str, Any] | None = None
        self.combo = QComboBox()
        self.combo.setObjectName("modelCombo")
        self.combo.currentIndexChanged.connect(self._activate_selected)
        copy_button = QPushButton("Копировать модель")
        copy_button.setObjectName("copyModelButton")
        copy_button.clicked.connect(self._copy_model)
        export_button = QPushButton("Экспорт JSON")
        export_button.setObjectName("exportJsonButton")
        export_button.clicked.connect(self._export_json)
        import_button = QPushButton("Импорт JSON")
        import_button.setObjectName("importJsonButton")
        import_button.clicked.connect(self._import_json)
        header = QHBoxLayout()
        header.addWidget(QLabel("Модель"))
        header.addWidget(self.combo, 1)
        header.addWidget(copy_button)
        header.addWidget(export_button)
        header.addWidget(import_button)

        self.tree = QTreeWidget()
        self.tree.setObjectName("modelTree")
        self.tree.setHeaderLabel("Состав модели")
        self.tree.currentItemChanged.connect(lambda *_: self._load_current())

        self.title = QLabel("Элемент не выбран")
        self.title.setObjectName("elementTitle")
        self.units_edit = QLineEdit()
        self.units_edit.setObjectName("unitsEdit")
        self.description_edit = QLineEdit()
        self.description_edit.setObjectName("descriptionEdit")
        self.value_edit = QLineEdit()
        self.value_edit.setObjectName("valueEdit")
        self.min_edit = QLineEdit()
        self.min_edit.setObjectName("minEdit")
        self.max_edit = QLineEdit()
        self.max_edit.setObjectName("maxEdit")
        self.adjustable = QCheckBox("Регулируемая")
        self.adjustable.setObjectName("adjustableBox")
        self.editor = FormulaEditor()
        self.editor.check_button.clicked.connect(self._check)
        self.editor.save_button.clicked.connect(self._save)
        self.editor.history_button.clicked.connect(self._history)
        meta = QFormLayout()
        meta.addRow("Единицы", self.units_edit)
        meta.addRow("Описание", self.description_edit)
        meta.addRow("Значение", self.value_edit)
        meta.addRow("Минимум", self.min_edit)
        meta.addRow("Максимум", self.max_edit)
        meta.addRow("", self.adjustable)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.title)
        right_layout.addLayout(meta)
        right_layout.addWidget(self.editor, 1)
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        add_unit = QPushButton("Добавить узел")
        add_unit.setObjectName("addUnitButton")
        add_unit.clicked.connect(self._add_unit)
        add_mode = QPushButton("Добавить вид отказа")
        add_mode.setObjectName("addModeButton")
        add_mode.clicked.connect(self._add_mode)
        add_symbol = QPushButton("Добавить величину")
        add_symbol.setObjectName("addSymbolButton")
        add_symbol.clicked.connect(self._add_symbol)
        delete = QPushButton("Удалить")
        delete.setObjectName("deleteButton")
        delete.clicked.connect(self._delete)
        footer = QHBoxLayout()
        footer.addWidget(add_unit)
        footer.addWidget(add_mode)
        footer.addWidget(add_symbol)
        footer.addWidget(delete)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)
        layout.addLayout(footer)
        self._numeric_widgets = (self.value_edit, self.min_edit, self.max_edit, self.adjustable)

    def reload(self) -> None:
        model = self.window.model
        self.combo.blockSignals(True)
        self.combo.clear()
        active_index = 0
        for index, row in enumerate(self.window.db.list_models()):
            self.combo.addItem(row["name"], row["id"])
            if row["id"] == model.id:
                active_index = index
        self.combo.setCurrentIndex(active_index)
        self.combo.blockSignals(False)
        self._fill_tree()

    def _fill_tree(self) -> None:
        selected = self.payload
        self.tree.blockSignals(True)
        self.tree.clear()
        model = self.window.model
        units_root = self._group("Узлы")
        for unit in model.units:
            unit_item = QTreeWidgetItem([unit.name])
            unit_item.setData(0, Qt.UserRole, {"type": "unit", "id": unit.id, "name": unit.name})
            unit_item.setToolTip(0, unit.description)
            for mode in unit.failure_modes:
                mode_item = QTreeWidgetItem([mode.name])
                mode_item.setData(
                    0,
                    Qt.UserRole,
                    {"type": "mode", "id": mode.id, "unit_id": unit.id, "name": mode.name},
                )
                for role in FORMULA_ROLES:
                    formula = mode.formulas.get(role)
                    if formula is None:
                        continue
                    role_item = QTreeWidgetItem([ROLE_TITLES[role]])
                    role_item.setData(
                        0,
                        Qt.UserRole,
                        {
                            "type": "mode_formula",
                            "mode_id": mode.id,
                            "unit_id": unit.id,
                            "role": role,
                            "name": f"{unit.name}/{mode.name}",
                        },
                    )
                    mode_item.addChild(role_item)
                unit_item.addChild(mode_item)
            units_root.addChild(unit_item)
        self.tree.addTopLevelItem(units_root)
        self._add_symbol_group("Производные величины", "derived")
        self._add_symbol_group("Переменные режима", "regime")
        self._add_symbol_group("Параметры", "parameter")
        self._add_symbol_group("Технологические формулы", "technology")
        self.tree.expandAll()
        self.tree.blockSignals(False)
        if selected is not None:
            self._reselect(selected)

    def _group(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.UserRole, {"type": "group", "name": title})
        return item

    def _add_symbol_group(self, title: str, kind: str) -> None:
        root = self._group(title)
        for symbol in self.window.model.symbols:
            if symbol.kind != kind:
                continue
            item = QTreeWidgetItem([symbol.name])
            item.setToolTip(0, symbol.description)
            item.setData(
                0,
                Qt.UserRole,
                {"type": "symbol", "id": symbol.id, "name": symbol.name, "kind": kind},
            )
            root.addChild(item)
        self.tree.addTopLevelItem(root)

    def _reselect(self, payload: dict[str, Any]) -> None:
        found = self._find_item(self.tree.invisibleRootItem(), payload)
        if found is not None:
            self.tree.setCurrentItem(found)

    def _find_item(
        self, parent: QTreeWidgetItem, payload: dict[str, Any]
    ) -> QTreeWidgetItem | None:
        for index in range(parent.childCount()):
            child = parent.child(index)
            data = child.data(0, Qt.UserRole) or {}
            if data.get("type") == payload.get("type") and _same_target(data, payload):
                return child
            found = self._find_item(child, payload)
            if found is not None:
                return found
        return None

    def _load_current(self) -> None:
        item = self.tree.currentItem()
        data = item.data(0, Qt.UserRole) if item is not None else None
        self.payload = data if isinstance(data, dict) else None
        self._show_payload(self.payload)

    def _show_payload(self, payload: dict[str, Any] | None) -> None:
        formula_mode = payload is not None and _is_formula(payload, self.window.model)
        for widget in self._numeric_widgets:
            widget.setEnabled(payload is not None and payload.get("type") == "symbol")
        self.editor.setEnabled(bool(formula_mode))
        if payload is None or payload.get("type") == "group":
            self.title.setText("Элемент не выбран")
            self.editor.show_message("Выберите формулу, параметр или переменную режима.")
            return
        if payload["type"] == "symbol":
            symbol = self._symbol(payload["id"])
            self.title.setText(f"{symbol.name} — {symbol.description or symbol.kind}")
            self.units_edit.setText(symbol.units)
            self.description_edit.setText(symbol.description)
            self.value_edit.setText("" if symbol.value is None else format_number(symbol.value, 8))
            self.min_edit.setText(
                "" if symbol.min_value is None else format_number(symbol.min_value, 8)
            )
            self.max_edit.setText(
                "" if symbol.max_value is None else format_number(symbol.max_value, 8)
            )
            self.adjustable.setChecked(symbol.adjustable)
            if symbol.formula is not None:
                self.editor.set_expression(
                    symbol.formula.expression, symbol.formula.comment, symbol.formula.source
                )
                self.editor.show_message("Можно проверить формулу и сохранить новую версию.")
            else:
                self.editor.set_expression("", symbol.comment, symbol.source)
                self.editor.show_message("Число сохранится как новая версия значения.")
            return
        if payload["type"] == "mode_formula":
            mode = self._mode(payload["mode_id"])
            formula = mode.formulas[payload["role"]]
            self.title.setText(f"{payload['name']}: {ROLE_TITLES[payload['role']]}")
            self.units_edit.clear()
            self.description_edit.setText(mode.description)
            self.editor.set_expression(formula.expression, formula.comment, formula.source)
            locals_ = ", ".join(sorted(ROLE_LOCAL_NAMES[payload["role"]])) or "нет"
            self.editor.show_message("Локальные имена этой формулы: " + locals_)
            return
        if payload["type"] == "unit":
            unit = self._unit(payload["id"])
            self.title.setText(unit.name)
            self.description_edit.setText(unit.description)
            self.editor.show_message("У узла можно добавить вид отказа или удалить его.")
            return
        if payload["type"] == "mode":
            mode = self._mode(payload["id"])
            self.title.setText(mode.name)
            self.description_edit.setText(mode.description)
            self.editor.show_message("Выберите формулу этого вида отказа.")

    def _check(self) -> None:
        errors, trial = self._validate(save=False)
        if errors:
            self.editor.show_message("\n".join(errors), error=True)
            return
        self.editor.show_message(trial or "Формула записана без ошибок.")

    def _save(self) -> None:
        payload = self.payload
        if payload is None or payload.get("type") not in {"symbol", "mode_formula"}:
            self.editor.show_message("Нечего сохранять: выберите формулу или величину.", error=True)
            return
        errors, trial = self._validate(save=True)
        if errors:
            self.editor.show_message("\n".join(errors), error=True)
            return
        if payload["type"] == "symbol":
            symbol = self._symbol(payload["id"])
            try:
                self._save_symbol_meta(symbol.id)
            except ValueError as exc:
                self.editor.show_message(str(exc), error=True)
                return
            if symbol.formula is not None:
                self.window.db.add_formula_version(
                    symbol_id=symbol.id,
                    role="expression",
                    expression=self.editor.expression(),
                    comment=self.editor.comment_text(),
                    source=self.editor.source_text(),
                )
            elif symbol.kind in {"regime", "parameter"}:
                try:
                    value = _float_field(self.value_edit.text(), "значение")
                except ValueError as exc:
                    self.editor.show_message(str(exc), error=True)
                    return
                self.window.db.set_symbol_value(
                    symbol.id,
                    value,
                    comment=self.editor.comment_text(),
                    source=self.editor.source_text(),
                )
        else:
            self.window.db.add_formula_version(
                failure_mode_id=payload["mode_id"],
                role=payload["role"],
                expression=self.editor.expression(),
                comment=self.editor.comment_text(),
                source=self.editor.source_text(),
            )
        self.window.reload_model()
        self.editor.show_message((trial + "\n" if trial else "") + "Версия сохранена.")

    def _save_symbol_meta(self, symbol_id: int) -> None:
        fields: dict[str, Any] = {
            "units": self.units_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "adjustable": 1 if self.adjustable.isChecked() else 0,
        }
        for key, widget in (("min_value", self.min_edit), ("max_value", self.max_edit)):
            text = widget.text().strip()
            fields[key] = None if text == "" else _float_field(text, key)
        self.window.db.update_symbol_meta(symbol_id, fields)

    def _validate(self, *, save: bool) -> tuple[list[str], str]:
        del save
        payload = self.payload
        if payload is None:
            return ["Элемент не выбран."], ""
        if payload.get("type") == "symbol" and self._symbol(payload["id"]).formula is None:
            return [], "Числовое значение можно сохранить."
        if not _is_formula(payload, self.window.model):
            return ["У этого элемента нет формулы."], ""
        expression = self.editor.expression()
        if payload["type"] == "mode_formula":
            extra = ROLE_LOCAL_NAMES[payload["role"]]
            owner = payload["name"]
        else:
            extra = set()
            owner = payload["name"]
        errors = formula_problems(self.window.model, expression, extra_names=extra, owner=owner)
        if errors:
            return errors, ""
        if payload["type"] == "symbol" and payload.get("kind") in {"derived", "technology"}:
            trial_model = self._replaced(expression)
            relevant = [
                item
                for item in analyze_dependencies(trial_model).errors
                if payload["name"] in item or item.startswith("цикл")
            ]
            if relevant:
                return relevant, ""
        try:
            return [], self._trial_text(expression)
        except Exception as exc:
            return [], f"Пробное вычисление не удалось: {exc}"

    def _trial_text(self, expression: str) -> str:
        payload = self.payload or {}
        trial = self._replaced(expression)
        result = calculate(trial)
        if payload.get("type") == "symbol":
            if payload["name"] == "Q":
                return f"Проверка: Q = {format_number(result.Q)}"
            if payload["name"] == "P_prod":
                return f"Проверка: P_prod = {format_number(result.P_prod)}"
            context, errors = CompiledModel(trial).context(trial.regime())
            if errors:
                return "Проверка выполнена, но есть замечания: " + "; ".join(errors)
            value = evaluate(expression, context)
            return f"Проверка: {payload['name']} = {format_number(value)}"
        mode = next(
            item
            for unit in result.units
            for item in unit.modes
            if item.mode == self._mode(payload["mode_id"]).name
            and item.unit == self._unit_name(payload["unit_id"])
        )
        if mode.error:
            return f"Пробное вычисление: {mode.error}"
        field = {
            "wear_rate": mode.v,
            "residual": mode.R,
            "t_det": mode.t_det,
            "eta": mode.eta,
            "t_fail": mode.t_fail,
        }
        if payload["role"] == "reliability":
            curve = reliability_curve(mode, np.array([0.0]))
            shown = None if curve is None else float(curve[0])
            return f"Проверка: P(0) = {format_number(shown)}"
        return f"Проверка: {ROLE_TITLES[payload['role']]} = {format_number(field.get(payload['role']))}"

    def _replaced(self, expression: str):
        trial = copy.deepcopy(self.window.model)
        payload = self.payload or {}
        if payload.get("type") == "symbol":
            symbol = next(item for item in trial.symbols if item.id == payload["id"])
            if symbol.formula is None:
                return trial
            symbol.formula.expression = expression
            return trial
        for unit in trial.units:
            for mode in unit.failure_modes:
                if mode.id == payload.get("mode_id"):
                    mode.formulas[payload["role"]].expression = expression
        return trial

    def _history(self) -> None:
        payload = self.payload
        if payload is None or payload.get("type") not in {"symbol", "mode_formula"}:
            self.editor.show_message("История есть у формулы или числовой величины.", error=True)
            return
        if payload["type"] == "symbol" and self._symbol(payload["id"]).formula is None:
            rows = self.window.db.formula_history(symbol_id=payload["id"], role="expression")
            if not rows:
                versions = self._parameter_history(payload["id"])
                self._open_history(versions, numeric=True)
                return
        if payload["type"] == "symbol":
            versions = self.window.db.formula_history(symbol_id=payload["id"], role="expression")
        else:
            versions = self.window.db.formula_history(
                failure_mode_id=payload["mode_id"],
                role=payload["role"],
            )
        self._open_history(versions, numeric=False)

    def _parameter_history(self, symbol_id: int) -> list[dict[str, Any]]:
        rows = self.window.db.conn.execute(
            "SELECT * FROM parameter_versions WHERE symbol_id = ? ORDER BY id",
            (symbol_id,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "comment": row["comment"],
                "source": row["source"],
                "expression": str(row["value"]),
                "is_active": row["is_active"],
            }
            for row in rows
        ]

    def _open_history(self, versions: list[dict[str, Any]], *, numeric: bool) -> None:
        if not versions:
            self.editor.show_message("Версий пока нет.", error=True)
            return
        dialog = HistoryDialog(versions, self)
        if dialog.exec() == HistoryDialog.Accepted and dialog.chosen_id is not None and not numeric:
            self.window.db.rollback_formula(dialog.chosen_id)
            self.window.reload_model()
            self.editor.show_message("Выполнен откат: создана новая версия со старым выражением.")

    def _activate_selected(self) -> None:
        model_id = self.combo.currentData()
        if model_id is None or model_id == self.window.model.id:
            return
        self.window.db.set_active_model(int(model_id))
        self.window.reload_model()

    def _copy_model(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Копия модели", "Имя копии:", text=self.window.model.name + " (копия)"
        )
        if not ok or not name.strip():
            return
        try:
            self.window.db.copy_model(self.window.model.id, name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Копия", str(exc))
            return
        self.window.reload_model()

    def _export_json(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, "Экспорт модели", "model.json", "JSON (*.json)"
        )
        if not path:
            return
        save_model_file(self.window.model, path)

    def _import_json(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "Импорт модели", "", "JSON (*.json)")
        if not path:
            return
        try:
            model = load_model_file(path)
            self.window.db.insert_model(model, activate=True)
        except (OSError, ModelImportError, Exception) as exc:
            QMessageBox.warning(self, "Импорт", str(exc))
            return
        self.window.reload_model()

    def _add_unit(self) -> None:
        name, ok = QInputDialog.getText(self, "Узел", "Название узла:")
        if not ok or not name.strip():
            return
        try:
            self.window.db.add_unit(self.window.model.id, name.strip())
        except Exception as exc:
            self.editor.show_message(str(exc), error=True)
            return
        self.window.reload_model()

    def _add_mode(self) -> None:
        payload = self.payload or {}
        unit_id = None
        if payload.get("type") == "unit":
            unit_id = payload.get("id")
        elif payload.get("type") in {"mode", "mode_formula"}:
            unit_id = payload.get("unit_id")
        if unit_id is None:
            self.editor.show_message("Сначала выберите узел.", error=True)
            return
        name, ok = QInputDialog.getText(self, "Вид отказа", "Название:")
        if not ok or not name.strip():
            return
        try:
            self.window.db.add_failure_mode(int(unit_id), name.strip())
        except Exception as exc:
            self.editor.show_message(str(exc), error=True)
            return
        self.window.reload_model()

    def _add_symbol(self) -> None:
        kinds = ["regime", "parameter", "derived", "technology"]
        labels = [
            "переменная режима",
            "параметр",
            "производная величина",
            "технологическая формула",
        ]
        label, ok = QInputDialog.getItem(self, "Величина", "Тип:", labels, 1, False)
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "Величина", "Имя (латиницей, как в формуле):")
        if not ok or not name.strip():
            return
        from millrepair.model import Formula, Symbol

        kind = kinds[labels.index(label)]
        symbol = Symbol(
            kind=kind, name=name.strip(), value=0.0 if kind in {"regime", "parameter"} else None
        )
        if kind in {"derived", "technology"}:
            symbol.formula = Formula("0", "новая величина", "")
        try:
            self.window.db.add_symbol(self.window.model.id, symbol)
        except Exception as exc:
            self.editor.show_message(str(exc), error=True)
            return
        self.window.reload_model()

    def _delete(self) -> None:
        payload = self.payload
        if payload is None or payload.get("type") not in {"unit", "mode", "symbol"}:
            self.editor.show_message("Удалять можно узел, вид отказа или величину.", error=True)
            return
        answer = QMessageBox.question(self, "Удаление", "Удалить выбранный элемент?")
        if answer != QMessageBox.Yes:
            return
        if payload["type"] == "unit":
            self.window.db.delete_unit(payload["id"])
        elif payload["type"] == "mode":
            self.window.db.delete_failure_mode(payload["id"])
        else:
            self.window.db.delete_symbol(payload["id"])
        self.payload = None
        self.window.reload_model()

    def _symbol(self, symbol_id: int):
        for symbol in self.window.model.symbols:
            if symbol.id == symbol_id:
                return symbol
        raise KeyError(symbol_id)

    def _mode(self, mode_id: int):
        for unit in self.window.model.units:
            for mode in unit.failure_modes:
                if mode.id == mode_id:
                    return mode
        raise KeyError(mode_id)

    def _unit(self, unit_id: int):
        for unit in self.window.model.units:
            if unit.id == unit_id:
                return unit
        raise KeyError(unit_id)

    def _unit_name(self, unit_id: int) -> str:
        return self._unit(unit_id).name


def _is_formula(payload: dict[str, Any], model) -> bool:
    if payload.get("type") == "mode_formula":
        return True
    if payload.get("type") != "symbol":
        return False
    for symbol in model.symbols:
        if symbol.id == payload.get("id"):
            return symbol.formula is not None
    return False


def _same_target(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("type") != right.get("type"):
        return False
    if left.get("type") == "symbol":
        return left.get("id") == right.get("id")
    if left.get("type") == "mode_formula":
        return left.get("mode_id") == right.get("mode_id") and left.get("role") == right.get("role")
    if left.get("type") in {"unit", "mode"}:
        return left.get("id") == right.get("id")
    return left.get("name") == right.get("name")


def _float_field(text: str, label: str) -> float:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label}: нужно число") from exc
