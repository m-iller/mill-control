#!/usr/bin/env bash
# Полный локальный прогон, повторяющий то, что иначе делал бы GitHub Actions:
# установка не требуется (ожидается уже созданный .venv), затем ruff и pytest
# с покрытием. Qt запускается без дисплея.
#
# GitHub Actions для тестов не используется: минуты ограничены, а на приватных
# репозиториях минуты Windows-раннеров списываются с коэффициентом 2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x .venv/bin/pytest ]]; then
  BIN=".venv/bin"
elif [[ -x .venv/Scripts/pytest.exe ]]; then
  BIN=".venv/Scripts"
else
  echo "Виртуальное окружение не найдено." >&2
  echo "Создайте его: just setup    или    make setup" >&2
  echo "Вручную: python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\"" >&2
  exit 1
fi

"$BIN/ruff" check .
"$BIN/ruff" format --check .
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export QT_API="${QT_API:-pyside6}"
"$BIN/pytest" --cov --cov-report=term-missing --cov-report=html -q
