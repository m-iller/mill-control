"""Формула в математическом виде: дроби, степени, индексы, греческие буквы.

Текст формулы переводит ``millrepair.latex``, картинку рисует mathtext из
matplotlib: он уже есть в зависимостях, LaTeX в системе не нужен.
"""

from __future__ import annotations

from functools import lru_cache

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy

from millrepair.expr import ExpressionError
from millrepair.latex import FormulaLayout, expression_layout
from millrepair.ui import theme

_MATH_FONT = "stix"
_BASE_DPI = 100.0


def _math(text: str) -> str:
    return f"${text}$"


def _brace(x: float, bottom: float, top: float, width: float) -> MplPath:
    """Левая фигурная скобка высотой от ``bottom`` до ``top``."""
    middle = 0.5 * (bottom + top)
    right, left = x + width, x
    centre = x + 0.5 * width
    quarter = 0.25 * (top - bottom)
    vertices = [
        (right, top),
        (centre, top),
        (centre, top - 0.5 * quarter),
        (centre, middle + quarter),
        (centre, middle + 0.3 * quarter),
        (left, middle),
        (left, middle),
        (centre, middle - 0.3 * quarter),
        (centre, middle - quarter),
        (centre, bottom + 0.5 * quarter),
        (centre, bottom),
        (right, bottom),
        (right, bottom),
    ]
    codes = [MplPath.MOVETO] + [MplPath.CURVE4] * 12
    return MplPath(vertices, codes)


@lru_cache(maxsize=512)
def _render_cached(
    lhs: str,
    rows: tuple[tuple[str, str], ...],
    size: float,
    color: str,
    scale: float,
) -> tuple[bytes, int, int]:
    """Нарисовать формулу. Возвращает RGBA-буфер и размер в пикселях."""
    dpi = _BASE_DPI * scale
    figure = Figure(dpi=dpi)
    canvas = FigureCanvasAgg(figure)
    renderer = canvas.get_renderer()
    prop = FontProperties(size=size, math_fontfamily=_MATH_FONT)

    def measure(text: str) -> tuple[float, float, float]:
        if not text:
            return 0.0, 0.0, 0.0
        width, height, descent = renderer.get_text_width_height_descent(
            _math(text), prop, ismath=True
        )
        return float(width), float(height), float(descent)

    pad = 0.35 * size * dpi / 72.0
    gap = 0.9 * size * dpi / 72.0
    row_gap = 0.55 * size * dpi / 72.0
    lhs_text = f"{lhs} =" if lhs else ""
    lhs_w, lhs_h, lhs_d = measure(lhs_text)
    bodies = [measure(body) for body, _condition in rows]
    conditions = [measure(condition) for _body, condition in rows]
    piecewise = len(rows) > 1
    heights = []
    for body, condition in zip(bodies, conditions, strict=True):
        ascent = max(body[1] - body[2], condition[1] - condition[2])
        descent = max(body[2], condition[2])
        heights.append((ascent, descent))
    block_h = sum(a + d for a, d in heights) + row_gap * (len(rows) - 1)
    if not piecewise:
        ascent = max(heights[0][0], lhs_h - lhs_d)
        descent = max(heights[0][1], lhs_d)
        block_h = ascent + descent
    brace_w = 0.55 * size * dpi / 72.0 if piecewise else 0.0
    body_w = max(item[0] for item in bodies)
    condition_w = max(item[0] for item in conditions)
    x_lhs = pad
    x_brace = x_lhs + lhs_w + (0.45 * gap if lhs_text else 0.0)
    x_body = x_brace + brace_w + (0.3 * gap if piecewise else 0.0)
    x_condition = x_body + body_w + gap
    total_w = (x_condition + condition_w if condition_w else x_body + body_w) + pad
    total_h = block_h + 2 * pad
    width_px = max(int(total_w + 0.999), 2)
    height_px = max(int(total_h + 0.999), 2)
    figure.set_size_inches(width_px / dpi, height_px / dpi)
    figure.patch.set_alpha(0.0)

    def put(x: float, baseline: float, text: str) -> None:
        if text:
            figure.text(
                x / width_px,
                baseline / height_px,
                _math(text),
                fontproperties=prop,
                color=color,
                va="baseline",
                ha="left",
            )

    if piecewise:
        top = height_px - pad
        cursor = top
        for (body, condition), (ascent, descent) in zip(rows, heights, strict=True):
            baseline = cursor - ascent
            put(x_body, baseline, body)
            put(x_condition, baseline, condition)
            cursor = baseline - descent - row_gap
        middle = 0.5 * height_px
        put(x_lhs, middle - 0.5 * (lhs_h - 2 * lhs_d) * 0.7, lhs_text)
        path = _brace(x_brace, pad * 0.6, height_px - pad * 0.6, brace_w)
        scaled = MplPath([(vx / width_px, vy / height_px) for vx, vy in path.vertices], path.codes)
        figure.add_artist(
            PathPatch(
                scaled,
                transform=figure.transFigure,
                fill=False,
                edgecolor=color,
                linewidth=max(0.9, size / 13.0),
                capstyle="round",
            )
        )
    else:
        baseline = pad + max(heights[0][1], lhs_d)
        put(x_lhs, baseline, lhs_text)
        put(x_body, baseline, rows[0][0])
    canvas.draw()
    buffer = bytes(canvas.buffer_rgba())
    actual_w, actual_h = canvas.get_width_height()
    return buffer, int(actual_w), int(actual_h)


def render_layout(
    layout: FormulaLayout,
    *,
    size: float = 14.0,
    color: str = theme.TEXT,
    scale: float = 1.0,
) -> QPixmap:
    """Картинка формулы. ``scale`` — коэффициент плотности экрана."""
    buffer, width, height = _render_cached(
        layout.lhs, tuple(layout.rows), float(size), color, float(scale)
    )
    image = QImage(buffer, width, height, 4 * width, QImage.Format.Format_RGBA8888).copy()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def render_expression(
    expression: str,
    lhs: str = "",
    *,
    size: float = 14.0,
    color: str = theme.TEXT,
    scale: float = 1.0,
) -> QPixmap | None:
    """Картинка формулы или ``None``, если её не удалось разобрать и нарисовать."""
    try:
        layout = expression_layout(expression, lhs)
        return render_layout(layout, size=size, color=color, scale=scale)
    except (ExpressionError, ValueError, RuntimeError):
        return None


class FormulaLabel(QLabel):
    """Подпись, которая показывает формулу картинкой."""

    def __init__(self, parent=None, *, size: float = 14.0) -> None:
        super().__init__(parent)
        self._size = size
        self.rendered = False
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def set_formula(self, expression: str, lhs: str = "", *, placeholder: str = "") -> bool:
        """Показать формулу. Возвращает ``False``, если показать не удалось."""
        if not expression.strip():
            self.rendered = False
            self.setPixmap(QPixmap())
            self.setText(placeholder)
            return False
        pixmap = render_expression(
            expression, lhs, size=self._size, scale=float(self.devicePixelRatioF())
        )
        if pixmap is None:
            self.rendered = False
            self.setPixmap(QPixmap())
            self.setText(placeholder)
            return False
        self.rendered = True
        self.setText("")
        self.setPixmap(pixmap)
        return True


class FormulaPreview(QScrollArea):
    """Рамка с формулой. Длинная формула прокручивается по горизонтали."""

    def __init__(self, parent=None, *, size: float = 15.0, minimum_height: int = 84) -> None:
        super().__init__(parent)
        self.setObjectName("formulaPreview")
        self.label = FormulaLabel(size=size)
        self.label.setObjectName("formulaPreviewLabel")
        self.label.setMargin(10)
        self.setWidget(self.label)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumHeight(minimum_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._minimum_height = minimum_height

    def set_formula(self, expression: str, lhs: str = "", *, placeholder: str = "") -> bool:
        shown = self.label.set_formula(expression, lhs, placeholder=placeholder)
        pixmap = self.label.pixmap()
        wanted = self._minimum_height
        if shown and not pixmap.isNull():
            wanted = max(wanted, int(pixmap.height() / pixmap.devicePixelRatio()) + 40)
        self.setFixedHeight(min(wanted, 220))
        return shown
