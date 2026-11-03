"""Сборка черновика: вызов модели, проверка ответа, повтор с указанием ошибок."""

import json
import re
from collections.abc import Callable

from .checks import DESCRIPTION_MIN, UNIT_WORD_RE, check_card, has_thin_data, key_specs
from .input_data import Product
from .llm import LLMError
from .prompts import SYSTEM_PROMPT, build_fix_prompt, build_user_prompt

MAX_ATTEMPTS = 3
BAD_JSON = "Ответ не является JSON-объектом."
FIELDS_WITHOUT_UNIT = re.compile(r"^(класс|степень|код|артикул|серия)|количество|\bшт\b")
INVENTED = "Нет во входных данных"


def make_draft(product: Product, chat: Callable[[list[dict]], str]) -> dict:
    result = _empty_result(product)
    if blockers := product.blockers():
        return result | {"status": "needs_data", "problems": blockers}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(product)},
    ]
    best, best_problems, api_failure = None, [], ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        try:
            answer = chat(messages)
        except LLMError as error:
            api_failure = str(error)
            break
        card = parse_model_json(answer)
        problems = check_card(card, product) if card is not None else [BAD_JSON]
        if card is not None and (best is None or _weight(problems) < _weight(best_problems)):
            best, best_problems = card, problems
        if not problems:
            break
        messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": build_fix_prompt(problems)}]

    if best is None:
        return result | {"status": "error", "problems": [api_failure or BAD_JSON]}
    fields = _card_fields(best)
    problems = best_problems + ([api_failure] if api_failure else [])
    if has_thin_data(product) and len(fields["seo_description"]) < DESCRIPTION_MIN:
        problems.append(
            f"Фактов мало: описание короче {DESCRIPTION_MIN} символов, добирать объём выдумкой нельзя. Добавьте данные из паспорта."
        )
    return result | fields | {"status": "needs_review" if problems else "ready", "problems": problems}


def _weight(problems: list[str]) -> tuple[int, int]:
    """Выдуманное значение хуже нарушения длины."""
    return sum(problem.startswith(INVENTED) for problem in problems), len(problems)


def parse_model_json(answer: str) -> dict | None:
    start, end = answer.find("{"), answer.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(answer[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _empty_result(product: Product) -> dict:
    return {
        "status": "",
        "name": product.name,
        "manufacturer": product.manufacturer or "данных нет",
        "seo_title": "",
        "seo_description": "",
        "key_specs": key_specs(product),
        "search_queries": [],
        "commercial_block": {"audience": "", "tasks": ""},
        "problems": [],
        "warnings": product.notes + _specs_without_unit(product),
        "attempts": 0,
    }


def _card_fields(card: dict) -> dict:
    block = card.get("commercial_block")
    block = block if isinstance(block, dict) else {}
    queries = card.get("search_queries")
    return {
        "seo_title": _text(card.get("seo_title")),
        "seo_description": _text(card.get("seo_description")),
        "search_queries": [q for q in queries if isinstance(q, str)] if isinstance(queries, list) else [],
        "commercial_block": {"audience": _text(block.get("audience")), "tasks": _text(block.get("tasks"))},
    }


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _specs_without_unit(product: Product) -> list[str]:
    return [
        f"Характеристика «{key}»: значение {value} без единицы измерения, уточните по паспорту."
        for key, value in product.specs.items()
        if re.fullmatch(r"[\d.,]+", value) and not UNIT_WORD_RE.search(key) and not FIELDS_WITHOUT_UNIT.search(key.lower())
    ]
