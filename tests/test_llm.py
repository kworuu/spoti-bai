"""LLM helper tests that don't need an API key or network."""
import pytest

from BackEnd.llm import LLMError, parse_json


def test_plain_json():
    assert parse_json('{"ok": true}') == {"ok": True}


def test_json_wrapped_in_fences():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize("bad", ["", "no json here", "[1, 2]", "{broken"])
def test_bad_output_raises(bad):
    with pytest.raises(LLMError):
        parse_json(bad)