import pytest

from app.utils.json_utils import parse_json_lenient, parse_json_or_default


def test_plain_json():
    assert parse_json_lenient('{"a": 1}') == {"a": 1}


def test_code_fenced_json():
    raw = "```json\n{\"a\": 1, \"b\": [2, 3]}\n```"
    assert parse_json_lenient(raw) == {"a": 1, "b": [2, 3]}


def test_prose_wrapped_json():
    raw = 'Here is the result:\n{"result": "COMPLIANT"}\nThanks.'
    assert parse_json_lenient(raw) == {"result": "COMPLIANT"}


def test_array_fallback():
    assert parse_json_lenient("noise [1, 2, 3] trailing") == [1, 2, 3]


def test_unrepairable_raises():
    with pytest.raises(ValueError):
        parse_json_lenient("not json at all")


def test_or_default():
    assert parse_json_or_default("garbage", {"findings": []}) == {"findings": []}
