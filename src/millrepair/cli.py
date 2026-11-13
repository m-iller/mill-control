"""Командная строка. Окно Qt открывается, только если нет --calc и --optimize."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from millrepair import get_version
from millrepair.db import Database, default_db_path
from millrepair.engine import calculate, format_calc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="millrepair",
        description="Мониторинг и окно капитального ремонта барабанной шаровой мельницы",
    )
    parser.add_argument("--db", type=Path, default=None, help="файл SQLite вместо каталога данных")
    parser.add_argument("--calc", action="store_true", help="посчитать текущий режим и выйти")
    parser.add_argument("--optimize", action="store_true", help="подобрать режим и момент ремонта")
    parser.add_argument("--version", action="store_true", help="показать версию")
    parser.add_argument(
        "--maxiter", type=int, default=None, help="поколения differential_evolution"
    )
    parser.add_argument("--popsize", type=int, default=None, help="множитель размера популяции")
    parser.add_argument("--seed", type=int, default=None, help="зерно генератора для оптимизатора")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"millrepair {get_version()}")
        return 0
    if args.optimize:
        print(
            "Оптимизация ещё не подключена в этой сборке шага. Запустите --calc.",
            file=sys.stderr,
        )
        return 2
    if args.calc:
        return run_calc(args.db)
    from millrepair.ui.main_window import run_app

    return run_app(args.db)


def open_database(db_path: Path | None) -> Database:
    database = Database(db_path or default_db_path())
    database.migrate()
    database.ensure_default()
    return database


def run_calc(db_path: Path | None = None) -> int:
    """Посчитать активную модель. Пустая база получает модель по умолчанию."""
    try:
        database = open_database(db_path)
    except Exception as exc:
        print(f"Ошибка базы: {exc}", file=sys.stderr)
        return 1
    try:
        model = database.load_active_model()
        result = calculate(
            model,
            measurements=database.list_measurements(model.id),
            periods=database.list_periods(model.id),
        )
    except Exception as exc:
        print(f"Ошибка расчёта: {exc}", file=sys.stderr)
        return 1
    finally:
        database.close()
    print(format_calc(model, result))
    return 0


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            continue
