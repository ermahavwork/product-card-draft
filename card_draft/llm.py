"""Клиент LLM по протоколу OpenAI Chat Completions: OpenAI, OpenRouter, Groq, LM Studio, Ollama и другие."""

import ipaddress
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 90
MAX_RETRY_AFTER_SECONDS = 30
TEMPORARY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Сбой обращения к модели: сообщение показывается пользователю и не содержит ключа."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str


def build_chat():
    load_dotenv()
    return LLMClient(config_from_env()).chat


def config_from_env(env=os.environ) -> LLMConfig:
    base_url = env.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    try:
        parsed = urlparse(base_url)
        host, _ = parsed.hostname, parsed.port
    except ValueError as error:
        raise LLMError("LLM_BASE_URL должен быть адресом вида https://host/v1.") from error
    if parsed.scheme not in ("http", "https") or not host:
        raise LLMError("LLM_BASE_URL должен быть адресом вида https://host/v1.")
    model = env.get("LLM_MODEL", "").strip()
    if not model:
        raise LLMError("Не задан LLM_MODEL: укажите модель в файле .env.")
    api_key = env.get("LLM_API_KEY", "").strip()
    if not api_key and not _is_local(host):
        raise LLMError("Не задан LLM_API_KEY: укажите ключ в файле .env.")
    if not api_key.isascii():
        raise LLMError("LLM_API_KEY содержит недопустимые символы.")
    return LLMConfig(api_key=api_key, base_url=base_url, model=model)


def _is_local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


class LLMClient:
    def __init__(self, config: LLMConfig, transport=None, sleep=time.sleep):
        self.config = config
        self._sleep = sleep
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        self._http = httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS, transport=transport)

    def chat(self, messages: list[dict[str, str]]) -> str:
        body = {"model": self.config.model, "messages": messages, "temperature": 0.2}
        return _read_text(self._post_with_retries(body))

    def _post_with_retries(self, body: dict) -> httpx.Response:
        failure, delay = "", 0.0
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(delay)
            delay = 2.0**attempt
            try:
                response = self._http.post(f"{self.config.base_url}/chat/completions", json=body)
            except httpx.TimeoutException:
                failure = f"Модель не ответила за {TIMEOUT_SECONDS} с."
                continue
            except httpx.HTTPError:
                failure = "Модель не ответила: нет соединения с сервером API."
                continue
            if response.status_code not in TEMPORARY_STATUSES:
                self._raise_for_permanent(response)
                return response
            failure = f"API временно недоступен (код {response.status_code})."
            delay = _retry_after(response) or delay
        raise LLMError(f"{failure} Сделано попыток: {MAX_ATTEMPTS}.")

    def _raise_for_permanent(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise LLMError(f"API отклонил ключ или доступ (код {status}): проверьте LLM_API_KEY.")
        if status == 404:
            raise LLMError("API не нашёл модель или адрес (код 404): проверьте LLM_MODEL и LLM_BASE_URL.")
        reason = response.text[:200].replace(self.config.api_key, "***") if self.config.api_key else response.text[:200]
        raise LLMError(f"API не принял запрос (код {status}): {reason}")


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return max(0.0, min(float(response.headers.get("retry-after", "")), MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        return None


def _read_text(response: httpx.Response) -> str:
    try:
        choice = response.json()["choices"][0]
        text = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise LLMError("API вернул ответ неожиданного формата.") from error
    if choice.get("finish_reason") == "length":
        raise LLMError("Ответ модели обрезан по лимиту длины.")
    if not isinstance(text, str) or not text.strip():
        raise LLMError("API вернул пустой ответ.")
    return text
