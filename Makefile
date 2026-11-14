# Тот же набор целей, что у justfile. Удобно, если just не установлен.
# На Windows из PowerShell вызывайте команды из README напрямую.

.PHONY: setup test test-all check run

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -U pip
	.venv/bin/python -m pip install -e ".[dev]"
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push scripts/ci_local.sh

test:
	.venv/bin/pytest -m "not slow" -q

test-all:
	bash scripts/ci_local.sh

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

run:
	.venv/bin/python -m millrepair
