"""Вкладка расчёта: таблица, графики и оптимизация в фоновом потоке."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from millrepair.engine import CalcResult, calculate
from millrepair.optimize import OptimizeResult, optimize
from millrepair.ui.plots import PlotPanel
from millrepair.util import format_number


class _OptimizeThread(QThread):
    progressed = Signal(int, int, int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, model, measurements, periods) -> None:
        super().__init__()
        self.model = model
        self.measurements = measurements
        self.periods = periods
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            result = optimize(
                self.model,
                measurements=self.measurements,
                periods=self.periods,
                progress=self._progress,
                should_stop=lambda: self._stop,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _progress(self, event) -> None:
        self.progressed.emit(event.index, event.total, event.iteration, event.maxiter)


class CalcTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self._thread: _OptimizeThread | None = None
        self.last_kind = "calc"
        self.calc_button = QPushButton("Посчитать при текущем режиме")
        self.calc_button.setObjectName("calcButton")
        self.calc_button.clicked.connect(self.calculate_current)
        self.optimize_button = QPushButton("Оптимизировать")
        self.optimize_button.setObjectName("optimizeButton")
        self.optimize_button.clicked.connect(self.optimize_current)
        self.cancel_button = QPushButton("Остановить")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.progress = QProgressBar()
        self.progress.setObjectName("optimizeProgress")
        self.progress.setValue(0)
        buttons = QHBoxLayout()
        buttons.addWidget(self.calc_button)
        buttons.addWidget(self.optimize_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.progress, 1)

        self.summary = QLabel("Расчёт ещё не запускался.")
        self.summary.setObjectName("summaryLabel")
        self.summary.setWordWrap(True)
        self.table = QTableWidget(0, 1)
        self.table.setObjectName("resultsTable")
        self.plots = PlotPanel()
        save_button = QPushButton("Сохранить результат")
        save_button.setObjectName("saveResultButton")
        save_button.clicked.connect(self._save_result)
        csv_button = QPushButton("Экспорт CSV")
        csv_button.setObjectName("exportCsvButton")
        csv_button.clicked.connect(self._export_csv)
        png_button = QPushButton("Сохранить графики PNG")
        png_button.setObjectName("savePngButton")
        png_button.clicked.connect(self._save_png)
        files = QHBoxLayout()
        files.addWidget(save_button)
        files.addWidget(csv_button)
        files.addWidget(png_button)
        files.addStretch(1)
        self.saved = QListWidget()
        self.saved.setObjectName("savedResults")
        self.saved.currentRowChanged.connect(self._show_saved)
        self.saved_view = QPlainTextEdit()
        self.saved_view.setObjectName("savedResultView")
        self.saved_view.setReadOnly(True)
        self.saved_view.setPlaceholderText("Сохранённые результаты и версии формул")
        archive = QSplitter()
        archive.addWidget(self.saved)
        archive.addWidget(self.saved_view)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.plots, 3)
        layout.addLayout(files)
        layout.addWidget(QLabel("Сохранённые результаты"))
        layout.addWidget(archive, 1)
        self._outputs: dict | None = None

    def reload(self) -> None:
        self._fill_saved()

    def shutdown(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(2000)

    def calculate_current(self) -> None:
        self.window.reload_model()
        model = self.window.model
        try:
            result = calculate(
                model,
                measurements=self.window.db.list_measurements(model.id),
                periods=self.window.db.list_periods(model.id),
            )
        except Exception as exc:
            self.summary.setText(f"Ошибка расчёта: {exc}")
            return
        self.last_kind = "calc"
        self._show_calc(result)

    def optimize_current(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self.window.reload_model()
        model = copy.deepcopy(self.window.model)
        measurements = self.window.db.list_measurements(model.id)
        periods = self.window.db.list_periods(model.id)
        self._thread = _OptimizeThread(model, measurements, periods)
        self._thread.progressed.connect(self._on_progress)
        self._thread.succeeded.connect(self._on_optimized)
        self._thread.failed.connect(self._on_failed)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.optimize_button.setEnabled(False)
        self.summary.setText("Идёт подбор режима и кратностей…")
        self._thread.start()

    def _cancel(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self.summary.setText("Останавливаем поиск после текущего поколения…")

    def _on_progress(self, index: int, total: int, iteration: int, maxiter: int) -> None:
        total = max(total, 1)
        maxiter = max(maxiter, 1)
        fraction = (index + min(iteration, maxiter) / maxiter) / total
        self.progress.setValue(int(max(0.0, min(fraction, 1.0)) * 100))
        self.summary.setText(
            f"Вариант кратности {index + 1} из {total}, поколение {iteration} из {maxiter}"
        )

    def _on_optimized(self, result: OptimizeResult) -> None:
        self.cancel_button.setEnabled(False)
        self.optimize_button.setEnabled(True)
        self.progress.setValue(100)
        self.last_kind = "optimize"
        self._show_optimize(result)

    def _on_failed(self, message: str) -> None:
        self.cancel_button.setEnabled(False)
        self.optimize_button.setEnabled(True)
        QMessageBox.warning(self, "Оптимизация", message)

    def _show_calc(self, result: CalcResult) -> None:
        headers = ["Узел", "Вид отказа", "v", "R", "t_det, ч", "t_fail, ч", "Ошибка"]
        rows = []
        for unit in result.units:
            for mode in unit.modes:
                rows.append(
                    [
                        unit.name,
                        mode.mode,
                        format_number(mode.v),
                        format_number(mode.R),
                        format_number(mode.t_det),
                        format_number(mode.t_fail),
                        mode.error or "",
                    ]
                )
        self._fill_table(headers, rows)
        remarks = " ".join(result.errors)
        self.summary.setText(
            f"Q = {format_number(result.Q)}    P_prod = {format_number(result.P_prod)}"
            + (f"    {remarks}" if remarks else "")
        )
        self.plots.draw(result, eps=self.window.model.setting("eps"))
        self._outputs = {
            "kind": "calc",
            "Q": result.Q,
            "P_prod": result.P_prod,
            "regime": result.regime,
            "units": [
                {"name": unit.name, "t": unit.t, "error": unit.error} for unit in result.units
            ],
        }

    def _show_optimize(self, result: OptimizeResult) -> None:
        headers = ["Узел", "t, ч", "k", "T/k, ч", "Использование", "В окне", "Ошибка"]
        rows = [
            [
                unit.name,
                format_number(unit.t),
                str(unit.k),
                format_number(unit.replacement),
                format_number(unit.utilization),
                "да" if unit.in_window else "нет",
                unit.error or "",
            ]
            for unit in result.units
        ]
        self._fill_table(headers, rows)
        self.summary.setText(
            f"{result.message}    T = {format_number(result.T)} ч    "
            f"Q = {format_number(result.Q)}    P_prod = {format_number(result.P_prod)}"
        )
        if result.calc is not None:
            self.plots.draw(
                result.calc,
                horizon=result.T,
                multiplicities=result.multiplicities,
                eps=self.window.model.setting("eps"),
            )
        self._outputs = {
            "kind": "optimize",
            "feasible": result.feasible,
            "message": result.message,
            "T": result.T,
            "Q": result.Q,
            "P_prod": result.P_prod,
            "regime": result.regime,
            "multiplicities": result.multiplicities,
            "violations": result.violations,
            "units": [
                {
                    "name": unit.name,
                    "t": unit.t,
                    "k": unit.k,
                    "replacement": unit.replacement,
                    "utilization": unit.utilization,
                    "in_window": unit.in_window,
                    "error": unit.error,
                }
                for unit in result.units
            ],
        }

    def _fill_table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                self.table.setItem(row_index, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _save_result(self) -> None:
        if not self._outputs:
            self.summary.setText("Сначала выполните расчёт.")
            return
        model = self.window.model
        self.window.db.save_result(
            model,
            kind=self._outputs["kind"],
            criterion=model.criterion,
            inputs={"regime": self._outputs.get("regime", {})},
            outputs=self._outputs,
        )
        self._fill_saved()
        self.summary.setText(self.summary.text() + "  Результат записан в базу.")

    def _export_csv(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, "Экспорт таблицы", "result.csv", "CSV (*.csv)"
        )
        if not path:
            return
        import csv

        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            headers = [
                self.table.horizontalHeaderItem(column).text()
                for column in range(self.table.columnCount())
                if self.table.horizontalHeaderItem(column) is not None
            ]
            writer.writerow(headers)
            for row in range(self.table.rowCount()):
                writer.writerow(
                    [
                        self.table.item(row, column).text() if self.table.item(row, column) else ""
                        for column in range(self.table.columnCount())
                    ]
                )

    def _save_png(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(self, "Графики", "plots.png", "PNG (*.png)")
        if not path:
            return
        self.plots.figure.savefig(path, dpi=120)

    def _fill_saved(self) -> None:
        self.saved.clear()
        model_id = self.window.model.id
        if model_id is None:
            return
        for row in self.window.db.list_results(model_id):
            self.saved.addItem(f"{row['created_at']}  {row['kind']}  {row['criterion']}")
            self.saved.item(self.saved.count() - 1).setData(Qt.UserRole, row["id"])

    def _show_saved(self, row: int) -> None:
        if row < 0:
            return
        item = self.saved.item(row)
        result_id = item.data(Qt.UserRole)
        if result_id is None:
            return
        stored = self.window.db.get_result(int(result_id))
        import json

        text = json.dumps(
            {
                "created_at": stored["created_at"],
                "kind": stored["kind"],
                "criterion": stored["criterion"],
                "outputs": stored["outputs"],
                "formula_versions": stored["formula_versions"],
            },
            ensure_ascii=False,
            indent=2,
        )
        self.saved_view.setPlainText(text)
