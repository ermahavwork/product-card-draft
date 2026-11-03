"""Простая веб-форма: uvicorn card_draft.web:app"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from .input_data import InputError, load_products
from .llm import LLMError, build_chat
from .render import to_markdown
from .service import make_draft

app = FastAPI(title="Черновик карточки товара")
PAGE = (Path(__file__).parent / "form.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def form() -> str:
    return PAGE


@app.post("/api/draft")
async def draft(request: Request) -> dict:
    try:
        products = load_products((await request.body()).decode("utf-8"))
    except UnicodeDecodeError as error:
        raise HTTPException(400, "Данные должны быть в кодировке UTF-8.") from error
    except InputError as error:
        raise HTTPException(400, str(error)) from error
    if len(products) != 1:
        raise HTTPException(400, "В форме можно обработать только один товар.")
    try:
        chat = build_chat()
    except LLMError as error:
        raise HTTPException(503, str(error)) from error
    result = make_draft(products[0], chat)
    return result | {"markdown": to_markdown(result)}
