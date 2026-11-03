"""Страница приложения Angular и два метода API."""

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .input_data import InputError, load_products
from .llm import LLMError
from .providers import DEMO, DEMO_LABEL, available_models, build_chat
from .render import to_markdown
from .seo_data import add_seo_data
from .service import make_draft


EXAMPLES = (
    ("trm138v-shch7-t.json", "ТРМ138В-Щ7.Т, регулятор"),
    ("bust3.json", "БУСТ3, блок управления"),
    ("kleshchi-200a.json", "Клещи токовые 200 А: данных мало"),
    ("no-data.json", "Манометр: данных нет"),
    ("assignment-injection.json", "Манометр: команда внутри описания"),
)


def _error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


@ensure_csrf_cookie
@require_GET
def index(request: HttpRequest) -> HttpResponse:
    page = settings.FRONTEND_DIR / "index.html"
    return HttpResponse(page.read_text(encoding="utf-8"))


@require_GET
def models(request: HttpRequest) -> JsonResponse:
    demo = {"provider": DEMO, "kind": "без ключей", "models": [DEMO_LABEL]}
    return JsonResponse({"providers": [*available_models(), demo]})


@require_GET
def examples(request: HttpRequest) -> JsonResponse:
    folder = settings.BASE_DIR / "examples" / "input"
    items = [{"title": title, "product": (folder / name).read_text(encoding="utf-8")} for name, title in EXAMPLES]
    return JsonResponse({"examples": items})


@require_POST
def draft(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, ValueError):
        return _error(400, "Тело запроса должно быть JSON в кодировке UTF-8.")
    if not isinstance(body, dict) or not isinstance(body.get("product"), str):
        return _error(400, "Передайте данные о товаре в поле product.")
    try:
        products = load_products(body["product"])
    except InputError as error:
        return _error(400, str(error))
    if len(products) != 1:
        return _error(400, "В форме можно обработать только один товар.")
    try:
        chat = build_chat(body.get("provider") or None, body.get("model") or None)
    except LLMError as error:
        return _error(503, str(error))
    result = add_seo_data(make_draft(products[0], chat), products[0])
    return JsonResponse(result | {"markdown": to_markdown(result)})
