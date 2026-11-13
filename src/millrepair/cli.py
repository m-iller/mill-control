"""Командная строка. Окно Qt открывается, только если нет --calc и --optimize."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from millrepair import get_version
from millrepair.engine import calculate, format_calc
from millrepair.io_json import load_default_model


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


def run_calc(db_path: Path | None = None) -> int:
    """Посчитать модель.

    Пока нет базы, считается модель по умолчанию. Аргумент ``db_path``
    зарезервирован и начнёт использоваться вместе с SQLite.
    """
    del db_path
    try:
        model = load_default_model()
        result = calculate(model)
    except Exception as exc:
        print(f"Ошибка расчёта: {exc}", file=sys.stderr)
        return 1
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
