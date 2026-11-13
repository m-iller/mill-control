"""История версий формулы: просмотр, сравнение и откат."""

from __future__ import annotations

import difflib
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class HistoryDialog(QDialog):
    def __init__(self, versions: list[dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("История версий")
        self.resize(760, 480)
        self.versions = versions
        self.chosen_id: int | None = None
        self.list = QListWidget()
        self.list.setObjectName("historyList")
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setObjectName("historyDiff")
        for version in versions:
            mark = "● " if version.get("is_active") else "  "
            comment = version.get("comment") or "без комментария"
            label = f"{mark}{version.get('created_at', '')}  {comment}"
            self.list.addItem(label)
            self.list.item(self.list.count() - 1).setData(Qt.UserRole, version["id"])
        self.list.itemSelectionChanged.connect(self._show_diff)
        rollback = QPushButton("Откатить")
        rollback.setObjectName("rollbackButton")
        rollback.clicked.connect(self._rollback)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(rollback)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Выберите одну версию, чтобы увидеть текст, или две — чтобы сравнить.")
        )
        layout.addWidget(self.list, 1)
        layout.addWidget(self.diff, 2)
        layout.addLayout(buttons)
        if self.list.count():
            self.list.setCurrentRow(self.list.count() - 1)

    def _selected(self) -> list[dict[str, Any]]:
        chosen = []
        for item in self.list.selectedItems():
            version_id = item.data(Qt.UserRole)
            for version in self.versions:
                if version["id"] == version_id:
                    chosen.append(version)
        chosen.sort(key=lambda version: version["id"])
        return chosen

    def _show_diff(self) -> None:
        selected = self._selected()
        if len(selected) >= 2:
            left, right = selected[0], selected[-1]
            diff = difflib.unified_diff(
                left["expression"].splitlines(),
                right["expression"].splitlines(),
                fromfile=str(left.get("created_at", left["id"])),
                tofile=str(right.get("created_at", right["id"])),
                lineterm="",
            )
            text = "\n".join(diff) or "Формулы совпадают."
        elif len(selected) == 1:
            version = selected[0]
            text = (
                f"Источник: {version.get('source') or '—'}\n"
                f"Комментарий: {version.get('comment') or '—'}\n\n"
                f"{version.get('expression', '')}"
            )
        else:
            text = ""
        self.diff.setPlainText(text)

    def _rollback(self) -> None:
        selected = self._selected()
        if len(selected) != 1:
            self.diff.setPlainText("Для отката выберите ровно одну версию.")
            return
        self.chosen_id = int(selected[0]["id"])
        self.accept()
