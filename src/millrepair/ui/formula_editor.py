"""Поля формулы: выражение, его математическая запись, комментарий и источник."""

from __future__ import annotations

import re

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from millrepair.expr import ALLOWED_FUNCTIONS, CONSTANTS
from millrepair.ui import theme
from millrepair.ui.formula_view import FormulaPreview

_PREVIEW_DELAY_MS = 250


class _Highlighter(QSyntaxHighlighter):
    """Подсветка текста формулы: числа, функции, константы и ключевые слова."""

    def __init__(self, document) -> None:
        super().__init__(document)
        number = QTextCharFormat()
        number.setForeground(QColor("#a2470f"))
        function = QTextCharFormat()
        function.setForeground(QColor(theme.ACCENT))
        function.setFontWeight(QFont.Weight.DemiBold)
        keyword = QTextCharFormat()
        keyword.setForeground(QColor("#7a5ea8"))
        keyword.setFontWeight(QFont.Weight.DemiBold)
        names = "|".join(ALLOWED_FUNCTIONS)
        constants = "|".join(CONSTANTS)
        self._rules = [
            (re.compile(r"(?<![\w.])\d+\.?\d*(?:[eE][+-]?\d+)?"), number),
            (re.compile(rf"\b(?:{names})\b(?=\s*\()"), function),
            (re.compile(rf"\b(?:{constants})\b"), keyword),
            (re.compile(r"\b(?:if|else)\b"), keyword),
        ]

    def highlightBlock(self, text: str) -> None:  # noqa: N802  Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)


class FormulaEditor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lhs = ""
        self.preview = FormulaPreview()
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("formulaEditor")
        self.editor.setPlaceholderText("Выражение, например k * (G/G0)**a")
        self.editor.setFont(theme.monospace_font(11))
        self.editor.setMinimumHeight(72)
        self.editor.setMaximumHeight(140)
        self._highlighter = _Highlighter(self.editor.document())
        self.comment = QPlainTextEdit()
        self.comment.setObjectName("formulaComment")
        self.comment.setPlaceholderText("Что изменили и почему")
        self.comment.setFixedHeight(64)
        self.source = QPlainTextEdit()
        self.source.setObjectName("formulaSource")
        self.source.setPlaceholderText("Статья, учебник или паспорт")
        self.source.setFixedHeight(64)
        self.check_button = QPushButton("Проверить")
        self.check_button.setObjectName("checkFormulaButton")
        self.save_button = QPushButton("Сохранить версию")
        self.save_button.setObjectName("saveVersionButton")
        theme.mark_primary(self.save_button)
        self.history_button = QPushButton("История версий")
        self.history_button.setObjectName("historyButton")
        self.message = QLabel("Выберите формулу в дереве.")
        self.message.setObjectName("formulaMessage")
        self.message.setWordWrap(True)
        theme.set_state(self.message, "info")
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.history_button)
        buttons.addStretch(1)
        self.hint = hint = QLabel(
            "Степень пишется как **. Функции: "
            + ", ".join(ALLOWED_FUNCTIONS)
            + ". Константы: "
            + ", ".join(CONSTANTS)
            + ". Условие: a if x < 1 else b."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        self.expression_label = QLabel("Текст формулы")
        self.expression_label.setObjectName("sectionLabel")
        notes = QGridLayout()
        notes.setContentsMargins(0, 0, 0, 0)
        notes.setHorizontalSpacing(12)
        comment_label = QLabel("Комментарий")
        comment_label.setObjectName("sectionLabel")
        source_label = QLabel("Источник")
        source_label.setObjectName("sectionLabel")
        notes.addWidget(comment_label, 0, 0)
        notes.addWidget(source_label, 0, 1)
        notes.addWidget(self.comment, 1, 0)
        notes.addWidget(self.source, 1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.preview)
        layout.addWidget(self.expression_label)
        layout.addWidget(self.editor)
        layout.addWidget(hint)
        layout.addLayout(notes)
        layout.addLayout(buttons)
        layout.addWidget(self.message)
        layout.addStretch(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_PREVIEW_DELAY_MS)
        self._timer.timeout.connect(self.refresh_preview)
        self.editor.textChanged.connect(self._timer.start)
        self.refresh_preview()

    def set_lhs(self, lhs: str) -> None:
        """Левая часть в математической записи: чему равна формула."""
        self._lhs = lhs
        self.refresh_preview()

    def set_expression(self, expression: str, comment: str, source: str) -> None:
        self.editor.setPlainText(expression)
        self.comment.setPlainText(comment)
        self.source.setPlainText(source)
        self._timer.stop()
        self.refresh_preview()

    def set_formula_visible(self, visible: bool) -> None:
        """Скрыть поля формулы у числовой величины: у неё только значение."""
        for widget in (self.preview, self.expression_label, self.editor, self.hint):
            widget.setVisible(visible)

    def refresh_preview(self) -> None:
        expression = self.editor.toPlainText()
        if not expression.strip():
            self.preview.set_formula("", placeholder="Здесь появится формула.")
            return
        self.preview.set_formula(
            expression,
            self._lhs,
            placeholder="Формула не дописана: запись появится, когда текст разберётся.",
        )

    def expression(self) -> str:
        return self.editor.toPlainText()

    def comment_text(self) -> str:
        return self.comment.toPlainText().strip()

    def source_text(self) -> str:
        return self.source.toPlainText().strip()

    def show_message(self, text: str, *, error: bool = False, ok: bool = False) -> None:
        theme.set_state(self.message, "error" if error else ("ok" if ok else "info"))
        self.message.setText(text)
