"""Разбор и очистка входных данных о приборе."""

import html
import json
import math
import re
from dataclasses import dataclass, field

MAX_INPUT_CHARS = 50_000
EMPTY_MARKS = {"", "-", "—", "–", "н/д", "n/a", "na", "нет данных", "данных нет", "null", "none"}
KNOWN_FIELDS = {"name", "manufacturer", "specs", "description"}


class InputError(ValueError):
    """Вход нельзя разобрать: сообщение показывается пользователю как есть."""


@dataclass
class Product:
    name: str = ""
    manufacturer: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    description: str = ""
    empty_specs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def blockers(self) -> list[str]:
        """Причины, по которым черновик писать не из чего: модель в этом случае не вызывается."""
        problems = []
        if not self.name:
            problems.append("Не заполнено поле name (название товара).")
        if not self.specs and not self.description:
            problems.append("Нет ни specs, ни description: черновик писать не из чего.")
        return problems


def load_products(text: str) -> list[Product]:
    text = text.lstrip("﻿")
    if not text.strip():
        raise InputError("Вход пуст: нужен JSON с данными о товаре.")
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(f"Вход слишком большой: больше {MAX_INPUT_CHARS} знаков.")
    try:
        data = json.loads(text, parse_constant=_refuse_constant, object_pairs_hook=_refuse_duplicates)
    except json.JSONDecodeError as error:
        raise InputError(f"Некорректный JSON: строка {error.lineno}, позиция {error.colno}: {error.msg}.") from error
    except InputError:
        raise
    except (RecursionError, ValueError) as error:
        raise InputError("Некорректный JSON: слишком большая вложенность или число.") from error
    items = data if isinstance(data, list) else [data]
    if not items:
        raise InputError("Вход пуст: список товаров не содержит ни одного элемента.")
    return [_to_product(item) for item in items]


def _refuse_constant(name: str):
    raise InputError(f"Некорректный JSON: значение {name} не допускается.")


def _refuse_duplicates(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Поле «{key}» указано дважды: неясно, какое значение верное.")
        result[key] = value
    return result


def _to_product(item) -> Product:
    if not isinstance(item, dict):
        raise InputError("Каждый товар должен быть JSON-объектом с полями name, manufacturer, specs, description.")
    product = Product(
        name=_text_field(item, "name"),
        manufacturer=_text_field(item, "manufacturer"),
        description=_text_field(item, "description"),
    )
    _fill_specs(product, item.get("specs"))
    for key in sorted(item.keys() - KNOWN_FIELDS):
        product.notes.append(f"Поле «{key}» не используется: проверьте, нет ли опечатки в названии.")
    if not product.manufacturer:
        product.notes.append("Не заполнено поле manufacturer: в карточке производитель не указан.")
    return product


def _text_field(item: dict, key: str) -> str:
    value = item.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InputError(f"Поле {key} должно быть строкой.")
    cleaned = _clean(value)
    return "" if cleaned.lower() in EMPTY_MARKS else cleaned


def _fill_specs(product: Product, specs) -> None:
    if specs is None:
        return
    if not isinstance(specs, dict):
        raise InputError("Поле specs должно быть объектом вида {\"характеристика\": \"значение\"}.")
    for raw_key, raw_value in specs.items():
        key = _clean(raw_key)
        value = _spec_value(key, raw_value)
        if value.lower() in EMPTY_MARKS:
            product.empty_specs.append(key)
        else:
            product.specs[key] = value


def _spec_value(key: str, value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float) and not math.isfinite(value):
        raise InputError(f"Значение характеристики «{key}» не является конечным числом.")
    if isinstance(value, (str, int, float)):
        return _clean(str(value))
    if isinstance(value, list) and all(isinstance(part, (str, int, float)) for part in value):
        return ", ".join(_clean(str(part)) for part in value)
    raise InputError(f"Значение характеристики «{key}» должно быть строкой, числом или списком.")


def _clean(text: str) -> str:
    decoded = html.unescape(html.unescape(text))
    try:
        decoded.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InputError("Текст содержит символы, которые нельзя записать в UTF-8.") from error
    without_tags = re.sub(r"</?[a-zA-Z][^>]*>", " ", decoded)
    return re.sub(r"\s+", " ", without_tags).strip()
