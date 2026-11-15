"""Оформление окна: цвета, таблица стилей Qt и вид графиков.

Тема одна, светлая, и не зависит от темы системы: цвета сообщений, формул и
графиков подобраны под неё.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

WINDOW = "#f3f5f7"
SURFACE = "#ffffff"
SURFACE_ALT = "#f8fafb"
BORDER = "#d5dbe1"
BORDER_STRONG = "#b8c1ca"
TEXT = "#1c2733"
TEXT_MUTED = "#627181"
ACCENT = "#1f6f8b"
ACCENT_HOVER = "#185a72"
ACCENT_PRESSED = "#124658"
ACCENT_SOFT = "#e3f0f4"
OK = "#1f7a4d"
OK_SOFT = "#e4f3ea"
ERROR = "#b3261e"
ERROR_SOFT = "#fbe9e7"
WARN = "#8a5a00"
WARN_SOFT = "#fdf3dc"

# Цвета линий узлов на графиках: различимы и при печати в серых тонах.
SERIES = ("#1f6f8b", "#d1603d", "#3f8f5f", "#7a5ea8", "#b8860b", "#52616f")

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background: {WINDOW};
}}
QToolTip {{
    background: {TEXT};
    color: #ffffff;
    border: none;
    padding: 4px 6px;
}}

QTabWidget#mainTabs::pane {{
    border: none;
    border-top: 1px solid {BORDER};
    background: {WINDOW};
}}
QTabWidget#mainTabs > QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 10px 18px;
    margin-right: 2px;
    border: none;
    border-bottom: 3px solid transparent;
    font-weight: 600;
}}
QTabWidget#mainTabs > QTabBar::tab:hover {{
    color: {TEXT};
}}
QTabWidget#mainTabs > QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 3px solid {ACCENT};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 6px 14px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {TEXT};
    border-color: {BORDER};
}}

QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 12px 10px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {TEXT_MUTED};
}}
QGroupBox QLabel {{
    font-weight: 400;
}}

QLabel#elementTitle {{
    font-size: 13pt;
    font-weight: 600;
}}
QLabel#hintLabel, QLabel[role="hint"] {{
    color: {TEXT_MUTED};
}}
QLabel#sectionLabel {{
    color: {TEXT_MUTED};
    font-weight: 600;
}}
QLabel[state="ok"] {{
    color: {OK};
    background: {OK_SOFT};
    border-radius: 6px;
    padding: 6px 10px;
}}
QLabel[state="error"] {{
    color: {ERROR};
    background: {ERROR_SOFT};
    border-radius: 6px;
    padding: 6px 10px;
}}
QLabel[state="info"] {{
    color: {TEXT_MUTED};
    background: transparent;
    padding: 6px 0;
}}

QFrame#kpiTile {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#kpiCaption {{
    color: {TEXT_MUTED};
    font-size: 9pt;
}}
QLabel#kpiValue {{
    font-size: 16pt;
    font-weight: 600;
}}
QLabel#kpiValue[state="ok"] {{
    color: {OK};
    background: transparent;
    padding: 0;
}}
QLabel#kpiValue[state="error"] {{
    color: {ERROR};
    background: transparent;
    padding: 0;
}}

QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {SURFACE_ALT};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {ACCENT_SOFT};
}}
QPushButton:disabled {{
    color: #9aa5b1;
    background: #eef1f4;
    border-color: {BORDER};
}}
QPushButton[primary="true"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[primary="true"]:pressed {{
    background: {ACCENT_PRESSED};
}}
QPushButton[primary="true"]:disabled {{
    background: #a9c3cd;
    border-color: #a9c3cd;
    color: #ffffff;
}}
QPushButton[danger="true"]:hover {{
    border-color: {ERROR};
    color: {ERROR};
}}

QLineEdit, QPlainTextEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{
    background: #eef1f4;
    color: #9aa5b1;
}}
QPlainTextEdit[readOnly="true"] {{
    background: {SURFACE_ALT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}

QScrollArea#formulaPreview {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QScrollArea#formulaPreview > QWidget > QWidget {{
    background: {SURFACE_ALT};
}}
QLabel#formulaPreviewLabel {{
    color: {TEXT_MUTED};
    background: {SURFACE_ALT};
}}
QScrollArea#formulaSheet, QScrollArea#formulaSheet > QWidget > QWidget {{
    background: {SURFACE};
}}
QFrame#formulaCard {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
}}

QTreeWidget, QTableWidget, QListWidget {{
    background: {SURFACE};
    alternate-background-color: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: #e6eaee;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTreeWidget::item, QListWidget::item {{
    padding: 3px 4px;
}}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid #e6eaee;
    padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {SURFACE_ALT};
    border: none;
}}

QProgressBar {{
    background: #e6eaee;
    border: none;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}

QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 8px;
}}
QSplitter::handle:vertical {{
    height: 8px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c3ccd5;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #c3ccd5;
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:hover {{
    background: #9aa5b1;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
}}
"""


def palette() -> QPalette:
    colors = QPalette()
    colors.setColor(QPalette.ColorRole.Window, QColor(WINDOW))
    colors.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    colors.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    colors.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    colors.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    colors.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    colors.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    colors.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    colors.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    colors.setColor(QPalette.ColorRole.ToolTipBase, QColor(TEXT))
    colors.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    colors.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9aa5b1"))
    return colors


def apply(app: QApplication) -> None:
    """Включить тему для всего приложения. Повторный вызов безвреден."""
    style = QStyleFactory.create("Fusion")
    if style is not None:
        app.setStyle(style)
    app.setPalette(palette())
    app.setStyleSheet(STYLESHEET)


def monospace_font(point_size: int = 11) -> QFont:
    """Моноширинный шрифт системы: одинаково находится на Linux и Windows."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


def set_state(widget, state: str) -> None:
    """Сменить вид подписи: ``ok``, ``error`` или ``info``."""
    widget.setProperty("state", state)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def mark_primary(button) -> None:
    button.setProperty("primary", "true")


def mark_danger(button) -> None:
    button.setProperty("danger", "true")


def style_axes(axis) -> None:
    """Спокойный вид графика: без верхней и правой рамки, с бледной сеткой."""
    axis.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(BORDER_STRONG)
    axis.tick_params(colors=TEXT_MUTED, labelsize=9)
    axis.grid(True, color="#e6eaee", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.title.set_color(TEXT)
    axis.title.set_fontsize(11)
    axis.title.set_fontweight("bold")
    axis.xaxis.label.set_color(TEXT_MUTED)
    axis.yaxis.label.set_color(TEXT_MUTED)
