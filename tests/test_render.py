from card_draft.render import to_markdown


def result(**changes):
    return {
        "status": "ready",
        "name": "Прибор",
        "manufacturer": "Завод",
        "seo_title": "Заголовок",
        "seo_description": "Описание",
        "key_specs": [{"name": "Класс", "value": "1"}, {"name": "Питание", "value": "данных нет"}],
        "search_queries": ["запрос"],
        "commercial_block": {"audience": "Кому", "tasks": "Задачи"},
        "problems": [],
        "warnings": [],
        "attempts": 1,
    } | changes


def test_ready_card_has_all_sections():
    text = to_markdown(result())
    for part in ("Заголовок", "Описание", "- Класс: 1", "- Питание: данных нет", "- запрос", "Кому", "Задачи", "готов"):
        assert part in text


def test_problems_are_shown_on_top():
    text = to_markdown(result(status="needs_review", problems=["Нет во входных данных: 0,5"]))
    assert text.index("0,5") < text.index("Заголовок")
    assert "проверк" in text.lower()


def test_needs_data_shows_what_to_fill_without_empty_sections():
    text = to_markdown(result(status="needs_data", seo_title="", seo_description="", problems=["Не заполнено поле name"]))
    assert "Не заполнено поле name" in text
    assert "SEO-заголовок" not in text


def test_warnings_are_listed():
    assert "уточните" in to_markdown(result(warnings=["Значение 24, уточните"]))


def test_manufacturer_is_shown():
    assert "Завод" in to_markdown(result())
