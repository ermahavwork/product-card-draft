import json

import httpx
import pytest

from card_draft.llm import AnthropicClient, LLMClient, LLMConfig, LLMError, config_from_env


def client(handler, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return LLMClient(
        LLMConfig(api_key="sekret-key", base_url="https://llm.test/v1", model="m"),
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )


def reply(text="ответ", finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": finish}]})


MESSAGES = [{"role": "user", "content": "привет"}]


def test_returns_model_text_and_sends_key_in_header():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return reply()

    config = LLMConfig(api_key="abc", base_url="https://llm.test/v1", model="m")
    llm = LLMClient(config, transport=httpx.MockTransport(handler))
    assert llm.chat(MESSAGES) == "ответ"
    assert seen == {"auth": "Bearer abc", "url": "https://llm.test/v1/chat/completions"}


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_temporary_failures_are_retried(status):
    calls, sleeps = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={}) if len(calls) < 3 else reply()

    assert client(handler, sleeps).chat(MESSAGES) == "ответ"
    assert len(calls) == 3
    assert len(sleeps) == 2


def test_timeout_is_retried_then_explained():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMError, match="не ответила"):
        client(handler).chat(MESSAGES)
    assert len(calls) == 3


def test_retry_after_is_respected():
    sleeps, calls = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "7"}) if len(calls) == 1 else reply()

    client(handler, sleeps).chat(MESSAGES)
    assert sleeps == [7.0]


@pytest.mark.parametrize("status, fragment", [(401, "ключ"), (403, "ключ"), (404, "модел"), (400, "запрос")])
def test_permanent_failures_are_not_retried(status, fragment):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "детали"}})

    with pytest.raises(LLMError, match=fragment):
        client(handler).chat(MESSAGES)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>прокси</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
        httpx.Response(200, json={"choices": [{"message": {}}]}),
        httpx.Response(200, json=[1]),
    ],
)
def test_malformed_answers_are_explained(response):
    with pytest.raises(LLMError, match="ответ"):
        client(lambda request: response).chat(MESSAGES)


def test_cut_off_answer_is_explained():
    with pytest.raises(LLMError, match="обрезан"):
        client(lambda request: reply("{", "length")).chat(MESSAGES)


def test_config_requires_key_for_remote_api():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        config_from_env({"LLM_MODEL": "m"})


def test_config_requires_model():
    with pytest.raises(LLMError, match="LLM_MODEL"):
        config_from_env({"LLM_API_KEY": "k"})


def test_config_allows_local_model_without_key():
    config = config_from_env({"LLM_MODEL": "m", "LLM_BASE_URL": "http://127.0.0.1:1234/v1"})
    assert config.api_key == ""


def test_config_rejects_bad_url():
    with pytest.raises(LLMError, match="LLM_BASE_URL"):
        config_from_env({"LLM_MODEL": "m", "LLM_API_KEY": "k", "LLM_BASE_URL": "ftp://x"})


def test_negative_retry_after_does_not_crash():
    sleeps, calls = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "-1"}) if len(calls) == 1 else reply()

    assert client(handler, sleeps).chat(MESSAGES) == "ответ"
    assert sleeps[0] >= 0


def test_rejected_request_shows_reason_without_key():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "unsupported parameter sekret-key"}})

    with pytest.raises(LLMError) as error:
        client(handler).chat(MESSAGES)
    assert "unsupported parameter" in str(error.value)
    assert "sekret-key" not in str(error.value)


@pytest.mark.parametrize("url", ["http://[bad/v1", "http://host:abc/v1"])
def test_broken_url_is_explained(url):
    with pytest.raises(LLMError, match="LLM_BASE_URL"):
        config_from_env({"LLM_MODEL": "m", "LLM_API_KEY": "k", "LLM_BASE_URL": url})


def test_non_ascii_key_is_explained():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        config_from_env({"LLM_MODEL": "m", "LLM_API_KEY": "ключ"})


def test_private_network_model_needs_no_key():
    assert config_from_env({"LLM_MODEL": "m", "LLM_BASE_URL": "http://192.168.1.5:1234/v1"}).api_key == ""


def test_anthropic_protocol_uses_messages_api():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ответ"}], "stop_reason": "end_turn"})

    config = LLMConfig(api_key="abc", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5")
    llm = AnthropicClient(config, transport=httpx.MockTransport(handler))
    assert llm.chat([{"role": "system", "content": "правила"}, {"role": "user", "content": "товар"}]) == "ответ"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["key"] == "abc"
    assert seen["body"]["system"] == "правила"
    assert seen["body"]["messages"] == [{"role": "user", "content": "товар"}]


def test_anthropic_cut_off_answer_is_explained():
    config = LLMConfig(api_key="abc", base_url="https://api.anthropic.com/v1", model="m")
    response = httpx.Response(200, json={"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"})
    with pytest.raises(LLMError, match="обрезан"):
        AnthropicClient(config, transport=httpx.MockTransport(lambda request: response)).chat(MESSAGES)


def test_reason_is_masked_before_cutting():
    def handler(request):
        return httpx.Response(400, text="x" * 195 + "sekret-key")

    with pytest.raises(LLMError) as error:
        client(handler).chat(MESSAGES)
    assert "sekret" not in str(error.value)
