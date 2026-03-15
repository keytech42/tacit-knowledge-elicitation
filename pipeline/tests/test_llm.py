"""Tests for LLM wrapper — JSON extraction and error handling."""

import json

import pytest

from pipeline.llm import _clean_json_text, _extract_json


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


# --- _clean_json_text tests ---


def test_clean_json_text_smart_quotes():
    cleaned = _clean_json_text('say \u201chello\u201d')
    assert "\u201c" not in cleaned
    assert "\u201d" not in cleaned


def test_clean_json_text_control_chars():
    cleaned = _clean_json_text('hello\x00world')
    assert "\x00" not in cleaned
    assert "\\u0000" in cleaned


def test_clean_json_text_passthrough():
    """Normal text should pass through unchanged."""
    text = '{"key": "value"}'
    assert _clean_json_text(text) == text


# --- Multi-strategy fallback tests ---


def test_extract_json_bom_prefix():
    """BOM character before JSON should be handled via { } extraction."""
    text = '\ufeff{"key": "value"}'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_preamble_and_smart_quotes_combined():
    """Preamble text + smart quotes requires both { } extraction and cleanup."""
    text = 'Here is the result:\n{"text": "they said \u201chi\u201d"}'
    result = _extract_json(text)
    assert "hi" in result["text"]


def test_extract_json_code_fences_not_at_start():
    """Code fences appearing after other text should still be stripped."""
    text = 'Sure, here you go:\n```json\n{"key": "value"}\n```'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_multiple_strategies_no_false_positive():
    """Text with braces but no valid JSON should still raise."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json("function() { return 42; }")
