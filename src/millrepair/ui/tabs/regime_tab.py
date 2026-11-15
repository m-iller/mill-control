"""Режим, границы, критерий, веса и кратности."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from millrepair.ui import theme
from millrepair.util import format_number

_SETTINGS = (
    ("Q_min", "Минимальный выпуск Q_min"),
    ("P_min", "Минимальная производительность P_min"),
    ("eps", "Порог гарантированного отказа ε"),
    ("delta", "Допуск окна δ, ч"),
    ("T_min", "Нижняя граница T_min, ч"),
    ("T_max", "Верхняя граница T_max, ч"),
    ("w_T", "Вес цели «максимальная наработка T»"),
)


class RegimeTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("regimeTable")
        self.table.setHorizontalHeaderLabels(
            ["Имя", "Описание", "Единицы", "Значение", "Мин", "Макс", "Регулируемая"]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.criterion = QComboBox()
        self.criterion.setObjectName("criterionCombo")
        self.criterion.addItem("A — максимум узлов в окне", "A")
        self.criterion.addItem("B — минимум недоработанного ресурса", "B")
        self._setting_edits: dict[str, QLineEdit] = {}
        form = QFormLayout()
        form.addRow("Критерий", self.criterion)
        for name, label in _SETTINGS:
            edit = QLineEdit()
            edit.setObjectName(f"setting_{name}")
            self._setting_edits[name] = edit
            form.addRow(label, edit)
        self.units = QTableWidget(0, 3)
        self.units.setObjectName("unitWeightsTable")
        self.units.setHorizontalHeaderLabels(["Узел", "Вес w", "Кратность k"])
        self.units.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.message = QLabel("")
        self.message.setObjectName("regimeMessage")
        self.message.setWordWrap(True)
        save = QPushButton("Сохранить режим и ограничения")
        save.setObjectName("saveRegimeButton")
        save.clicked.connect(self._save)
        theme.mark_primary(save)
        theme.set_state(self.message, "info")
        for table in (self.table, self.units):
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
        self.units.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        regime_box = QGroupBox("Переменные режима")
        regime_layout = QVBoxLayout(regime_box)
        regime_hint = QLabel("Галочка «регулируемая» отдаёт величину оптимизатору.")
        regime_hint.setObjectName("hintLabel")
        regime_layout.addWidget(regime_hint)
        regime_layout.addWidget(self.table)

        limits_box = QGroupBox("Критерий и ограничения")
        limits_layout = QVBoxLayout(limits_box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(14)
        limits_layout.addLayout(form)
        limits_layout.addStretch(1)

        units_box = QGroupBox("Узлы: вес и кратность замены")
        units_layout = QVBoxLayout(units_box)
        units_hint = QLabel("«Подбирать» перебирает число замен за цикл k от 1 до 4.")
        units_hint.setObjectName("hintLabel")
        units_hint.setWordWrap(True)
        units_layout.addWidget(units_hint)
        units_layout.addWidget(self.units)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        lower.addWidget(limits_box, 1)
        lower.addWidget(units_box, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(regime_box, 2)
        layout.addLayout(lower, 3)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(self.message, 1)
        layout.addLayout(row)

    def reload(self) -> None:
        model = self.window.model
        regime = [item for item in model.symbols if item.kind == "regime"]
        self.table.setRowCount(len(regime))
        for row, symbol in enumerate(regime):
            self._set(row, 0, symbol.name, editable=False)
            self._set(row, 1, symbol.description, editable=False)
            self._set(row, 2, symbol.units, editable=False)
            self._set(row, 3, _text(symbol.value))
            self._set(row, 4, _text(symbol.min_value))
            self._set(row, 5, _text(symbol.max_value))
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            box.setCheckState(
                Qt.CheckState.Checked if symbol.adjustable else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 6, box)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, symbol.id)
        index = self.criterion.findData(model.criterion)
        if index >= 0:
            self.criterion.setCurrentIndex(index)
        for name, edit in self._setting_edits.items():
            symbol = model.symbol(name)
            edit.setText(
                "" if symbol is None or symbol.value is None else format_number(symbol.value, 8)
            )
        self.units.setRowCount(len(model.units))
        for row, unit in enumerate(model.units):
            self._unit_cell(row, unit.name, unit.id)
            self.units.setItem(row, 1, QTableWidgetItem(format_number(unit.weight, 6)))
            combo = QComboBox()
            combo.addItem("подбирать", None)
            for value in (1, 2, 3, 4):
                combo.addItem(str(value), value)
            selected = combo.findData(unit.multiplicity)
            combo.setCurrentIndex(selected if selected >= 0 else 0)
            self.units.setCellWidget(row, 2, combo)
        self.table.resizeColumnsToContents()

    def _save(self) -> None:
        model = self.window.model
        try:
            for row in range(self.table.rowCount()):
                symbol_id = int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
                value = _float_cell(self.table.item(row, 3).text(), "значение")
                minimum = _optional_cell(self.table.item(row, 4).text(), "минимум")
                maximum = _optional_cell(self.table.item(row, 5).text(), "максимум")
                adjustable = self.table.item(row, 6).checkState() == Qt.CheckState.Checked
                self.window.db.update_symbol_meta(
                    symbol_id,
                    {
                        "min_value": minimum,
                        "max_value": maximum,
                        "adjustable": 1 if adjustable else 0,
                    },
                )
                self.window.db.set_symbol_value(symbol_id, value, comment="изменение режима")
            for name, edit in self._setting_edits.items():
                symbol = model.symbol(name)
                if symbol is None or symbol.id is None:
                    continue
                self.window.db.set_symbol_value(
                    symbol.id,
                    _float_cell(edit.text(), name),
                    comment="изменение ограничения",
                )
            self.window.db.set_criterion(model.id, self.criterion.currentData())
            for row, unit in enumerate(model.units):
                weight = _float_cell(self.units.item(row, 1).text(), f"вес {unit.name}")
                multiplicity = self.units.cellWidget(row, 2).currentData()
                self.window.db.update_unit(
                    unit.id,
                    weight=weight,
                    multiplicity=multiplicity,
                    multiplicity_set=True,
                )
        except ValueError as exc:
            theme.set_state(self.message, "error")
            self.message.setText(str(exc))
            return
        self.window.reload_model()
        theme.set_state(self.message, "ok")
        self.message.setText("Режим и ограничения сохранены.")

    def _set(self, row: int, column: int, text: str, *, editable: bool = True) -> None:
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, column, item)

    def _unit_cell(self, row: int, name: str, unit_id: int) -> None:
        item = QTableWidgetItem(name)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setData(Qt.ItemDataRole.UserRole, unit_id)
        self.units.setItem(row, 0, item)


def _text(value: float | None) -> str:
    if value is None:
        return ""
    return format_number(value, 8)


def _float_cell(text: str, label: str) -> float:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label}: нужно число") from exc


def _optional_cell(text: str, label: str) -> float | None:
    if not text.strip():
        return None
    return _float_cell(text, label)
