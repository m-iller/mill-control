"""Чтение CSV с замерами. Заголовки можно писать по-русски или по-английски."""

from __future__ import annotations

import csv
from pathlib import Path

_HEADERS = {
    "date": "measured_at",
    "дата": "measured_at",
    "unit": "unit_name",
    "узел": "unit_name",
    "quantity": "quantity",
    "величина": "quantity",
    "value": "value",
    "значение": "value",
    "comment": "comment",
    "комментарий": "comment",
}


def read_measurement_csv(path: Path | str) -> list[dict[str, str]]:
    """Вернуть строки с ключами measured_at, unit_name, quantity, value, comment."""
    file_path = Path(path)
    with file_path.open(newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if reader.fieldnames is None:
            raise ValueError("в CSV нет заголовка")
        mapping = {}
        for field in reader.fieldnames:
            key = _HEADERS.get(field.strip().lower())
            if key is not None:
                mapping[field] = key
        missing = {"measured_at", "unit_name", "quantity", "value"} - set(mapping.values())
        if missing:
            raise ValueError("не хватает столбцов: " + ", ".join(sorted(missing)))
        rows = []
        for index, raw in enumerate(reader, start=2):
            item = {
                name: "" for name in ("measured_at", "unit_name", "quantity", "value", "comment")
            }
            for field, key in mapping.items():
                item[key] = (raw.get(field) or "").strip()
            if not any(item.values()):
                continue
            if (
                not item["measured_at"]
                or not item["unit_name"]
                or not item["quantity"]
                or not item["value"]
            ):
                raise ValueError(f"строка {index}: заполните дату, узел, величину и значение")
            rows.append(item)
    return rows
