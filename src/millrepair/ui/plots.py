"""Графики остаточного ресурса и вероятности безотказной работы."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from millrepair.engine import CalcResult, unit_reliability, unit_residual_fraction
from millrepair.ui import theme
from millrepair.util import format_number


class PlotPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("plotPanel")
        self.figure = Figure(figsize=(10, 4.2), layout="constrained", facecolor=theme.SURFACE)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax_residual = self.figure.add_subplot(1, 2, 1)
        self.ax_reliability = self.figure.add_subplot(1, 2, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.clear()

    def clear(self) -> None:
        for axis in (self.ax_residual, self.ax_reliability):
            axis.clear()
        self.ax_residual.set_title("Остаточный ресурс")
        self.ax_residual.set_xlabel("Время, ч")
        self.ax_residual.set_ylabel("Доля остатка")
        self.ax_reliability.set_title("Вероятность безотказной работы")
        self.ax_reliability.set_xlabel("Время, ч")
        self.ax_reliability.set_ylabel("P(t)")
        for axis in (self.ax_residual, self.ax_reliability):
            theme.style_axes(axis)
        self.canvas.draw_idle()

    def draw(
        self,
        calc: CalcResult,
        *,
        horizon: float | None = None,
        multiplicities: dict[str, int] | None = None,
        eps: float = 0.05,
    ) -> None:
        self.clear()
        horizon_values = [mode.t_fail or 0 for unit in calc.units for mode in unit.modes]
        if horizon is not None:
            horizon_values.append(horizon)
        upper = max(horizon_values) if horizon_values else 0
        upper = upper * 1.15 if upper > 0 else 1000.0
        grid = np.linspace(0.0, upper, 240)
        for index, unit in enumerate(calc.units):
            color = theme.SERIES[index % len(theme.SERIES)]
            residual = unit_residual_fraction(unit, grid)
            if residual is not None:
                self.ax_residual.plot(grid, residual, label=unit.name, color=color, linewidth=2)
            reliability = unit_reliability(unit, grid)
            if reliability is not None:
                self.ax_reliability.plot(
                    grid, reliability, label=unit.name, color=color, linewidth=2
                )
                if unit.t is not None and 0 < unit.t <= upper:
                    # Точка, где кривая узла доходит до порога eps: это t узла.
                    self.ax_reliability.plot(
                        [unit.t], [eps], marker="o", markersize=5, color=color, linestyle="none"
                    )
        self.ax_residual.set_xlim(0, upper)
        self.ax_reliability.set_xlim(0, upper)
        self.ax_residual.set_ylim(-0.05, 1.05)
        self.ax_reliability.set_ylim(-0.05, 1.05)
        self.ax_reliability.axhline(
            eps,
            color=theme.TEXT_MUTED,
            linestyle="--",
            linewidth=1,
            label=f"ε = {format_number(eps)}",
        )
        if horizon is not None and horizon > 0:
            self.ax_residual.axvline(horizon, color=theme.TEXT, linewidth=1.4, label="T")
            self.ax_reliability.axvline(horizon, color=theme.TEXT, linewidth=1.4, label="T")
            seen: set[float] = set()
            for _name, k in (multiplicities or {}).items():
                if k <= 0:
                    continue
                mark = horizon / k
                if any(abs(mark - item) < 1e-6 for item in seen):
                    continue
                seen.add(mark)
                self.ax_residual.axvline(mark, color=theme.TEXT_MUTED, linestyle=":", linewidth=1)
        for axis in (self.ax_residual, self.ax_reliability):
            if axis.lines:
                axis.legend(fontsize=8, frameon=False, labelcolor=theme.TEXT)
        self.canvas.draw_idle()
