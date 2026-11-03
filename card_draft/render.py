"""Текстовое представление черновика для контент-менеджера."""

STATUS_TITLES = {
    "ready": "Черновик готов, проверки пройдены",
    "needs_review": "Черновик требует проверки человеком",
    "needs_data": "Недостаточно данных: черновик не создан",
    "error": "Ошибка: черновик не создан",
}


def to_markdown(result: dict) -> str:
    lines = [f"# {result['name'] or 'Товар без названия'}", "", f"**Производитель:** {result['manufacturer']}", "", f"**Статус:** {STATUS_TITLES[result['status']]}", ""]
    lines += _list_section("Что исправить", result["problems"])
    lines += _list_section("Что уточнить", result["warnings"])
    if result["seo_title"]:
        lines += ["## SEO-заголовок", "", result["seo_title"], ""]
    if result["seo_description"]:
        lines += ["## SEO-описание", "", result["seo_description"], ""]
    lines += ["## Ключевые характеристики", ""]
    lines += [f"- {spec['name']}: {spec['value']}" for spec in result["key_specs"]]
    lines.append("")
    lines += _list_section("Поисковые запросы", result["search_queries"])
    block = result["commercial_block"]
    if block["audience"] or block["tasks"]:
        lines += ["## Для менеджера", "", f"**Кому подходит:** {block['audience']}", "", f"**Какие задачи решает:** {block['tasks']}", ""]
    return "\n".join(lines).rstrip() + "\n"


def _list_section(title: str, items: list[str]) -> list[str]:
    return [f"## {title}", "", *[f"- {item}" for item in items], ""] if items else []
