import json

import pytest
from django.test import Client

from card_draft import views
from card_draft.llm import LLMError

GOOD = json.dumps({
    "seo_title": "Прибор",
    "seo_description": "Прибор для измерения. " * 45,
    "search_queries": ["прибор", "прибор купить", "прибор для измерения"],
    "commercial_block": {"audience": "Службы.", "tasks": "Измерение."},
}, ensure_ascii=False)
PRODUCT = json.dumps({"name": "Прибор", "manufacturer": "Завод", "description": "Прибор для измерения."}, ensure_ascii=False)


def post(body, **extra):
    return Client().post("/api/draft", data=body, content_type="application/json", **extra)


@pytest.fixture
def model(monkeypatch):
    seen = {}

    def build(provider=None, model=None):
        seen.update(provider=provider, model=model)
        return lambda messages: GOOD

    monkeypatch.setattr(views, "build_chat", build)
    return seen


def test_page_is_served_with_csrf_cookie():
    response = Client().get("/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies


def test_draft_returns_card_and_markdown(model):
    data = post(json.dumps({"product": PRODUCT})).json()
    assert data["status"] == "ready"
    assert "SEO-заголовок" in data["markdown"]


def test_selected_model_reaches_provider(model):
    post(json.dumps({"product": PRODUCT, "provider": "openai", "model": "gpt-5-nano"}))
    assert model == {"provider": "openai", "model": "gpt-5-nano"}


def test_bad_product_json_is_explained(model):
    response = post(json.dumps({"product": "{bad"}))
    assert response.status_code == 400
    assert "Некорректный JSON" in response.json()["detail"]


@pytest.mark.parametrize("body", ["{bad", "[]", '{"product": 5}', "{}"])
def test_bad_request_shape_is_explained(model, body):
    response = post(body)
    assert response.status_code == 400
    assert response.json()["detail"]


def test_one_product_only(model):
    response = post(json.dumps({"product": f"[{PRODUCT}, {PRODUCT}]"}))
    assert response.status_code == 400


def test_config_error_is_503(monkeypatch):
    def broken(provider=None, model=None):
        raise LLMError("Нет доступной модели")

    monkeypatch.setattr(views, "build_chat", broken)
    response = post(json.dumps({"product": PRODUCT}))
    assert response.status_code == 503
    assert "Нет доступной модели" in response.json()["detail"]


def test_models_endpoint_lists_scan(monkeypatch):
    monkeypatch.setattr(views, "available_models", lambda: [{"provider": "claude-cli", "kind": "подписка", "models": ["haiku"]}])
    data = Client().get("/api/models").json()
    assert data["providers"][0]["models"] == ["haiku"]


def test_post_requires_csrf_token():
    response = Client(enforce_csrf_checks=True).post("/api/draft", data="{}", content_type="application/json")
    assert response.status_code == 403


def test_examples_endpoint_gives_products_to_try():
    data = Client().get("/api/examples").json()
    names = [json.loads(item["product"])["name"] for item in data["examples"]]
    assert any("ТРМ138В" in name for name in names)
    assert any("БУСТ3" in name for name in names)


def test_demo_works_without_keys_end_to_end():
    example = next(item for item in Client().get("/api/examples").json()["examples"] if "БУСТ3" in item["title"])
    data = post(json.dumps({"product": example["product"], "provider": "demo"})).json()
    assert data["status"] == "ready"
    assert data["model"].startswith("demo/")


def test_models_endpoint_always_offers_demo(monkeypatch):
    monkeypatch.setattr(views, "available_models", lambda: [])
    data = Client().get("/api/models").json()
    assert data["providers"][-1]["provider"] == "demo"


def test_main_examples_go_first_with_clear_titles():
    titles = [item["title"] for item in Client().get("/api/examples").json()["examples"]]
    assert "ТРМ138В" in titles[0]
    assert "БУСТ3" in titles[1]
    assert any("команда" in title for title in titles)


def test_needs_data_works_without_any_model(monkeypatch):
    def broken(provider=None, model=None):
        raise LLMError("Нет доступной модели")

    monkeypatch.setattr(views, "build_chat", broken)
    data = post(json.dumps({"product": '{"name": "Х"}'})).json()
    assert data["status"] == "needs_data"


def test_demo_works_for_thin_example():
    example = next(item for item in Client().get("/api/examples").json()["examples"] if "Клещи" in item["title"])
    data = post(json.dumps({"product": example["product"], "provider": "demo"})).json()
    assert data["status"] == "needs_review"
    assert data["seo_title"]


@pytest.mark.parametrize("body", ['{"product": "{}", "model": 5}', '{"product": "{}", "provider": ["a"]}', "[" * 100000])
def test_wrong_types_and_deep_nesting_are_400(model, body):
    assert post(body).status_code == 400


def test_too_big_body_is_explained():
    response = post(json.dumps({"product": "я" * 300000}))
    assert response.status_code == 400
    assert response.json()["detail"]
