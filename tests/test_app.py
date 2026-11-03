import json

import pytest
from fastapi.testclient import TestClient

from card_draft import cli, web
from card_draft.llm import LLMError

GOOD = json.dumps({
    "seo_title": "Прибор",
    "seo_description": "Прибор для измерения. " * 45,
    "search_queries": ["прибор", "прибор купить", "прибор для измерения"],
    "commercial_block": {"audience": "Службы.", "tasks": "Измерение."},
}, ensure_ascii=False)
PRODUCT = '{"name": "Прибор", "manufacturer": "Завод", "description": "Прибор для измерения."}'


@pytest.fixture
def model(monkeypatch):
    def install(answer=GOOD):
        def chat(messages):
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(cli, "build_chat", lambda: chat)
        monkeypatch.setattr(web, "build_chat", lambda: chat)

    return install


def test_cli_prints_json_for_file(model, tmp_path, capsys):
    model()
    path = tmp_path / "p.json"
    path.write_text(PRODUCT, encoding="utf-8")
    assert cli.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "ready"


def test_cli_prints_markdown_on_request(model, tmp_path, capsys):
    model()
    path = tmp_path / "p.json"
    path.write_text(PRODUCT, encoding="utf-8")
    assert cli.main([str(path), "--format", "md"]) == 0
    assert "SEO-заголовок" in capsys.readouterr().out


def test_cli_explains_bad_json_with_exit_2(model, tmp_path, capsys):
    model()
    path = tmp_path / "p.json"
    path.write_text("{bad", encoding="utf-8")
    assert cli.main([str(path)]) == 2
    assert "Некорректный JSON" in capsys.readouterr().err


def test_cli_missing_file_exit_2(capsys):
    assert cli.main(["нет-такого.json"]) == 2
    assert "нет-такого.json" in capsys.readouterr().err


def test_cli_non_utf8_file_exit_2(tmp_path, capsys):
    path = tmp_path / "p.json"
    path.write_bytes('{"name": "Прибор"}'.encode("cp1251"))
    assert cli.main([str(path)]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_cli_config_error_exit_3(monkeypatch, tmp_path, capsys):
    def broken():
        raise LLMError("Не задан LLM_API_KEY")

    monkeypatch.setattr(cli, "build_chat", broken)
    path = tmp_path / "p.json"
    path.write_text(PRODUCT, encoding="utf-8")
    assert cli.main([str(path)]) == 3
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_cli_needs_data_exit_1(model, tmp_path, capsys):
    model()
    path = tmp_path / "p.json"
    path.write_text('{"name": "Прибор"}', encoding="utf-8")
    assert cli.main([str(path)]) == 1
    assert json.loads(capsys.readouterr().out)[0]["status"] == "needs_data"


def test_cli_api_failure_exit_3(model, tmp_path, capsys):
    model(LLMError("API временно недоступен"))
    path = tmp_path / "p.json"
    path.write_text(PRODUCT, encoding="utf-8")
    assert cli.main([str(path)]) == 3
    assert json.loads(capsys.readouterr().out)[0]["status"] == "error"


def test_web_form_is_served():
    response = TestClient(web.app).get("/")
    assert response.status_code == 200
    assert "<form" in response.text


def test_web_returns_draft_and_markdown(model):
    model()
    data = TestClient(web.app).post("/api/draft", content=PRODUCT).json()
    assert data["status"] == "ready"
    assert "SEO-заголовок" in data["markdown"]


def test_web_explains_bad_json(model):
    model()
    response = TestClient(web.app).post("/api/draft", content="{bad")
    assert response.status_code == 400
    assert "Некорректный JSON" in response.json()["detail"]


def test_web_takes_one_product_only(model):
    model()
    response = TestClient(web.app).post("/api/draft", content=f"[{PRODUCT}, {PRODUCT}]")
    assert response.status_code == 400


def test_web_config_error_is_503(monkeypatch):
    def broken():
        raise LLMError("Не задан LLM_API_KEY")

    monkeypatch.setattr(web, "build_chat", broken)
    response = TestClient(web.app).post("/api/draft", content=PRODUCT)
    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]
