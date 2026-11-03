import json

import httpx

from card_draft.input_data import Product, load_products
from card_draft.render import to_markdown
from card_draft.seo_data import add_seo_data


def result(**changes):
    return {
        "status": "ready", "name": "Прибор", "manufacturer": "Завод", "seo_title": "З", "seo_description": "О",
        "key_specs": [], "search_queries": ["регулятор овен", "редкий запрос"], "commercial_block": {"audience": "", "tasks": ""},
        "problems": [], "warnings": [], "attempts": 1,
    } | changes


WORDSTAT_ENV = {"YANDEX_SEARCH_API_KEY": "k", "YANDEX_FOLDER_ID": "f"}


def wordstat(request):
    phrase = json.loads(request.content)["phrase"]
    return httpx.Response(200, json={"totalCount": "1200" if phrase == "регулятор овен" else "0"})


def test_without_settings_frequency_is_marked_unchecked():
    data = add_seo_data(result(), Product(name="А"), {})
    assert data["query_stats"] == [
        {"query": "регулятор овен", "frequency": None},
        {"query": "редкий запрос", "frequency": None},
    ]
    assert data["metrika_phrases"] == []


def test_wordstat_frequency_is_added_and_zero_is_warned():
    data = add_seo_data(result(), Product(name="А"), WORDSTAT_ENV, transport=httpx.MockTransport(wordstat))
    assert data["query_stats"][0] == {"query": "регулятор овен", "frequency": 1200}
    assert any("редкий запрос" in note for note in data["warnings"])


def test_wordstat_sends_key_and_folder():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"totalCount": "5"})

    add_seo_data(result(search_queries=["а"]), Product(name="А"), WORDSTAT_ENV, transport=httpx.MockTransport(handler))
    assert seen["auth"] == "Api-Key k"
    assert json.loads(seen["body"])["folderId"] == "f"


def test_wordstat_failure_keeps_draft_and_warns():
    transport = httpx.MockTransport(lambda request: httpx.Response(403, json={}))
    data = add_seo_data(result(), Product(name="А"), WORDSTAT_ENV, transport=transport)
    assert data["status"] == "ready"
    assert data["query_stats"][0]["frequency"] is None
    assert any("Вордстат" in note for note in data["warnings"])


METRIKA_ENV = {"YANDEX_METRIKA_TOKEN": "t", "YANDEX_METRIKA_COUNTER": "123"}


def test_metrika_returns_phrases_of_page():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["filters"] = request.url.params["filters"]
        return httpx.Response(200, json={"data": [{"dimensions": [{"name": "трм138"}], "metrics": [7.0]}]})

    data = add_seo_data(result(search_queries=[]), Product(name="А", url="https://site/p/"), METRIKA_ENV, transport=httpx.MockTransport(handler))
    assert data["metrika_phrases"] == [{"phrase": "трм138", "visits": 7}]
    assert seen["auth"] == "OAuth t"
    assert "https://site/p/" in seen["filters"]


def test_metrika_needs_page_url():
    data = add_seo_data(result(search_queries=[]), Product(name="А"), METRIKA_ENV)
    assert any("url" in note for note in data["warnings"])


def test_metrika_failure_warns():
    transport = httpx.MockTransport(lambda request: httpx.Response(403, json={}))
    data = add_seo_data(result(search_queries=[]), Product(name="А", url="https://s/"), METRIKA_ENV, transport=transport)
    assert any("Метрик" in note for note in data["warnings"])


def test_no_draft_means_no_requests():
    data = add_seo_data(result(status="needs_data", search_queries=[]), Product(), WORDSTAT_ENV)
    assert data["query_stats"] == []


def test_url_field_is_read_from_input():
    assert load_products('{"name": "А", "url": "https://s/p/", "description": "т"}')[0].url == "https://s/p/"


def test_markdown_shows_frequency_and_phrases():
    data = result(query_stats=[{"query": "а", "frequency": 5}, {"query": "б", "frequency": None}], metrika_phrases=[{"phrase": "в", "visits": 2}], model="claude-cli/haiku")
    text = to_markdown(data)
    assert "а — 5 показов в месяц" in text
    assert "б — частотность не проверена" in text
    assert "в — 2 визита" in text or "в — визитов: 2" in text
    assert "claude-cli/haiku" in text
