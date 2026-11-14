"""Общие настройки тестов.

``QT_QPA_PLATFORM=offscreen`` выставляется до импорта Qt, как в локальном
прогоне, который повторяет проверку без дисплея.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_API", "pyside6")
