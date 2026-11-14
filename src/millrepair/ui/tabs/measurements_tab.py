"""Замеры толщин и журнал фактического режима."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from millrepair.csv_import import read_measurement_csv
from millrepair.util import format_number, parse_datetime


class MeasurementsTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.message = QLabel("")
        self.message.setObjectName("measurementsMessage")
        self.message.setWordWrap(True)
        self.cycle_edit = QLineEdit()
        self.cycle_edit.setObjectName("cycleStartEdit")
        self.cycle_edit.setPlaceholderText("2026-01-01T00:00:00+00:00")
        cycle_button = QPushButton("Сохранить начало цикла")
        cycle_button.setObjectName("saveCycleButton")
        cycle_button.clicked.connect(self._save_cycle)
        cycle = QHBoxLayout()
        cycle.addWidget(QLabel("Начало цикла"))
        cycle.addWidget(self.cycle_edit, 1)
        cycle.addWidget(cycle_button)

        self.measure_date = QLineEdit()
        self.measure_unit = QLineEdit()
        self.measure_quantity = QLineEdit()
        self.measure_value = QLineEdit()
        self.measure_comment = QLineEdit()
        for widget, name in (
            (self.measure_date, "measurementDate"),
            (self.measure_unit, "measurementUnit"),
            (self.measure_quantity, "measurementQuantity"),
            (self.measure_value, "measurementValue"),
            (self.measure_comment, "measurementComment"),
        ):
            widget.setObjectName(name)
        add_measure = QPushButton("Добавить замер")
        add_measure.setObjectName("addMeasurementButton")
        add_measure.clicked.connect(self._add_measurement)
        import_button = QPushButton("Импорт CSV")
        import_button.setObjectName("importCsvButton")
        import_button.clicked.connect(self._import_csv)
        delete_measure = QPushButton("Удалить замер")
        delete_measure.clicked.connect(self._delete_measurement)
        measure_buttons = QHBoxLayout()
        measure_buttons.addWidget(add_measure)
        measure_buttons.addWidget(import_button)
        measure_buttons.addWidget(delete_measure)
        measure_buttons.addStretch(1)
        measure_form = QGridLayout()
        for column, (label, widget) in enumerate(
            (
                ("Дата", self.measure_date),
                ("Узел", self.measure_unit),
                ("Величина", self.measure_quantity),
                ("Значение", self.measure_value),
                ("Комментарий", self.measure_comment),
            )
        ):
            measure_form.addWidget(QLabel(label), 0, column)
            measure_form.addWidget(widget, 1, column)
        self.measurements = QTableWidget(0, 5)
        self.measurements.setObjectName("measurementsTable")
        self.measurements.setHorizontalHeaderLabels(
            ["Дата", "Узел", "Величина", "Значение", "Комментарий"]
        )

        self.period_start = QLineEdit()
        self.period_end = QLineEdit()
        self.period_comment = QLineEdit()
        self.period_start.setObjectName("periodStart")
        self.period_end.setObjectName("periodEnd")
        self._regime_edits: dict[str, QLineEdit] = {}
        self.regime_form = QFormLayout()
        add_period = QPushButton("Добавить период")
        add_period.setObjectName("addPeriodButton")
        add_period.clicked.connect(self._add_period)
        delete_period = QPushButton("Удалить период")
        delete_period.clicked.connect(self._delete_period)
        period_buttons = QHBoxLayout()
        period_buttons.addWidget(add_period)
        period_buttons.addWidget(delete_period)
        period_buttons.addStretch(1)
        self.periods = QTableWidget(0, 4)
        self.periods.setObjectName("periodsTable")
        self.periods.setHorizontalHeaderLabels(["Начало", "Конец", "Режим", "Комментарий"])

        layout = QVBoxLayout(self)
        layout.addLayout(cycle)
        layout.addWidget(QLabel("Замеры. Если замер есть, остаточный ресурс считается от него."))
        layout.addLayout(measure_form)
        layout.addLayout(measure_buttons)
        layout.addWidget(self.measurements, 1)
        layout.addWidget(
            QLabel("Фактический режим по периодам. Пропуск заполняется текущими значениями.")
        )
        period_head = QGridLayout()
        period_head.addWidget(QLabel("Начало"), 0, 0)
        period_head.addWidget(self.period_start, 1, 0)
        period_head.addWidget(QLabel("Конец"), 0, 1)
        period_head.addWidget(self.period_end, 1, 1)
        period_head.addWidget(QLabel("Комментарий"), 0, 2)
        period_head.addWidget(self.period_comment, 1, 2)
        layout.addLayout(period_head)
        layout.addLayout(self.regime_form)
        layout.addLayout(period_buttons)
        layout.addWidget(self.periods, 1)
        self.calibration_combo = QComboBox()
        self.calibration_combo.setObjectName("calibrationCombo")
        calibrate = QPushButton("Калибровать коэффициент")
        calibrate.setObjectName("calibrateButton")
        calibrate.clicked.connect(self._calibrate)
        calibration = QHBoxLayout()
        calibration.addWidget(QLabel("Коэффициент износа"))
        calibration.addWidget(self.calibration_combo, 1)
        calibration.addWidget(calibrate)
        layout.addLayout(calibration)
        layout.addWidget(self.message)

    def reload(self) -> None:
        model = self.window.model
        self.cycle_edit.setText(model.cycle_start or "")
        rows = self.window.db.list_measurements(model.id)
        self.measurements.setRowCount(len(rows))
        for index, item in enumerate(rows):
            values = [
                item.measured_at.isoformat(),
                item.unit_name,
                item.quantity,
                format_number(item.value, 8),
                item.comment,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(256, item.id)
                self.measurements.setItem(index, column, cell)
        self._rebuild_regime_fields()
        periods = self.window.db.list_periods(model.id)
        self.periods.setRowCount(len(periods))
        for index, period in enumerate(periods):
            summary = ", ".join(
                f"{key}={format_number(value, 4)}" for key, value in period.values.items()
            )
            values = [period.start.isoformat(), period.end.isoformat(), summary, period.comment]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(256, period.id)
                self.periods.setItem(index, column, cell)
        self.measurements.resizeColumnsToContents()
        self.periods.resizeColumnsToContents()
        self._fill_calibration()

    def _rebuild_regime_fields(self) -> None:
        while self.regime_form.rowCount():
            self.regime_form.removeRow(0)
        self._regime_edits.clear()
        for symbol in self.window.model.symbols:
            if symbol.kind != "regime":
                continue
            edit = QLineEdit(_text(symbol.value))
            edit.setObjectName(f"period_{symbol.name}")
            self._regime_edits[symbol.name] = edit
            suffix = f", {symbol.units}" if symbol.units else ""
            self.regime_form.addRow(symbol.name + suffix, edit)

    def _save_cycle(self) -> None:
        text = self.cycle_edit.text().strip()
        if text:
            try:
                text = parse_datetime(text).isoformat()
            except ValueError as exc:
                self.message.setText(f"Дата начала цикла: {exc}")
                return
        self.window.db.set_cycle_start(self.window.model.id, text or None)
        self.window.reload_model()
        self.message.setText("Начало цикла сохранено.")

    def _add_measurement(self) -> None:
        try:
            stamp = parse_datetime(self.measure_date.text().strip()).isoformat()
            value = float(self.measure_value.text().strip().replace(",", "."))
        except ValueError as exc:
            self.message.setText(f"Замер: {exc}")
            return
        unit = self.measure_unit.text().strip()
        quantity = self.measure_quantity.text().strip()
        if not unit or not quantity:
            self.message.setText("Укажите узел и величину замера.")
            return
        self.window.db.add_measurement(
            self.window.model.id,
            measured_at=stamp,
            unit_name=unit,
            quantity=quantity,
            value=value,
            comment=self.measure_comment.text().strip(),
        )
        self.measure_value.clear()
        self.window.reload_model()
        self.message.setText("Замер добавлен.")

    def _delete_measurement(self) -> None:
        row = self.measurements.currentRow()
        if row < 0 or self.measurements.item(row, 0) is None:
            return
        self.window.db.delete_measurement(int(self.measurements.item(row, 0).data(256)))
        self.window.reload_model()

    def _import_csv(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "Импорт замеров", "", "CSV (*.csv)")
        if not path:
            return
        try:
            rows = read_measurement_csv(path)
            for item in rows:
                self.window.db.add_measurement(
                    self.window.model.id,
                    measured_at=parse_datetime(item["measured_at"]).isoformat(),
                    unit_name=item["unit_name"],
                    quantity=item["quantity"],
                    value=float(item["value"].replace(",", ".")),
                    comment=item.get("comment", ""),
                )
        except (OSError, ValueError) as exc:
            self.message.setText(f"Импорт: {exc}")
            return
        self.window.reload_model()
        self.message.setText(f"Импортировано строк: {len(rows)}.")

    def _add_period(self) -> None:
        try:
            start = parse_datetime(self.period_start.text().strip()).isoformat()
            end = parse_datetime(self.period_end.text().strip()).isoformat()
            values = {
                name: float(edit.text().strip().replace(",", "."))
                for name, edit in self._regime_edits.items()
            }
        except ValueError as exc:
            self.message.setText(f"Период: {exc}")
            return
        try:
            self.window.db.add_period(
                self.window.model.id,
                start_at=start,
                end_at=end,
                values=values,
                comment=self.period_comment.text().strip(),
            )
        except Exception as exc:
            self.message.setText(str(exc))
            return
        self.window.reload_model()
        self.message.setText("Период режима добавлен.")

    def _delete_period(self) -> None:
        row = self.periods.currentRow()
        if row < 0 or self.periods.item(row, 0) is None:
            return
        self.window.db.delete_period(int(self.periods.item(row, 0).data(256)))
        self.window.reload_model()

    def _fill_calibration(self) -> None:
        current = self.calibration_combo.currentData()
        self.calibration_combo.clear()
        for unit in self.window.model.units:
            for mode in unit.failure_modes:
                if not mode.rate_parameter:
                    continue
                label = f"{unit.name} / {mode.name} ({mode.rate_parameter})"
                self.calibration_combo.addItem(label, (unit.name, mode.name))
        if current is not None:
            for index in range(self.calibration_combo.count()):
                if self.calibration_combo.itemData(index) == current:
                    self.calibration_combo.setCurrentIndex(index)
                    break

    def _calibrate(self) -> None:
        from millrepair.calibration import calibrate_rate

        chosen = self.calibration_combo.currentData()
        if not chosen:
            self.message.setText("Нет вида отказа с коэффициентом скорости износа.")
            return
        unit_name, mode_name = chosen
        model = self.window.model
        result = calibrate_rate(
            model,
            unit_name,
            mode_name,
            self.window.db.list_measurements(model.id),
            self.window.db.list_periods(model.id),
        )
        if not result.ok or result.value is None:
            self.message.setText(result.message)
            return
        symbol = model.symbol(result.parameter)
        if symbol is None or symbol.id is None:
            self.message.setText(result.message)
            return
        self.window.db.set_symbol_value(
            symbol.id,
            result.value,
            comment=result.comment,
            source="замеры",
        )
        self.window.reload_model()
        self.message.setText(result.message)


def _text(value: float | None) -> str:
    if value is None:
        return ""
    return format_number(value, 8)
