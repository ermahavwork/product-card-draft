"""Проверки без LLM: характеристики берём из входа, текст модели сверяем с входом."""

import re

from .input_data import Product

TITLE_MAX = 70
DESCRIPTION_MIN, DESCRIPTION_MAX = 800, 1200
QUERIES_MIN, QUERIES_MAX = 3, 5
NO_DATA = "данных нет"

# Минимальный состав карточки: название строки → как она называется среди specs.
EXPECTED_SPECS = {
    "Диапазон измерений": r"диапазон измерен|пределы? измерен",
    "Класс точности": r"класс точности|класс допуска|погрешност",
    "Питание": r"^питание|^напряжение питания",
    "Тип корпуса": r"^корпус|тип корпуса",
    "Интерфейсы": r"интерфейс|выходной сигнал|выход\. сигнал|коммуникац",
}

# Утверждения, которые нельзя делать без подтверждения во входных данных. Список не полон.
CLAIMS = {
    "гост": r"\bгост\b|\bгост\s?\d",
    "госреестр": r"госреестр|государственн\w* реестр",
    "поверка": r"поверк|поверочн|поверен",
    "сертификат": r"сертифи",
    "гарантия": r"гарант",
    "взрывозащита": r"взрывозащ|искробезопас",
    "в наличии": r"в наличии",
    "доставка": r"доставк",
    "цена": r"\bцен[аыеу]\b(?! делени)|\bскидк|\bстоимост",
    "материал": r"нержавеющ|керамическ|латун|алюмини",
    "страна производства": r"российск|отечественн|импортн|сделан\w* в\b",
    "самый": r"\bсам(ый|ая|ое|ого|ой|ых|ым)\b|\bлучш(ий|ая|ее|ие|его)\b|\bнаилучш",
}

UNITS = (
    "МПа|кПа|Па|бар|мбар|атм|°C|мм|см|км|мА|мкА|кВ|мВ|ВА|В|А|кВт|Вт|кГц|МГц|Гц|кОм|МОм|Ом|мкФ|мГн|мс|мин|кг|лет|года|год|%"
    "|вольт(?:а|ов)?|ампер(?:а|ов)?"
)
LONG_UNITS = {"вольт": "В", "ампер": "А"}
NOT_LETTER = r"(?![А-Яа-яЁёA-Za-z])"
NUMBER = r"\d+(?:[.,]\d+)?"
# Значение, а не часть обозначения: G1/2, M20, PRT-100 и ТРМ138В сюда не попадают.
FREE_NUMBER_RE = re.compile(rf"(?<![\w/,])(?<!\d\.)(?<![A-Za-zА-Яа-яЁё]-)([-+−]?)({NUMBER})(?![\w/])")
RANGE_RE = re.compile(
    rf"(?<![\w/,])(?<!\d\.)((?:[-+−]?{NUMBER}\s*(?:…|\.\.\.|–|—|-|до|÷)\s*)*[-+−]?{NUMBER})\s*({UNITS}){NOT_LETTER}"
)
SIGNED_RE = re.compile(rf"(?:(?<=\s)|(?<=^)|(?<=[(…]))[-+−]{NUMBER}|{NUMBER}")
UNIT_WORD_RE = re.compile(rf"(?<![А-Яа-яЁёA-Za-z])({UNITS}){NOT_LETTER}")
LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+\-]*")
CODE_RE = re.compile(r"[А-ЯЁ]+-?\d[\wА-Яа-яЁё\-]*")
DENIED_VALUES = {"нет", "отсутствует", "не предусмотрено", "не предусмотрен"}
IGNORED_KEY_WORDS = {"наличие", "есть", "подходит", "тип", "степень", "для"}


def key_specs(product: Product) -> list[dict[str, str]]:
    """Список характеристик собирается кодом: значения модели сюда не попадают."""
    result = [{"name": name, "value": value} for name, value in product.specs.items()]
    result += [{"name": name, "value": NO_DATA} for name in product.empty_specs]
    keys = [key.lower() for key in (*product.specs, *product.empty_specs)]
    for name, pattern in EXPECTED_SPECS.items():
        if not any(re.search(pattern, key) for key in keys):
            result.append({"name": name, "value": NO_DATA})
    return result


def has_thin_data(product: Product) -> bool:
    """Фактов меньше, чем нужный объём описания: добирать его можно только выдумкой."""
    return len(_source_text(product)) < DESCRIPTION_MIN


def find_unsupported(text: str, product: Product) -> list[str]:
    source = _source_text(product)
    found = _unsupported_numbers(text, product)
    found += _unsupported_tokens(text, source)
    found += _unsupported_claims(text, source)
    found += _denied_features(text, product)
    return list(dict.fromkeys(found))


def check_card(card: dict, product: Product) -> list[str]:
    problems = _check_title(card) + _check_description(card, has_thin_data(product)) + _check_queries(card) + _check_commercial(card)
    for item in find_unsupported(_card_text(card), product):
        problems.append(f"Нет во входных данных: {item}")
    return problems


def _source_text(product: Product) -> str:
    parts = [product.name, product.manufacturer, product.description]
    for key, value in product.specs.items():
        parts += [key, value]
    return _normalize(" \n ".join(parts))


def _normalize(text: str) -> str:
    return re.sub(r"[º⁰]", "°", text).replace("°С", "°C").replace("° C", "°C").replace("\u00a0", " ")


def _number(sign: str, value: str) -> str:
    return ("-" if sign in ("-", "−") else "") + value.replace(",", ".")


def _unit(raw: str) -> str:
    for start, short in LONG_UNITS.items():
        if raw.startswith(start):
            return short
    return raw


def _pairs(text: str) -> list[tuple[str, str, str]]:
    """Все пары «число + единица»: в диапазоне единица относится к каждому числу."""
    pairs = []
    for match in RANGE_RE.finditer(text):
        unit = _unit(match.group(2))
        for raw in SIGNED_RE.findall(match.group(1)):
            sign = raw[0] if raw[0] in "-+−" else ""
            pairs.append((_number(sign, raw.lstrip("-+−")), unit, raw))
    return pairs


def _free_numbers(text: str) -> set[str]:
    return {_number(sign, value) for sign, value in FREE_NUMBER_RE.findall(text)}


def _source_values(product: Product) -> tuple[set[tuple[str, str]], set[str]]:
    texts = [_normalize(text) for text in (product.name, product.manufacturer, product.description)]
    pairs, numbers = set(), set()
    for key, value in product.specs.items():
        key, value = _normalize(key), _normalize(value)
        texts += [key, value]
        for unit in UNIT_WORD_RE.findall(key):
            pairs |= {(number, _unit(unit)) for number in _free_numbers(value)}
    for text in texts:
        pairs |= {(number, unit) for number, unit, _ in _pairs(text)}
        numbers |= _free_numbers(text)
    numbers |= {number for number, _ in pairs}
    return pairs, numbers


def _unsupported_numbers(text: str, product: Product) -> list[str]:
    text = _normalize(text)
    source_pairs, source_numbers = _source_values(product)
    found = [f"{raw} {unit}" for number, unit, raw in _pairs(text) if (number, unit) not in source_pairs]
    found += [
        sign + value
        for sign, value in FREE_NUMBER_RE.findall(text)
        if _number(sign, value) not in source_numbers
    ]
    return found


def _unsupported_tokens(text: str, source: str) -> list[str]:
    lowered = source.lower()
    return [token for token in (*LATIN_RE.findall(text), *CODE_RE.findall(text)) if not _token_in(token, lowered)]


def _token_in(token: str, lowered_source: str) -> bool:
    """Обозначение ищется целиком, пробелы и дефисы не важны: Pt100 = Pt 100, RS485 = RS-485."""
    letters = [re.escape(char) for char in token.lower() if char != "-"]
    pattern = r"[\s\-]?".join(letters)
    return re.search(rf"(?<![a-zа-яё0-9]){pattern}(?![a-zа-яё0-9])", lowered_source) is not None


def _unsupported_claims(text: str, source: str) -> list[str]:
    lowered_text, lowered_source = text.lower(), source.lower()
    return [
        claim
        for claim, pattern in CLAIMS.items()
        if re.search(pattern, lowered_text) and not re.search(pattern, lowered_source)
    ]


def _denied_features(text: str, product: Product) -> list[str]:
    """Вход говорит «нет», а текст утверждает обратное: «С дисплеем: Нет» → «прибор с дисплеем»."""
    lowered = text.lower()
    found = []
    for key, value in product.specs.items():
        if value.lower() not in DENIED_VALUES:
            continue
        words = [w for w in re.findall(r"[а-яё]+", key.lower()) if len(w) > 3 and w not in IGNORED_KEY_WORDS]
        if not words:
            continue
        stem = max(words, key=len)[:6]
        for match in re.finditer(stem, lowered):
            clause = re.split(r"[,.;:]", lowered[max(0, match.start() - 20) : match.start()])[-1]
            if not re.search(r"\b(не|нет|без)\b", clause):
                found.append(f"{key}: во входных данных «{value}»")
                break
    return found


def _check_title(card: dict) -> list[str]:
    title = card.get("seo_title")
    if not isinstance(title, str) or not title.strip():
        return ["Нет seo_title."]
    if len(title) > TITLE_MAX:
        return [f"seo_title: {len(title)} символов, нужно до {TITLE_MAX}."]
    return []


def _check_description(card: dict, thin: bool) -> list[str]:
    text = card.get("seo_description")
    if not isinstance(text, str) or not text.strip():
        return ["Нет seo_description."]
    minimum = 1 if thin else DESCRIPTION_MIN
    if not minimum <= len(text) <= DESCRIPTION_MAX:
        return [f"seo_description: {len(text)} символов, нужно {DESCRIPTION_MIN}–{DESCRIPTION_MAX}."]
    return []


def _check_queries(card: dict) -> list[str]:
    queries = card.get("search_queries")
    if not isinstance(queries, list) or not all(isinstance(q, str) and q.strip() for q in queries):
        return ["Нет search_queries: нужен список непустых строк."]
    unique = {q.strip().lower() for q in queries}
    if len(unique) != len(queries):
        return ["search_queries содержит повторы."]
    if not QUERIES_MIN <= len(queries) <= QUERIES_MAX:
        return [f"search_queries: {len(queries)} шт., нужно {QUERIES_MIN}–{QUERIES_MAX}."]
    return []


def _check_commercial(card: dict) -> list[str]:
    block = card.get("commercial_block")
    if not isinstance(block, dict):
        return ["Нет commercial_block."]
    return [
        f"Нет commercial_block.{part}."
        for part in ("audience", "tasks")
        if not isinstance(block.get(part), str) or not block[part].strip()
    ]


def _card_text(card: dict) -> str:
    parts = [card.get("seo_title"), card.get("seo_description")]
    queries = card.get("search_queries")
    if isinstance(queries, list):
        parts += queries
    block = card.get("commercial_block")
    if isinstance(block, dict):
        parts += [block.get("audience"), block.get("tasks")]
    return " \n ".join(part for part in parts if isinstance(part, str))
