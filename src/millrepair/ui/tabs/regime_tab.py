"""Режим, границы, критерий, веса и кратности."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
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

from millrepair.util import format_number

_SETTINGS = (
    ("Q_min", "Q_min, выпуск"),
    ("P_min", "P_min, производительность"),
    ("eps", "eps, порог гарантированного отказа"),
    ("delta", "δ, допуск окна, ч"),
    ("T_min", "T_min, ч"),
    ("T_max", "T_max, ч"),
    ("w_T", "вес цели «максимальная наработка T»"),
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
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Переменные режима. Галочка «регулируемая» отдаёт величину оптимизатору.")
        )
        layout.addWidget(self.table, 2)
        layout.addLayout(form)
        layout.addWidget(
            QLabel("Веса узлов и кратность замены. «Подбирать» перебирает k от 1 до 4.")
        )
        layout.addWidget(self.units, 1)
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
            box = QCheckBox()
            box.setChecked(symbol.adjustable)
            self.table.setCellWidget(row, 6, box)
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
                adjustable = self.table.cellWidget(row, 6).isChecked()
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
            self.message.setText(str(exc))
            return
        self.window.reload_model()
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
