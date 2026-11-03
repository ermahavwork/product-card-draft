"""Запуск из командной строки: card-draft product.json [--format md]."""

import argparse
import json
import sys
from pathlib import Path

from .input_data import InputError, load_products
from .llm import LLMError
from .providers import available_models, build_chat
from .render import to_markdown
from .seo_data import add_seo_data
from .service import make_draft

EXIT_OK, EXIT_NEEDS_ATTENTION, EXIT_BAD_INPUT, EXIT_API = 0, 1, 2, 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Черновик карточки товара по данным о приборе.")
    parser.add_argument("file", nargs="?", help="JSON-файл с товаром или списком товаров; «-» читает стандартный ввод")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    parser.add_argument("--scan", action="store_true", help="показать доступные подписки и ключи")
    parser.add_argument("--provider", help="claude-cli, codex-cli, gemini-cli, anthropic, openai, google, compatible")
    parser.add_argument("--model", help="модель выбранного провайдера; по умолчанию самая слабая")
    args = parser.parse_args(argv)

    if args.scan:
        print(json.dumps(available_models(), ensure_ascii=False, indent=2))
        return EXIT_OK
    if not args.file:
        parser.error("укажите файл с товаром или --scan")

    try:
        products = load_products(_read(args.file))
    except InputError as error:
        print(error, file=sys.stderr)
        return EXIT_BAD_INPUT
    try:
        chat = build_chat(args.provider, args.model)
    except LLMError as error:
        print(error, file=sys.stderr)
        return EXIT_API

    results = [add_seo_data(make_draft(product, chat), product) for product in products]
    if args.format == "md":
        print("\n---\n\n".join(to_markdown(result) for result in results))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return _exit_code({result["status"] for result in results})


def _read(path: str) -> str:
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"Не удалось прочитать файл {path}: {error.strerror}.") from error
    except UnicodeDecodeError as error:
        raise InputError(f"Файл {path} должен быть в кодировке UTF-8.") from error


def _exit_code(statuses: set[str]) -> int:
    if "error" in statuses:
        return EXIT_API
    return EXIT_OK if statuses == {"ready"} else EXIT_NEEDS_ATTENTION


if __name__ == "__main__":
    sys.exit(main())
