import json

import httpx
import pytest

from card_draft.llm import LLMError
from card_draft.providers import Chain, CliChat, DemoChat, _run, build_chat_from, scan, weakest_model


@pytest.mark.parametrize(
    "names, expected",
    [
        (["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-4-5"], "claude-haiku-5-5"),
        (["gpt-5", "gpt-5-mini", "gpt-5-nano", "text-embedding-3-small", "gpt-5-nano-tts"], "gpt-5-nano"),
        (["models/gemini-3-pro", "models/gemini-3-flash", "models/gemini-3-flash-lite", "models/gemini-embedding-001"], "gemini-3-flash-lite"),
        (["gpt-6-luna", "o9"], "gpt-6-luna"),
    ],
)
def test_weakest_model_is_chosen_from_list(names, expected):
    assert weakest_model(names) == expected


def test_no_text_models_gives_none():
    assert weakest_model(["text-embedding-3-small", "whisper-1"]) is None


def run_fake(outputs):
    def run(argv, **kwargs):
        return outputs.get(argv[0] + " " + argv[1], (1, ""))

    return run


def models_transport(by_host):
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": name} for name in by_host[request.url.host]]})

    return httpx.MockTransport(handler)


def names(candidates):
    return [(item.name, item.model) for item in candidates]


CODEX_MODELS = json.dumps({"models": [
    {"slug": "gpt-6-luna", "visibility": "list", "priority": 5},
    {"slug": "gpt-5.6-luna", "visibility": "list", "priority": 9},
    {"slug": "hidden", "visibility": "hide", "priority": 99},
]})


def test_scan_finds_subscriptions_first_with_weakest_model():
    found = scan(
        {"ANTHROPIC_API_KEY": "k"},
        which=lambda name: f"/bin/{name}" if name in ("claude", "codex") else None,
        run=run_fake({
            "claude auth": (0, json.dumps({"loggedIn": True, "subscriptionType": "max"})),
            "codex login": (0, "Logged in using ChatGPT"),
            "codex debug": (0, CODEX_MODELS),
        }),
        transport=models_transport({"api.anthropic.com": ["claude-opus-5-5", "claude-haiku-5-5"]}),
    )
    assert names(found) == [
        ("claude-cli", "haiku"),
        ("codex-cli", "gpt-5.6-luna"),
        ("anthropic", "claude-haiku-5-5"),
    ]


def test_scan_skips_cli_without_login():
    found = scan({}, which=lambda name: "/bin/claude" if name == "claude" else None,
                 run=run_fake({"claude auth": (0, json.dumps({"loggedIn": False}))}))
    assert found == []


def test_scan_finds_all_api_keys():
    found = scan(
        {"OPENAI_API_KEY": "a", "GEMINI_API_KEY": "b"},
        which=lambda name: None,
        transport=models_transport({
            "api.openai.com": ["gpt-5", "gpt-5-nano"],
            "generativelanguage.googleapis.com": ["models/gemini-3-flash-lite", "models/gemini-3-pro"],
        }),
    )
    assert names(found) == [("openai", "gpt-5-nano"), ("google", "gemini-3-flash-lite")]


def test_rejected_key_is_skipped():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={}))
    assert scan({"OPENAI_API_KEY": "bad"}, which=lambda name: None, transport=transport) == []


def test_chain_moves_to_next_on_failure():
    def broken(messages):
        raise LLMError("лимит подписки")

    chain = Chain([("claude-cli/haiku", broken), ("openai/gpt-5-nano", lambda messages: "ответ")])
    assert chain([]) == "ответ"
    assert chain.used == "openai/gpt-5-nano"


def test_chain_reports_all_failures():
    def broken(messages):
        raise LLMError("сбой")

    with pytest.raises(LLMError, match="claude-cli/haiku: сбой"):
        Chain([("claude-cli/haiku", broken)])([])


def test_build_chat_explains_nothing_found():
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        build_chat_from({}, which=lambda name: None)


def test_explicit_provider_is_respected():
    chain = build_chat_from(
        {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b"},
        which=lambda name: None,
        transport=models_transport({"api.openai.com": ["gpt-5-nano"], "api.anthropic.com": ["claude-haiku-5-5"]}),
    )
    assert [name for name, _ in chain.steps] == ["openai/gpt-5-nano"]


def test_model_can_be_set_by_hand():
    chain = build_chat_from(
        {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-5", "OPENAI_API_KEY": "a"},
        which=lambda name: None,
        transport=models_transport({"api.openai.com": ["gpt-5-nano"]}),
    )
    assert [name for name, _ in chain.steps] == ["openai/gpt-5"]


def test_compatible_api_is_used_first_when_configured():
    chain = build_chat_from({"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "LLM_MODEL": "m"}, which=lambda name: None)
    assert [name for name, _ in chain.steps] == ["compatible/m"]


MESSAGES = [{"role": "system", "content": "правила"}, {"role": "user", "content": "товар"}]


def test_cli_chat_sends_prompt_through_stdin_and_returns_text():
    seen = {}

    def run(argv, **kwargs):
        seen.update(argv=argv, input=kwargs["input"])
        return 0, "ответ"

    assert CliChat("claude-cli", "haiku", run=run)(MESSAGES) == "ответ"
    assert "haiku" in seen["argv"]
    assert "правила" in seen["argv"]
    assert "товар" in seen["input"]


def test_cli_chat_explains_failure():
    with pytest.raises(LLMError, match="claude-cli"):
        CliChat("claude-cli", "haiku", run=lambda argv, **kwargs: (1, ""))(MESSAGES)


def test_cli_chat_empty_answer_is_failure():
    with pytest.raises(LLMError):
        CliChat("claude-cli", "haiku", run=lambda argv, **kwargs: (0, "  "))(MESSAGES)


def test_real_run_helper_returns_stderr_when_stdout_empty(tmp_path):
    import sys

    from card_draft.providers import _run

    code, output = _run([sys.executable, "-c", "import sys; sys.stderr.write('Logged in')"])
    assert (code, output) == (0, "Logged in")


def test_demo_replays_recorded_answer_for_known_product(tmp_path):
    recorded = tmp_path / "a.json"
    recorded.write_text(json.dumps([{
        "name": "Прибор А", "seo_title": "Заголовок", "seo_description": "Описание",
        "search_queries": ["з"], "commercial_block": {"audience": "к", "tasks": "т"},
    }], ensure_ascii=False), encoding="utf-8")
    answer = DemoChat(tmp_path)([{"role": "user", "content": '{"name": "Прибор А"}'}])
    assert json.loads(answer)["seo_title"] == "Заголовок"


def test_demo_explains_unknown_product(tmp_path):
    with pytest.raises(LLMError, match="демо"):
        DemoChat(tmp_path)([{"role": "user", "content": '{"name": "Другой"}'}])


def test_demo_is_chosen_only_on_request():
    with pytest.raises(LLMError):
        build_chat_from({}, which=lambda name: None)
    chain = build_chat_from({"LLM_PROVIDER": "demo"}, which=lambda name: None)
    assert [name for name, _ in chain.steps] == ["demo/записанные ответы"]


def test_run_finds_command_through_path(monkeypatch):
    seen = {}

    def fake(argv, **kwargs):
        seen["argv"] = argv

        class Done:
            returncode, stdout, stderr = 0, "ok", ""

        return Done()

    monkeypatch.setattr("card_draft.providers.shutil.which", lambda name: f"C:/bin/{name}.cmd")
    monkeypatch.setattr("card_draft.providers.subprocess.run", fake)
    _run(["claude", "-p"])
    assert seen["argv"][0] == "C:/bin/claude.cmd"
