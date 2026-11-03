import pytest

from card_draft.checks import check_card, find_unsupported, key_specs
from card_draft.input_data import Product

PRODUCT = Product(
    name="Преобразователь давления PRT-100-1,6-1,0-M20",
    manufacturer="EKF",
    specs={
        "Диапазон измерений, МПа": "0...1,6",
        "Напряжение питания": "24",
        "Выход. сигнал": "4-20мА",
        "Степень защиты (IP)": "IP65",
        "Взрывозащищенный": "Нет",
        "С дисплеем": "Нет",
    },
    description="Общепромышленные преобразователи с керамической мембраной для ГВС и ХВС. " * 12,
)


@pytest.mark.parametrize(
    "text",
    [
        "Диапазон 0–1,6 МПа, выход 4–20 мА, защита IP65",
        "Преобразователь PRT-100-1,6-1,0-M20 от EKF для ГВС и ХВС",
        "Керамическая мембрана и питание 24",
        "Прибор не имеет взрывозащиты и работает без дисплея",
    ],
)
def test_values_from_input_pass(text):
    assert find_unsupported(text, PRODUCT) == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Класс точности 0,5", "0,5"),
        ("Диапазон до 1,6 кПа", "1,6 кПа"),
        ("Питание 24 В", "24 В"),
        ("Интерфейс RS-485", "RS-485"),
        ("Протокол HART", "HART"),
        ("Соответствует ГОСТ", "гост"),
        ("Занесён в Госреестр", "госреестр"),
        ("Гарантия от производителя", "гарант"),
        ("Есть в наличии на складе", "в наличии"),
        ("Самый надёжный датчик", "самый"),
        ("Взрывозащищенный корпус", "Взрывозащищенный"),
        ("Удобный прибор с дисплеем", "С дисплеем"),
    ],
)
def test_invented_values_are_caught(text, expected):
    assert any(expected.lower() in item.lower() for item in find_unsupported(text, PRODUCT))


MANOMETER = Product(
    name="Манометр показывающий DM 02",
    manufacturer="Манотомь",
    specs={"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5", "присоединение": "G1/2", "диаметр корпуса": "100 мм"},
    description="Прибор предназначен для измерения избыточного давления.",
)


@pytest.mark.parametrize("text", ["Диапазон 0–2 МПа", "Класс точности 1", "Питание 138 В", "Давление до 20 кПа"])
def test_digits_inside_designations_are_not_values(text):
    product = Product(name="ТРМ138В PRT-100-M20", specs=MANOMETER.specs)
    assert find_unsupported(text, product)


@pytest.mark.parametrize("text", ["Резьба G1/2 на манометре DM 02", "Корпус 100 мм, диапазон 0–1,6 МПа", "Класс точности 1,5 с присоединением G1/2"])
def test_manometer_normal_text_passes(text):
    assert find_unsupported(text, MANOMETER) == []


def test_sign_of_number_matters():
    product = Product(name="Регулятор", specs={"Рабочая температура": "-30…+55 ⁰С"})
    assert find_unsupported("Температура от +30 до +55 °C", product)
    assert find_unsupported("Температура от -30 °C до +55 °C", product) == []


def test_preposition_v_does_not_allow_volts():
    product = Product(name="Датчик", specs={"Питание": "24"}, description="В комплекте паспорт.")
    assert find_unsupported("Питание 24 В", product)
    assert find_unsupported("Питание 24  вольта", product)


def test_unit_in_spec_name_applies_to_its_value_only():
    product = Product(name="Датчик", specs={"Масса, кг": "0,6", "Длина": "154"})
    assert find_unsupported("Масса 0,6 кг", product) == []
    assert find_unsupported("Длина 154 кг", product)


@pytest.mark.parametrize(
    "text",
    ["Прибор сертифицирован", "Включён в Государственный реестр", "Прибор поверен", "Алюминиевый корпус", "Сделано в России",
     "Самого высокого качества", "Наилучшее решение", "Низкая стоимость", "Искробезопасный прибор"],
)
def test_more_claims_are_caught(text):
    assert find_unsupported(text, MANOMETER)


@pytest.mark.parametrize("text", ["Для гостиниц и котельных", "Цена деления шкалы видна", "Лучше читается в цехе"])
def test_common_words_are_not_claims(text):
    assert find_unsupported(text, MANOMETER) == []


def test_latin_token_must_match_whole():
    product = Product(name="Прибор", description="Подходит для scanner")
    assert find_unsupported("Интерфейс CAN", product)


def test_slash_separates_latin_tokens():
    product = Product(name="Прибор", specs={"Интерфейсы": "RS-485, USB"})
    assert find_unsupported("Порты RS-485/USB", product) == []


@pytest.mark.parametrize(
    "key, value, text",
    [("Наличие дисплея", "Нет", "Прибор с дисплеем"), ("Дисплей", "отсутствует", "Прибор с дисплеем"), ("С реле", "Нет", "Без дисплея, с реле")],
)
def test_denied_feature_variants(key, value, text):
    assert find_unsupported(text, Product(name="Прибор", specs={key: value}))


def test_denied_feature_uses_meaningful_word():
    product = Product(name="Прибор", specs={"Защита от перегрузки": "Нет", "Степень защиты": "IP54"})
    assert find_unsupported("Защита корпуса IP54", product) == []


def test_degree_sign_variants_match():
    product = Product(name="Термометр", specs={"Диапазон, ºС": "от -50 до +200"})
    assert find_unsupported("Измеряет от -50 до +200 °C", product) == []


def test_superscript_degree_matches():
    product = Product(name="Регулятор", description="Работа от -30 до +55 ⁰С")
    assert find_unsupported("Работает при температуре до +55 °C", product) == []


def test_range_written_differently_matches_pt_with_space():
    product = Product(name="ТСП", specs={"НСХ": "Pt 100"})
    assert find_unsupported("Датчик Pt100", product) == []


def good_card():
    return {
        "seo_title": "Преобразователь давления PRT-100-1,6-1,0-M20 EKF",
        "seo_description": "Текст. " * 150,
        "search_queries": ["датчик давления ekf", "преобразователь давления prt-100", "датчик давления гвс"],
        "commercial_block": {"audience": "Службы автоматизации.", "tasks": "Контроль давления."},
    }


def test_good_card_has_no_problems():
    assert check_card(good_card(), PRODUCT) == []


def test_title_length_limit():
    card = good_card() | {"seo_title": "я" * 71}
    assert any("71" in problem for problem in check_card(card, PRODUCT))


@pytest.mark.parametrize("length", [799, 1201])
def test_description_length_limits(length):
    card = good_card() | {"seo_description": "я" * length}
    assert any(str(length) in problem for problem in check_card(card, PRODUCT))


@pytest.mark.parametrize("length", [800, 1200])
def test_description_length_bounds_are_allowed(length):
    assert check_card(good_card() | {"seo_description": "я" * length}, PRODUCT) == []


@pytest.mark.parametrize("queries", [["а", "б"], ["а", "б", "в", "г", "д", "е"], ["а", "а", "б"], "текст", ["а", "б", 3]])
def test_bad_query_lists(queries):
    assert check_card(good_card() | {"search_queries": queries}, PRODUCT)


@pytest.mark.parametrize("field", ["seo_title", "seo_description", "search_queries", "commercial_block"])
def test_missing_field_is_a_problem(field):
    card = good_card()
    del card[field]
    assert any(field in problem for problem in check_card(card, PRODUCT))


def test_commercial_block_needs_both_parts():
    card = good_card() | {"commercial_block": {"audience": "Службы."}}
    assert any("tasks" in problem for problem in check_card(card, PRODUCT))


def test_invented_value_in_query_is_a_problem():
    card = good_card() | {"search_queries": ["датчик hart", "датчик", "преобразователь"]}
    assert any("HART".lower() in problem.lower() for problem in check_card(card, PRODUCT))


def test_key_specs_list_input_values_unchanged():
    specs = key_specs(PRODUCT)
    assert {"name": "Напряжение питания", "value": "24"} in specs


def test_expected_absent_spec_is_marked_no_data():
    assert {"name": "Тип корпуса", "value": "данных нет"} in key_specs(PRODUCT)


def test_expected_present_under_other_name_is_not_marked():
    names = [spec["name"] for spec in key_specs(PRODUCT)]
    assert "Диапазон измерений" not in names
    assert "Питание" not in names
    assert "Интерфейсы" not in names


@pytest.mark.parametrize(
    "key, expected",
    [("Материал корпуса", "Тип корпуса"), ("Диапазон рабочих температур", "Диапазон измерений"), ("Встроенный источник питания", "Питание"), ("Выходы", "Интерфейсы")],
)
def test_related_spec_does_not_hide_missing_one(key, expected):
    assert {"name": expected, "value": "данных нет"} in key_specs(Product(name="А", specs={key: "значение"}))


def test_empty_spec_is_marked_no_data():
    product = Product(name="А", specs={"к": "1"}, empty_specs=["Присоединение"])
    assert {"name": "Присоединение", "value": "данных нет"} in key_specs(product)
