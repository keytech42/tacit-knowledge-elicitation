"""Tests for dedup strategies."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pipeline.dedup.exact import ExactDedup, _normalize
from pipeline.dedup.llm_dedup import DedupResult, LLMDedup
from pipeline.models import GeneratedQuestion


# --- ExactDedup ---


@pytest.mark.asyncio
async def test_exact_dedup_removes_duplicates():
    dedup = ExactDedup()
    questions = [
        GeneratedQuestion(title="How are decisions made?", body="Body A", confidence=0.9),
        GeneratedQuestion(title="How are decisions made?", body="Body B", confidence=0.7),
        GeneratedQuestion(title="Who approves budgets?", body="Body C", confidence=0.8),
    ]
    result = await dedup.dedup(questions)
    assert len(result) == 2
    assert result[0].body == "Body A"  # first occurrence kept
    assert result[1].title == "Who approves budgets?"


@pytest.mark.asyncio
async def test_exact_dedup_case_insensitive():
    dedup = ExactDedup()
    questions = [
        GeneratedQuestion(title="How Are Decisions Made?", body="A", confidence=0.9),
        GeneratedQuestion(title="how are decisions made?", body="B", confidence=0.7),
    ]
    result = await dedup.dedup(questions)
    assert len(result) == 1
    assert result[0].body == "A"


@pytest.mark.asyncio
async def test_exact_dedup_normalizes_punctuation():
    dedup = ExactDedup()
    questions = [
        GeneratedQuestion(title="How are decisions made?", body="A", confidence=0.9),
        GeneratedQuestion(title="How are decisions made", body="B", confidence=0.7),
        GeneratedQuestion(title="How are decisions made!", body="C", confidence=0.6),
    ]
    result = await dedup.dedup(questions)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_exact_dedup_normalizes_whitespace():
    dedup = ExactDedup()
    questions = [
        GeneratedQuestion(title="How are decisions made", body="A", confidence=0.9),
        GeneratedQuestion(title="  How  are   decisions  made  ", body="B", confidence=0.7),
    ]
    result = await dedup.dedup(questions)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_exact_dedup_all_unique():
    dedup = ExactDedup()
    questions = [
        GeneratedQuestion(title="Question one", body="A", confidence=0.9),
        GeneratedQuestion(title="Question two", body="B", confidence=0.8),
        GeneratedQuestion(title="Question three", body="C", confidence=0.7),
    ]
    result = await dedup.dedup(questions)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_exact_dedup_empty_input():
    dedup = ExactDedup()
    result = await dedup.dedup([])
    assert result == []


def test_normalize():
    assert _normalize("Hello World?") == "hello world"
    assert _normalize("  Extra   Spaces  ") == "extra spaces"
    assert _normalize("Punctuation!?.,;:-") == "punctuation"
    assert _normalize('"Quoted"') == "quoted"


# --- LLMDedup ---


@pytest.mark.asyncio
async def test_llm_dedup_removes_semantic_duplicates():
    mock_llm = AsyncMock(
        return_value=DedupResult(is_duplicate=True, confidence=0.95, reason="Same question")
    )
    dedup = LLMDedup(threshold=0.85)
    questions = [
        GeneratedQuestion(
            title="How are decisions made?", body="A", category="Authority", confidence=0.9
        ),
        GeneratedQuestion(
            title="What is the decision-making process?",
            body="B",
            category="Authority",
            confidence=0.7,
        ),
    ]
    with patch("pipeline.dedup.llm_dedup.call_llm", mock_llm):
        result = await dedup.dedup(questions)
    assert len(result) == 1
    assert result[0].confidence == 0.9  # higher confidence kept


@pytest.mark.asyncio
async def test_llm_dedup_keeps_non_duplicates():
    mock_llm = AsyncMock(
        return_value=DedupResult(is_duplicate=False, confidence=0.2, reason="Different topics")
    )
    dedup = LLMDedup(threshold=0.85)
    questions = [
        GeneratedQuestion(
            title="How are decisions made?", body="A", category="Authority", confidence=0.9
        ),
        GeneratedQuestion(
            title="What is the vacation policy?",
            body="B",
            category="Authority",
            confidence=0.8,
        ),
    ]
    with patch("pipeline.dedup.llm_dedup.call_llm", mock_llm):
        result = await dedup.dedup(questions)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_llm_dedup_respects_threshold():
    mock_llm = AsyncMock(
        return_value=DedupResult(is_duplicate=True, confidence=0.6, reason="Somewhat similar")
    )
    dedup = LLMDedup(threshold=0.85)
    questions = [
        GeneratedQuestion(
            title="How are decisions made?", body="A", category="Authority", confidence=0.9
        ),
        GeneratedQuestion(
            title="Decision process?", body="B", category="Authority", confidence=0.7
        ),
    ]
    with patch("pipeline.dedup.llm_dedup.call_llm", mock_llm):
        result = await dedup.dedup(questions)
    # Confidence 0.6 < threshold 0.85, so both kept
    assert len(result) == 2


@pytest.mark.asyncio
async def test_llm_dedup_empty_input():
    dedup = LLMDedup()
    result = await dedup.dedup([])
    assert result == []


@pytest.mark.asyncio
async def test_llm_dedup_single_item():
    dedup = LLMDedup()
    questions = [GeneratedQuestion(title="Only one", body="Body", confidence=0.9)]
    result = await dedup.dedup(questions)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_llm_dedup_different_categories_not_compared():
    """Questions in different categories should not be compared."""
    mock_llm = AsyncMock(
        return_value=DedupResult(is_duplicate=True, confidence=0.99, reason="Identical")
    )
    dedup = LLMDedup(threshold=0.85)
    questions = [
        GeneratedQuestion(
            title="How are decisions made?", body="A", category="Authority", confidence=0.9
        ),
        GeneratedQuestion(
            title="How are decisions made?", body="A", category="Culture", confidence=0.9
        ),
    ]
    with patch("pipeline.dedup.llm_dedup.call_llm", mock_llm):
        result = await dedup.dedup(questions)
    # Different categories — LLM not called for cross-category pairs
    mock_llm.assert_not_called()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_llm_dedup_removes_lower_confidence():
    """When duplicates found, the lower-confidence question is removed."""
    mock_llm = AsyncMock(
        return_value=DedupResult(is_duplicate=True, confidence=0.95, reason="Same")
    )
    dedup = LLMDedup(threshold=0.85)
    questions = [
        GeneratedQuestion(
            title="Q1", body="A", category="Cat", confidence=0.5
        ),
        GeneratedQuestion(
            title="Q2", body="B", category="Cat", confidence=0.9
        ),
    ]
    with patch("pipeline.dedup.llm_dedup.call_llm", mock_llm):
        result = await dedup.dedup(questions)
    assert len(result) == 1
    assert result[0].confidence == 0.9  # higher confidence kept
