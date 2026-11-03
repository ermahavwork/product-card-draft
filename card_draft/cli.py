"""Запуск из командной строки: card-draft product.json [--format md]."""

import argparse
import json
import sys
from pathlib import Path

from .input_data import InputError, load_products
from .llm import LLMError, build_chat
from .render import to_markdown
from .service import make_draft

EXIT_OK, EXIT_NEEDS_ATTENTION, EXIT_BAD_INPUT, EXIT_API = 0, 1, 2, 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Черновик карточки товара по данным о приборе.")
    parser.add_argument("file", help="JSON-файл с товаром или списком товаров; «-» читает стандартный ввод")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    args = parser.parse_args(argv)

    try:
        products = load_products(_read(args.file))
    except InputError as error:
        print(error, file=sys.stderr)
        return EXIT_BAD_INPUT
    try:
        chat = build_chat()
    except LLMError as error:
        print(error, file=sys.stderr)
        return EXIT_API

    results = [make_draft(product, chat) for product in products]
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
