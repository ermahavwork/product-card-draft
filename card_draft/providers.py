"""Поиск доступных моделей: подписки, затем ключи API. Берётся самая слабая модель."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .llm import AnthropicClient, LLMClient, LLMConfig, LLMError, config_from_env

CLI_TIMEOUT_SECONDS = 180
OPENAI_URL = "https://api.openai.com/v1"
ANTHROPIC_URL = "https://api.anthropic.com/v1"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
HELP = (
    "Нет доступной модели. Войдите в Claude Code, Codex или Gemini CLI, либо задайте в .env "
    "OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, либо LLM_BASE_URL и LLM_MODEL. "
    "Для проверки без ключей: LLM_PROVIDER=demo."
)
# От слабых моделей к сильным. Порядок задан вручную: API не сообщает уровень модели.
TIERS = ("lite", "nano", "haiku", "mini", "luna", "flash", "sonnet", "terra", "pro", "opus")
NOT_TEXT = re.compile(
    r"embed|whisper|tts|audio|image|vision|moderation|realtime|transcribe|search|robotics|live|dall|sora|veo|guard|aqa|research|computer|thinking"
)
RECORDED_DIR = Path(__file__).resolve().parent.parent / "examples" / "output"
API_KEY_NAMES = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
DEMO = "demo"
DEMO_LABEL = "записанные ответы"
DATED = re.compile(r"\d{4}-\d{2}-\d{2}|\d{8}")


def _run(argv: list[str], input: str | None = None, cwd: str | None = None) -> tuple[int, str]:
    # На Windows команды npm лежат как .cmd: без полного пути subprocess их не находит.
    argv = [shutil.which(argv[0]) or argv[0], *argv[1:]]
    # Иначе командная строка подписки списывала бы деньги с ключа из .env.
    clean_env = {name: value for name, value in os.environ.items() if name not in API_KEY_NAMES}
    try:
        done = subprocess.run(
            argv, input=input, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=CLI_TIMEOUT_SECONDS, cwd=cwd, env=clean_env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return done.returncode, done.stdout or done.stderr


def rank_models(names: list[str]) -> list[str]:
    """Текстовые модели от самой слабой к самой сильной."""

    def key(name: str) -> tuple:
        words = re.split(r"[-_.:/]", name.lower())
        tier = next((index for index, word in enumerate(TIERS) if word in words), len(TIERS))
        version = tuple(-int(part) for part in re.findall(r"\d+", name))
        return tier, bool(DATED.search(name)), version

    cleaned = [name.removeprefix("models/") for name in names]
    return sorted((name for name in cleaned if not NOT_TEXT.search(name.lower())), key=key)


class CliChat:
    """Модель из подписки через её командную строку: инструменты выключены, запрос идёт через stdin."""

    def __init__(self, name: str, model: str, run: Callable = _run):
        self.name, self.model, self._run = name, model, run

    def __call__(self, messages: list[dict]) -> str:
        # Весь текст идёт через stdin: на Windows многострочные аргументы .cmd обрезаются.
        prompt = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)
        with tempfile.TemporaryDirectory() as empty_dir:
            code, output = self._run(self._command(), input=prompt, cwd=empty_dir)
        if code != 0 or not output.strip():
            raise LLMError(f"{self.name} не вернул ответ (код {code}): проверьте вход и лимит подписки.")
        return output

    def _command(self) -> list[str]:
        if self.name == "claude-cli":
            return [
                "claude", "-p", "--model", self.model, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                "--system-prompt", "Выполни задание из сообщения и верни только то, что оно требует.",
            ]
        if self.name == "codex-cli":
            return [
                "codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                "--color", "never", "-c", 'model_reasoning_effort="low"', "-m", self.model, "-",
            ]
        return ["gemini", "-m", self.model, "-p", ""]


class DemoChat:
    """Проверка сервиса без ключей: отдаёт записанный ответ модели для товаров из examples."""

    def __init__(self, recorded_dir: Path = RECORDED_DIR):
        self.recorded_dir = recorded_dir

    def __call__(self, messages: list[dict]) -> str:
        request = "\n".join(message["content"] for message in messages)
        for path in sorted(self.recorded_dir.glob("*.json")):
            card = json.loads(path.read_text(encoding="utf-8"))[0]
            if json.dumps(card["name"], ensure_ascii=False)[1:-1] in request and card.get("seo_title"):
                return json.dumps(card, ensure_ascii=False)
        raise LLMError("В демо есть только товары из examples/input с готовым черновиком: для других нужна модель.")


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str
    models: tuple[str, ...]
    make: Callable[[str], Callable] = field(compare=False)

    @property
    def model(self) -> str:
        return self.models[0]


def _claude_cli(which, run) -> Candidate | None:
    if not which("claude"):
        return None
    code, output = run(["claude", "auth", "status"])
    try:
        logged_in = code == 0 and json.loads(output).get("loggedIn")
    except ValueError:
        logged_in = False
    if not logged_in:
        return None
    return Candidate("claude-cli", "подписка", ("haiku", "sonnet", "opus"), lambda m: CliChat("claude-cli", m, run))


def _codex_cli(which, run) -> Candidate | None:
    if not which("codex"):
        return None
    code, output = run(["codex", "login", "status"])
    if code != 0 or "Logged in" not in output:
        return None
    code, output = run(["codex", "debug", "models"])
    try:
        listed = [m for m in json.loads(output)["models"] if m.get("visibility") == "list"]
    except (ValueError, KeyError, TypeError):
        return None
    # Codex показывает модели от основной к запасной: у самой слабой наибольший priority.
    models = tuple(m["slug"] for m in sorted(listed, key=lambda m: -m.get("priority", 0)))
    return Candidate("codex-cli", "подписка", models, lambda m: CliChat("codex-cli", m, run)) if models else None


def _gemini_cli(which, run, env) -> Candidate | None:
    home = env.get("HOME") or os.path.expanduser("~")
    if not which("gemini") or not os.path.exists(os.path.join(home, ".gemini", "oauth_creds.json")):
        return None
    models = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro")
    return Candidate("gemini-cli", "подписка", models, lambda m: CliChat("gemini-cli", m, run))


def _list_models(base_url: str, headers: dict, transport) -> list[str]:
    try:
        response = httpx.get(f"{base_url}/models", headers=headers, timeout=20) if transport is None else \
            httpx.Client(transport=transport).get(f"{base_url}/models", headers=headers)
        response.raise_for_status()
        return [item["id"] for item in response.json()["data"]]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []


def _api(name: str, key: str, base_url: str, transport) -> Candidate | None:
    if name == "anthropic":
        headers, client = {"x-api-key": key, "anthropic-version": "2023-06-01"}, AnthropicClient
    else:
        headers, client = {"Authorization": f"Bearer {key}"}, LLMClient
    models = tuple(rank_models(_list_models(base_url, headers, transport)))
    if not models:
        return None
    return Candidate(name, "ключ API", models, lambda m: client(LLMConfig(key, base_url, m), transport=transport).chat)


def scan(env=os.environ, which=shutil.which, run: Callable = _run, transport=None) -> list[Candidate]:
    found = [_claude_cli(which, run), _codex_cli(which, run), _gemini_cli(which, run, env)]
    keys = {
        "anthropic": (env.get("ANTHROPIC_API_KEY"), ANTHROPIC_URL),
        "openai": (env.get("OPENAI_API_KEY"), OPENAI_URL),
        "google": (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"), GOOGLE_URL),
    }
    found += [_api(name, key, url, transport) for name, (key, url) in keys.items() if key]
    return [candidate for candidate in found if candidate]


class Chain:
    """Модели по очереди: если одна недоступна или исчерпала лимит, запрос уходит следующей."""

    def __init__(self, steps: list[tuple[str, Callable]]):
        self.steps = steps
        self.used = ""

    def __call__(self, messages: list[dict]) -> str:
        failures = []
        for label, chat in self.steps:
            try:
                answer = chat(messages)
            except LLMError as error:
                failures.append(f"{label}: {error}")
                continue
            self.used = label
            return answer
        raise LLMError("; ".join(failures))


def build_chat_from(
    env=os.environ, which=shutil.which, run: Callable = _run, transport=None, provider: str | None = None, model: str | None = None
) -> Chain:
    provider = provider or env.get("LLM_PROVIDER") or "auto"
    if provider == DEMO:
        return Chain([(f"{DEMO}/{DEMO_LABEL}", DemoChat())])
    steps = []
    if env.get("LLM_BASE_URL") and provider in ("auto", "compatible"):
        config = config_from_env(env)
        steps.append((f"compatible/{config.model}", LLMClient(config, transport=transport).chat))
    if provider != "compatible":
        for candidate in scan(env, which, run, transport):
            if provider in ("auto", candidate.name):
                chosen = model if provider != "auto" and model else candidate.model
                if chosen not in candidate.models:
                    raise LLMError(f"У {candidate.name} нет модели {chosen}. Посмотрите список: card-draft --scan.")
                steps.append((f"{candidate.name}/{chosen}", candidate.make(chosen)))
    if not steps:
        raise LLMError(HELP)
    return Chain(steps)


def build_chat(provider: str | None = None, model: str | None = None) -> Chain:
    load_dotenv()
    return build_chat_from(provider=provider, model=model)


def available_models() -> list[dict]:
    load_dotenv()
    return [{"provider": c.name, "kind": c.kind, "models": list(c.models)} for c in scan()]
