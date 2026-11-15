"""Мелкие функции без физической модели: время, числа, подсказки по именам."""

from __future__ import annotations

import difflib
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def parse_datetime(value: str | datetime) -> datetime:
    """Разобрать ISO-дату. Наивные метки считаются UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("пустая дата")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def format_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "не число"
    if math.isinf(number):
        return "∞" if number > 0 else "−∞"
    return f"{number:.{digits}g}"


def format_display(value: Any, digits: int = 4) -> str:
    """Число для таблиц и подписей: без записи вида 1.487e+04.

    Значащих цифр ``digits``. Тысячи разделены узким пробелом, дробная часть
    отделена запятой. Очень большие и очень малые числа остаются в степенной
    записи, но с множителем «·10ⁿ».
    """
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "не число"
    if math.isinf(number):
        return "∞" if number > 0 else "−∞"
    if number == 0:
        return "0"
    magnitude = abs(number)
    sign = "−" if number < 0 else ""
    if 1e-4 <= magnitude < 1e9:
        exponent = math.floor(math.log10(magnitude))
        decimals = max(digits - 1 - exponent, 0)
        rounded = (
            round(magnitude, decimals) if decimals else round(magnitude, digits - 1 - exponent)
        )
        text = f"{rounded:,.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return sign + text.replace(",", "\u202f").replace(".", ",")
    mantissa, power = f"{magnitude:.{digits - 1}e}".split("e")
    mantissa = mantissa.rstrip("0").rstrip(".").replace(".", ",")
    superscript = str(int(power)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"{sign}{mantissa}·10{superscript}"


def as_float(value: Any, label: str = "значение") -> float:
    if isinstance(value, np.ndarray):
        if value.shape != ():
            raise TypeError(f"{label}: ожидалось одно число, получен массив")
        value = value.item()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label}: ожидалось число, получено {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} не является конечным числом")
    return number


def unknown_names_message(owner: str, missing: set[str], known: set[str]) -> str:
    """Подсказка, каких имён не хватает и на что они похожи."""
    chunks: list[str] = []
    known_list = sorted(known)
    for name in sorted(missing):
        close = difflib.get_close_matches(name, known_list, n=2, cutoff=0.6)
        if close:
            chunks.append(f"«{name}» (похоже на: {', '.join(close)})")
        else:
            chunks.append(f"«{name}»")
    return f"{owner}: неизвестные имена: {', '.join(chunks)}"
