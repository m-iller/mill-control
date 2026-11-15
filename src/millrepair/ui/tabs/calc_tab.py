"""Вкладка расчёта: таблица, графики и оптимизация в фоновом потоке."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from millrepair.engine import CalcResult, calculate
from millrepair.optimize import OptimizeResult, optimize
from millrepair.ui import theme
from millrepair.ui.plots import PlotPanel
from millrepair.util import format_display, format_number


class _Tile(QFrame):
    """Плитка с одним показателем: подпись и крупное число."""

    def __init__(self, caption: str, name: str) -> None:
        super().__init__()
        self.setObjectName("kpiTile")
        self.caption = QLabel(caption)
        self.caption.setObjectName("kpiCaption")
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        self.value.setProperty("tile", name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)

    def show_value(self, text: str, state: str = "") -> None:
        self.value.setText(text)
        theme.set_state(self.value, state)


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
        theme.mark_primary(self.calc_button)
        self.optimize_button = QPushButton("Подобрать режим и момент ремонта")
        self.optimize_button.setObjectName("optimizeButton")
        self.optimize_button.clicked.connect(self.optimize_current)
        self.cancel_button = QPushButton("Остановить")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.progress = QProgressBar()
        self.progress.setObjectName("optimizeProgress")
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        buttons = QHBoxLayout()
        buttons.addWidget(self.calc_button)
        buttons.addWidget(self.optimize_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.progress, 1)

        self.tile_q = _Tile("Выпуск Q", "Q")
        self.tile_p = _Tile("Производительность P_prod", "P_prod")
        self.tile_first = _Tile("Первый отказ", "first")
        self.tile_t = _Tile("Момент капремонта T", "T")
        self.tile_window = _Tile("Узлов в окне", "window")
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        for tile in (self.tile_q, self.tile_p, self.tile_first, self.tile_t, self.tile_window):
            tiles.addWidget(tile, 1)

        self.summary = QLabel("Расчёт ещё не запускался.")
        self.summary.setObjectName("summaryLabel")
        self.summary.setWordWrap(True)
        theme.set_state(self.summary, "info")
        self.table = QTableWidget(0, 1)
        self.table.setObjectName("resultsTable")
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
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
        files.addStretch(1)
        files.addWidget(save_button)
        files.addWidget(csv_button)
        files.addWidget(png_button)
        self.saved = QListWidget()
        self.saved.setObjectName("savedResults")
        self.saved.setAlternatingRowColors(True)
        self.saved.currentRowChanged.connect(self._show_saved)
        self.saved_view = QPlainTextEdit()
        self.saved_view.setObjectName("savedResultView")
        self.saved_view.setReadOnly(True)
        self.saved_view.setFont(theme.monospace_font(10))
        self.saved_view.setPlaceholderText("Выберите сохранённый результат слева")
        archive = QSplitter()
        archive.addWidget(self.saved)
        archive.addWidget(self.saved_view)
        archive.setStretchFactor(1, 2)
        archive_page = QWidget()
        archive_layout = QVBoxLayout(archive_page)
        archive_layout.addWidget(archive)
        plots_page = QWidget()
        plots_layout = QVBoxLayout(plots_page)
        plots_layout.setContentsMargins(6, 6, 6, 6)
        plots_layout.addWidget(self.plots)
        self.views = QTabWidget()
        self.views.setObjectName("calcViews")
        self.views.addTab(plots_page, "Графики")
        self.views.addTab(archive_page, "Сохранённые результаты")
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(self.table)
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(upper)
        split.addWidget(self.views)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([250, 380])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(buttons)
        layout.addLayout(tiles)
        layout.addWidget(self.summary)
        layout.addWidget(split, 1)
        layout.addLayout(files)
        self._outputs: dict | None = None
        self._csv: tuple[list[str], list[list]] | None = None

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
            theme.set_state(self.summary, "error")
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
        theme.set_state(self.summary, "info")
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
        headers = [
            "Узел",
            "Вид отказа",
            "Скорость v",
            "Остаток R",
            "Среднее t_det, ч",
            "Отказ t_fail, ч",
            "Замечание",
        ]
        rows = []
        limiting: set[int] = set()
        for unit in result.units:
            for mode in unit.modes:
                if unit.t is not None and mode.t_fail == unit.t and len(unit.modes) > 1:
                    limiting.add(len(rows))
                note = mode.error or ("ресурс исчерпан" if mode.exhausted else "")
                rows.append(
                    [
                        unit.name,
                        mode.mode,
                        format_display(mode.v),
                        format_display(mode.R),
                        format_display(mode.t_det, 5),
                        format_display(mode.t_fail, 5),
                        note,
                    ]
                )
        self._fill_table(headers, rows, numeric={2, 3, 4, 5})
        self._csv = (
            headers,
            [
                [unit.name, mode.mode, mode.v, mode.R, mode.t_det, mode.t_fail, mode.error or ""]
                for unit in result.units
                for mode in unit.modes
            ],
        )
        for row in limiting:
            self.table.item(row, 5).setToolTip("Этот вид отказа определяет время узла")
            font = self.table.item(row, 5).font()
            font.setBold(True)
            self.table.item(row, 5).setFont(font)
        for row, values in enumerate(rows):
            if values[6]:
                self._paint_row(row, theme.ERROR_SOFT)
        remarks = " ".join(result.errors)
        self.summary.setText(
            f"Q = {format_number(result.Q)}    P_prod = {format_number(result.P_prod)}"
            + (f"    {remarks}" if remarks else "")
        )
        theme.set_state(self.summary, "error" if remarks else "info")
        self._show_metrics(result)
        self.tile_t.show_value("—")
        self.tile_window.show_value("—")
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
        headers = [
            "Узел",
            "Время до отказа t, ч",
            "Замен за цикл k",
            "Замена через T/k, ч",
            "Использование ресурса",
            "В окне",
            "Замечание",
        ]
        rows = [
            [
                unit.name,
                format_display(unit.t, 5),
                str(unit.k),
                format_display(unit.replacement, 5),
                "—" if unit.utilization is None else f"{unit.utilization * 100:.1f} %",
                "да" if unit.in_window else "нет",
                unit.error or "",
            ]
            for unit in result.units
        ]
        self._fill_table(headers, rows, numeric={1, 2, 3, 4})
        self._csv = (
            headers,
            [
                [
                    unit.name,
                    unit.t,
                    unit.k,
                    unit.replacement,
                    unit.utilization,
                    "да" if unit.in_window else "нет",
                    unit.error or "",
                ]
                for unit in result.units
            ],
        )
        for row, unit in enumerate(result.units):
            cell = self.table.item(row, 5)
            cell.setForeground(QColor(theme.OK if unit.in_window else theme.ERROR))
            if unit.error:
                self._paint_row(row, theme.ERROR_SOFT)
        self.summary.setText(
            f"{result.message}    T = {format_display(result.T, 5)} ч    "
            f"Q = {format_number(result.Q)}    P_prod = {format_number(result.P_prod)}"
        )
        theme.set_state(self.summary, "ok" if result.feasible else "error")
        if result.calc is not None:
            self._show_metrics(result.calc)
        self.tile_t.show_value(f"{format_display(result.T, 5)} ч")
        inside = sum(1 for unit in result.units if unit.in_window)
        self.tile_window.show_value(
            f"{inside} из {len(result.units)}",
            "ok" if result.units and inside == len(result.units) else "",
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

    def _show_metrics(self, result: CalcResult) -> None:
        model = self.window.model
        units = {item.name: item.units for item in model.symbols}
        for tile, name, value, minimum in (
            (self.tile_q, "Q", result.Q, model.setting("Q_min")),
            (self.tile_p, "P_prod", result.P_prod, model.setting("P_min")),
        ):
            suffix = f" {units[name]}" if units.get(name) else ""
            state = ""
            if value is not None and minimum > 0:
                state = "ok" if value >= minimum else "error"
            tile.show_value(format_display(value) + suffix, state)
            tile.setToolTip(f"Нижняя граница: {format_display(minimum)}{suffix}")
        timed = [unit for unit in result.units if unit.t is not None]
        if timed:
            first = min(timed, key=lambda unit: unit.t)
            self.tile_first.show_value(f"{format_display(first.t, 5)} ч")
            self.tile_first.caption.setText(f"Первый отказ: {first.name}")
        else:
            self.tile_first.show_value("—")
            self.tile_first.caption.setText("Первый отказ")

    def _fill_table(
        self, headers: list[str], rows: list[list[str]], *, numeric: set[int] | None = None
    ) -> None:
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                cell = QTableWidgetItem(value)
                if numeric and column in numeric:
                    cell.setTextAlignment(right)
                self.table.setItem(row_index, column, cell)
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(column, self.table.columnWidth(column) + 18)
        header.setStretchLastSection(True)

    def _paint_row(self, row: int, color: str) -> None:
        for column in range(self.table.columnCount()):
            cell = self.table.item(row, column)
            if cell is not None:
                cell.setBackground(QColor(color))

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

        if self._csv is None:
            self.summary.setText("Сначала выполните расчёт.")
            return
        headers, rows = self._csv
        # В файл идут исходные числа, а не округлённые подписи из таблицы.
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(["" if value is None else value for value in row])

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
