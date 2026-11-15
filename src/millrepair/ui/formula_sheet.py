"""Лист формул: вся модель в математической записи на одной странице.

Рядом с формулой стоит её значение при текущем режиме, чтобы расчёт можно
было проверить вручную. Лист сохраняется картинкой.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from millrepair.engine import CompiledModel, calculate
from millrepair.latex import ROLE_LHS, name_to_latex
from millrepair.model import FORMULA_ROLES, ROLE_TITLES, Model
from millrepair.ui.formula_view import FormulaLabel
from millrepair.util import as_float, format_display


class FormulaSheetDialog(QDialog):
    def __init__(self, model: Model, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Формулы модели «{model.name}»")
        self.resize(900, 760)
        self.formula_count = 0
        self.sheet = QWidget()
        self.sheet.setObjectName("formulaSheetBody")
        self.body = QVBoxLayout(self.sheet)
        self.body.setContentsMargins(20, 12, 20, 20)
        self.body.setSpacing(0)
        self._fill(model)
        self.body.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("formulaSheet")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.sheet)
        save = QPushButton("Сохранить как PNG")
        save.setObjectName("saveSheetButton")
        save.clicked.connect(self._save_png)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.reject)
        note = QLabel("Значения справа посчитаны при текущем режиме, без истории замеров.")
        note.setObjectName("hintLabel")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(12, 8, 12, 12)
        buttons.addWidget(note, 1)
        buttons.addWidget(save)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

    def _fill(self, model: Model) -> None:
        values, modes = _current_values(model)
        for title, kind in (
            ("Производные величины", "derived"),
            ("Технологические формулы", "technology"),
        ):
            symbols = [item for item in model.symbols if item.kind == kind and item.formula]
            if not symbols:
                continue
            self._heading(title)
            for symbol in symbols:
                self._card(
                    name_to_latex(symbol.name),
                    symbol.formula.expression,
                    caption=symbol.description or symbol.name,
                    value=values.get(symbol.name),
                    units=symbol.units,
                )
        for unit in model.units:
            for mode in unit.failure_modes:
                self._heading(f"{unit.name}: {mode.name}")
                numbers = modes.get((unit.name, mode.name), {})
                for role in FORMULA_ROLES:
                    formula = mode.formulas.get(role)
                    if formula is None:
                        continue
                    self._card(
                        ROLE_LHS[role],
                        formula.expression,
                        caption=ROLE_TITLES[role],
                        value=numbers.get(role),
                        units="ч" if role in {"t_det", "eta", "t_fail"} else "",
                    )

    def _heading(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("elementTitle")
        label.setContentsMargins(0, 18, 0, 6)
        self.body.addWidget(label)

    def _card(
        self,
        lhs: str,
        expression: str,
        *,
        caption: str,
        value: float | None,
        units: str,
    ) -> None:
        card = QFrame()
        card.setObjectName("formulaCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(0, 8, 0, 8)
        left = QVBoxLayout()
        left.setSpacing(2)
        text = QLabel(caption)
        text.setObjectName("hintLabel")
        text.setWordWrap(True)
        formula = FormulaLabel(size=14.0)
        if not formula.set_formula(expression, lhs):
            formula.setText(expression)
        left.addWidget(text)
        left.addWidget(formula)
        row.addLayout(left, 1)
        if value is not None:
            shown = format_display(value, 5)
            number = QLabel(f"{shown} {units}".strip())
            number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            number.setMinimumWidth(130)
            row.addWidget(number)
        self.body.addWidget(card)
        self.formula_count += 1

    def _save_png(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, "Лист формул", "formulas.png", "PNG (*.png)"
        )
        if not path:
            return
        self.sheet.grab().save(path, "PNG")


def _current_values(
    model: Model,
) -> tuple[dict[str, float], dict[tuple[str, str], dict[str, float | None]]]:
    """Значения производных величин и формул видов отказа при текущем режиме."""
    values: dict[str, float] = {}
    modes: dict[tuple[str, str], dict[str, float | None]] = {}
    try:
        context, _errors = CompiledModel(model).context(model.regime())
        result = calculate(model)
    except Exception:
        return values, modes
    raw: dict[str, Any] = context
    for name, item in raw.items():
        try:
            values[name] = as_float(item, name)
        except (TypeError, ValueError):
            continue
    for unit in result.units:
        for mode in unit.modes:
            modes[(unit.name, mode.mode)] = {
                "wear_rate": mode.v,
                "residual": mode.R,
                "t_det": mode.t_det,
                "eta": mode.eta,
                "t_fail": mode.t_fail,
            }
    return values, modes
