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


def test_extract_json_smart_quotes():
    """LLMs sometimes produce curly/smart quotes inside JSON string values."""
    text = '{"text": "They said \u201chello\u201d to us"}'
    result = _extract_json(text)
    assert "hello" in result["text"]


def test_extract_json_code_fence_with_smart_quotes():
    """Real failure case: code fence + Korean text with curly quotes."""
    text = '```json\n{"passage": "댓글로 \u201c희망!\u201d라고"}\n```'
    result = _extract_json(text)
    assert "희망" in result["passage"]
