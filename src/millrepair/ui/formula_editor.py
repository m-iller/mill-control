"""Поля формулы: выражение, комментарий, источник и сообщение проверки."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from millrepair.expr import ALLOWED_FUNCTIONS, CONSTANTS


class FormulaEditor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("formulaEditor")
        self.editor.setPlaceholderText("Выражение, например k * (G/G0)**a")
        font = QFont("DejaVu Sans Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        self.editor.setMinimumHeight(120)
        self.comment = QPlainTextEdit()
        self.comment.setObjectName("formulaComment")
        self.comment.setPlaceholderText("Комментарий: что изменили и почему")
        self.comment.setFixedHeight(64)
        self.source = QPlainTextEdit()
        self.source.setObjectName("formulaSource")
        self.source.setPlaceholderText("Источник: статья или учебник")
        self.source.setFixedHeight(48)
        self.check_button = QPushButton("Проверить")
        self.check_button.setObjectName("checkFormulaButton")
        self.save_button = QPushButton("Сохранить версию")
        self.save_button.setObjectName("saveVersionButton")
        self.history_button = QPushButton("История версий")
        self.history_button.setObjectName("historyButton")
        self.message = QLabel("Выберите формулу в дереве.")
        self.message.setObjectName("formulaMessage")
        self.message.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.history_button)
        buttons.addStretch(1)
        hint = QLabel(
            "Функции: "
            + ", ".join(ALLOWED_FUNCTIONS)
            + ". Константы: "
            + ", ".join(CONSTANTS)
            + "."
        )
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Формула"))
        layout.addWidget(self.editor)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Комментарий"))
        layout.addWidget(self.comment)
        layout.addWidget(QLabel("Источник"))
        layout.addWidget(self.source)
        layout.addLayout(buttons)
        layout.addWidget(self.message)

    def set_expression(self, expression: str, comment: str, source: str) -> None:
        self.editor.setPlainText(expression)
        self.comment.setPlainText(comment)
        self.source.setPlainText(source)

    def expression(self) -> str:
        return self.editor.toPlainText()

    def comment_text(self) -> str:
        return self.comment.toPlainText().strip()

    def source_text(self) -> str:
        return self.source.toPlainText().strip()

    def show_message(self, text: str, *, error: bool = False) -> None:
        color = "#8a1f1f" if error else "#1d4a1f"
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
