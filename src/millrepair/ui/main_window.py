"""Главное окно: модель и расчёт. Остальные вкладки добавляются следом."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from millrepair import get_version
from millrepair.cli import open_database
from millrepair.db import Database
from millrepair.ui.tabs.calc_tab import CalcTab
from millrepair.ui.tabs.measurements_tab import MeasurementsTab
from millrepair.ui.tabs.model_tab import ModelTab
from millrepair.ui.tabs.regime_tab import RegimeTab


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.db = database
        self.db.migrate()
        self.db.ensure_default()
        self.model = self.db.load_active_model()
        self.setWindowTitle(f"Окно капремонта мельницы — {get_version()}")
        self.resize(1180, 820)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.model_tab = ModelTab(self)
        self.regime_tab = RegimeTab(self)
        self.measurements_tab = MeasurementsTab(self)
        self.calc_tab = CalcTab(self)
        self.tabs.addTab(self.model_tab, "Модель")
        self.tabs.addTab(self.regime_tab, "Режим и ограничения")
        self.tabs.addTab(self.measurements_tab, "Замеры")
        self.tabs.addTab(self.calc_tab, "Расчёт")
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.reload_model()

    def reload_model(self) -> None:
        self.model = self.db.load_active_model()
        self.model_tab.reload()
        self.regime_tab.reload()
        self.measurements_tab.reload()
        self.calc_tab.reload()

    def _tab_changed(self, _index: int) -> None:
        self.reload_model()

    def closeEvent(self, event) -> None:  # noqa: N802  Qt API
        self.calc_tab.shutdown()
        super().closeEvent(event)


def run_app(db_path: Path | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    database = open_database(db_path)
    window = MainWindow(database)
    window.show()
    code = app.exec()
    database.close()
    return int(code)
