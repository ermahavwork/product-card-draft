import pytest

from card_draft.input_data import InputError, load_products


def one(text):
    return load_products(text)[0]


def test_reads_the_example_from_the_assignment():
    product = one(
        '{"name": "Манометр показывающий DM 02", "manufacturer": "Манотомь",'
        '"specs": {"класс точности": "1,5"}, "description": "Прибор для измерения."}'
    )
    assert product.name == "Манометр показывающий DM 02"
    assert product.manufacturer == "Манотомь"
    assert product.specs == {"класс точности": "1,5"}
    assert product.description == "Прибор для измерения."
    assert product.blockers() == []


def test_array_gives_several_products():
    assert len(load_products('[{"name": "А"}, {"name": "Б"}]')) == 2


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("{broken", "строка 1"),
        ("", "пуст"),
        ("   ", "пуст"),
        ("[]", "пуст"),
        ('"текст"', "объект"),
        ("[1]", "объект"),
        ('{"name": NaN}', "NaN"),
        ('{"name": "А", "name": "Б"}', "дважды"),
        ('{"name": 5}', "name"),
        ('{"name": "А", "specs": ["класс"]}', "specs"),
        ('{"name": "А", "specs": {"х": {"вложенный": 1}}}', "х"),
    ],
)
def test_invalid_input_is_explained(text, fragment):
    with pytest.raises(InputError) as error:
        load_products(text)
    assert fragment in str(error.value)


def test_oversized_input_is_refused():
    with pytest.raises(InputError, match="слишком"):
        load_products('{"name": "' + "я" * 60_000 + '"}')


def test_bom_is_tolerated():
    assert one('﻿{"name": "А"}').name == "А"


@pytest.mark.parametrize("empty", ['""', '"  "', '"-"', '"—"', '"н/д"', '"Нет данных"', "null"])
def test_empty_marks_count_as_missing_value(empty):
    product = one('{"name": "А", "specs": {"класс точности": %s}}' % empty)
    assert product.specs == {}
    assert product.empty_specs == ["класс точности"]


def test_real_value_no_is_kept():
    assert one('{"name": "А", "specs": {"С дисплеем": "Нет"}}').specs == {"С дисплеем": "Нет"}


def test_numbers_and_lists_become_text():
    product = one('{"name": "А", "specs": {"класс": 1.5, "выходы": ["4-20 мА", "RS-485"]}}')
    assert product.specs == {"класс": "1.5", "выходы": "4-20 мА, RS-485"}


def test_html_and_spaces_are_cleaned():
    product = one('{"name": " Прибор\\u00a0 А ", "description": "<p>Текст &amp; <b>данные</b></p>"}')
    assert product.name == "Прибор А"
    assert product.description == "Текст & данные"


def test_unknown_field_is_reported():
    assert any("specifications" in note for note in one('{"name": "А", "specifications": {}}').notes)


def test_missing_name_blocks_generation():
    assert any("name" in item for item in one('{"specs": {"класс": "1"}}').blockers())


def test_nothing_to_write_from_blocks_generation():
    assert any("specs" in item for item in one('{"name": "А"}').blockers())


def test_only_description_is_enough_to_generate():
    assert one('{"name": "А", "description": "Текст"}').blockers() == []


def test_missing_manufacturer_is_only_a_note():
    product = one('{"name": "А", "specs": {"к": "1"}}')
    assert product.blockers() == []
    assert any("manufacturer" in note for note in product.notes)


def test_comparison_signs_are_not_treated_as_tags():
    product = one('{"name": "А", "specs": {"рабочие условия": "давление <1,6 МПа, температура >50 °C"}}')
    assert product.specs["рабочие условия"] == "давление <1,6 МПа, температура >50 °C"


def test_encoded_tags_are_removed():
    assert one('{"name": "А", "description": "&lt;script&gt;x&lt;/script&gt;текст"}').description == "x текст"


def test_double_encoded_quote_is_restored():
    assert one('{"name": "для &amp;quot;К-3&amp;quot;", "description": "т"}').name == 'для "К-3"'


@pytest.mark.parametrize(
    "text",
    ["[" * 49_000, '{"name": ' + "1" * 5000 + "}", '{"name": "\\ud800", "description": "т"}', '{"name": "А", "specs": {"к": 1e999}}'],
)
def test_pathological_json_is_explained(text):
    with pytest.raises(InputError):
        load_products(text)


def test_empty_marks_in_text_fields_count_as_missing():
    product = one('{"name": "-", "manufacturer": "н/д", "description": "-"}')
    assert len(product.blockers()) == 2
