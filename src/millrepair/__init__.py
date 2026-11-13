"""Мониторинг и окно капитального ремонта барабанной шаровой мельницы.

Программа ничего не регулирует: она считает износ узлов и рекомендует режим
и момент одного капитального ремонта.
"""

from __future__ import annotations

__all__ = ["get_version"]


def get_version() -> str:
    """Версия берётся из git-тега через hatch-vcs, если пакет установлен."""
    try:
        from millrepair._version import __version__

        if __version__:
            return __version__
    except Exception:
        pass
    try:
        from importlib.metadata import version

        return version("millrepair")
    except Exception:
        return "0.0.0"
