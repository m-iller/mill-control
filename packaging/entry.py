"""Точка входа PyInstaller. Окно без консоли на Windows, CLI остаётся доступен."""

from __future__ import annotations

import sys

from millrepair.cli import main

if __name__ == "__main__":
    sys.exit(main())
