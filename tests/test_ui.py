"""Интерфейс: модель по умолчанию, версии формул, расчёт и графики."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from millrepair.db import Database
from millrepair.ui.main_window import MainWindow

pytestmark = pytest.mark.slow


@pytest.fixture
def window(qtbot, tmp_path):
    database = Database(tmp_path / "ui.sqlite")
    database.migrate()
    database.ensure_default()
    widget = MainWindow(database)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    yield widget
    database.close()


def test_window_opens_with_default_model(window) -> None:
    assert "Окно капремонта" in window.windowTitle()
    assert window.model_tab.combo.currentText() == "Базовая"
    assert window.model.name == "Базовая"
    assert window.model_tab.tree.topLevelItemCount() >= 4
    assert window.isVisible()


def test_saved_formula_is_used_in_calculation(qtbot, window) -> None:
    window.model_tab.tree.setCurrentItem(_find(window, name="Q"))
    assert "G" in window.model_tab.editor.expression()
    window.model_tab.editor.editor.setPlainText("100")
    qtbot.mouseClick(window.model_tab.editor.save_button, Qt.MouseButton.LeftButton)
    assert "100" in window.model_tab.editor.message.text()
    seen: dict[str, int] = {}

    def grab() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        seen["count"] = dialog.list.count()
        dialog.reject()

    QTimer.singleShot(0, grab)
    qtbot.mouseClick(window.model_tab.editor.history_button, Qt.MouseButton.LeftButton)
    assert seen["count"] >= 2
    window.tabs.setCurrentWidget(window.calc_tab)
    qtbot.mouseClick(window.calc_tab.calc_button, Qt.MouseButton.LeftButton)
    assert "Q = 100" in window.calc_tab.summary.text()


def test_bad_formula_shows_message_and_keeps_the_window(qtbot, window) -> None:
    window.model_tab.tree.setCurrentItem(_find(window, name="Q"))
    window.model_tab.editor.editor.setPlainText("1 +")
    qtbot.mouseClick(window.model_tab.editor.check_button, Qt.MouseButton.LeftButton)
    assert "синтаксическ" in window.model_tab.editor.message.text()
    qtbot.mouseClick(window.model_tab.editor.save_button, Qt.MouseButton.LeftButton)
    assert window.isVisible()
    assert "синтаксическ" in window.model_tab.editor.message.text()
    window.tabs.setCurrentWidget(window.calc_tab)
    qtbot.mouseClick(window.calc_tab.calc_button, Qt.MouseButton.LeftButton)
    assert "Q = 72" in window.calc_tab.summary.text()


def test_calculate_fills_table_and_plots(qtbot, window) -> None:
    window.tabs.setCurrentWidget(window.calc_tab)
    qtbot.mouseClick(window.calc_tab.calc_button, Qt.MouseButton.LeftButton)
    assert window.calc_tab.table.rowCount() >= 4
    assert window.calc_tab.plots.ax_residual.lines
    assert window.calc_tab.plots.ax_reliability.lines


def test_formula_is_drawn_as_math(qtbot, window) -> None:
    editor = window.model_tab.editor
    window.model_tab.tree.setCurrentItem(_find(window, name="P_drive"))
    assert editor.preview.label.rendered
    assert not editor.preview.label.pixmap().isNull()
    editor.editor.setPlainText("1 +")
    editor.refresh_preview()
    assert not editor.preview.label.rendered
    assert "не дописана" in editor.preview.label.text()
    window.model_tab.tree.setCurrentItem(_find(window, type="mode_formula", role="residual"))
    assert editor.preview.label.rendered


def test_parameter_value_can_be_saved_from_model_tab(qtbot, window) -> None:
    window.model_tab.tree.setCurrentItem(_find(window, name="k_l"))
    assert window.model_tab.editor.save_button.isEnabled()
    assert not window.model_tab.editor.editor.isVisibleTo(window.model_tab)
    window.model_tab.value_edit.setText("0.02")
    qtbot.mouseClick(window.model_tab.editor.save_button, Qt.MouseButton.LeftButton)
    assert window.model.symbol("k_l").value == pytest.approx(0.02)


def test_formula_sheet_lists_every_formula(qtbot, window) -> None:
    from millrepair.ui.formula_sheet import FormulaSheetDialog

    dialog = FormulaSheetDialog(window.model, window)
    qtbot.addWidget(dialog)
    expected = sum(1 for item in window.model.symbols if item.formula is not None)
    expected += sum(
        len(mode.formulas) for unit in window.model.units for mode in unit.failure_modes
    )
    assert dialog.formula_count == expected


def test_optimize_result_fills_tiles(qtbot, window) -> None:
    from millrepair.optimize import optimize

    window.tabs.setCurrentWidget(window.calc_tab)
    result = optimize(window.model, seed=3, maxiter=2, popsize=3)
    window.calc_tab._show_optimize(result)
    assert window.calc_tab.table.rowCount() == len(window.model.units)
    assert "из" in window.calc_tab.tile_window.value.text()
    assert window.calc_tab.tile_t.value.text().endswith("ч")


def _find(window, **expected):
    def walk(item):
        for index in range(item.childCount()):
            child = item.child(index)
            yield child
            yield from walk(child)

    for item in walk(window.model_tab.tree.invisibleRootItem()):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and all(
            data.get(key) == value for key, value in expected.items()
        ):
            return item
    raise AssertionError(expected)
