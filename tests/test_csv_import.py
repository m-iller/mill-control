"""Импорт замеров из CSV."""

from __future__ import annotations

from millrepair.csv_import import read_measurement_csv


def test_russian_headers_and_semicolon(tmp_path) -> None:
    path = tmp_path / "замеры.csv"
    path.write_text(
        "дата;узел;величина;значение;комментарий\n"
        "2026-01-01T00:00:00+00:00;Футеровка;толщина плиты;90;первый\n",
        encoding="utf-8",
    )
    rows = read_measurement_csv(path)
    assert rows == [
        {
            "measured_at": "2026-01-01T00:00:00+00:00",
            "unit_name": "Футеровка",
            "quantity": "толщина плиты",
            "value": "90",
            "comment": "первый",
        }
    ]
