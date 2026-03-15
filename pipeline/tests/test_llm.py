"""Tests for LLM wrapper — JSON extraction and error handling."""

import json

import pytest

from pipeline.llm import _extract_json


def test_extract_json_plain():
    assert _extract_json('{"key": "value"}') == {"key": "value"}


def test_extract_json_with_code_fences():
    text = '```json\n{"key": "value"}\n```'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_with_preamble():
    text = 'Here is the JSON:\n\n{"key": "value"}'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_with_trailing_text():
    text = '{"key": "value"}\n\nHope this helps!'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_with_control_chars():
    # Tab character inside a JSON string value
    text = '{"text": "hello\tworld"}'
    result = _extract_json(text)
    assert result["text"] == "hello\tworld"


def test_extract_json_nested():
    text = '{"norms": [{"text": "A norm", "type": "stated"}]}'
    result = _extract_json(text)
    assert len(result["norms"]) == 1


def test_extract_json_no_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("No JSON here at all")


def test_extract_json_whitespace():
    text = '  \n  {"key": "value"}  \n  '
    assert _extract_json(text) == {"key": "value"}
