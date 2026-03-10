"""Unit tests for LLM-based respondent recommendation task."""

import pytest
from unittest.mock import AsyncMock, patch

from worker.tasks.respondent_recommend import run_respondent_recommendation
from worker.schemas import RecommendationResult, RecommendedRespondent


class TestRunRespondentRecommendation:
    @pytest.mark.asyncio
    async def test_returns_ranked_respondents(self):
        """LLM results are mapped back to candidate display names."""
        question = {"title": "How to deploy?", "body": "Best practices for deploying.", "category": "devops"}
        candidates = [
            {"user_id": "u-1", "display_name": "Alice", "answer_summaries": [
                {"question_title": "CI/CD pipelines", "category": "devops", "status": "approved"},
            ]},
            {"user_id": "u-2", "display_name": "Bob", "answer_summaries": [
                {"question_title": "Database design", "category": "backend", "status": "approved"},
            ]},
        ]

        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id="u-1", score=0.9, reasoning="DevOps expert"),
            RecommendedRespondent(user_id="u-2", score=0.4, reasoning="Less relevant"),
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result):
            result = await run_respondent_recommendation(question, candidates, top_k=5)

        assert len(result["items"]) == 2
        assert result["items"][0]["display_name"] == "Alice"
        assert result["items"][0]["score"] == 0.9
        assert result["items"][1]["display_name"] == "Bob"
        assert result["reason"] is None

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        """Only top_k results are returned even if LLM returns more."""
        question = {"title": "Q", "body": "B", "category": "c"}
        candidates = [
            {"user_id": f"u-{i}", "display_name": f"User {i}", "answer_summaries": []}
            for i in range(5)
        ]

        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id=f"u-{i}", score=0.9 - i * 0.1, reasoning=f"reason {i}")
            for i in range(5)
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result):
            result = await run_respondent_recommendation(question, candidates, top_k=2)

        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        """No candidates returns empty result without calling LLM."""
        result = await run_respondent_recommendation(
            question={"title": "Q", "body": "B"},
            candidates=[],
        )
        assert result["items"] == []
        assert "no candidates" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_unknown_user_id_filtered(self):
        """LLM user_ids that don't match candidates are filtered out."""
        question = {"title": "Q", "body": "B"}
        candidates = [{"user_id": "u-1", "display_name": "Alice", "answer_summaries": []}]

        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id="u-1", score=0.8, reasoning="good"),
            RecommendedRespondent(user_id="u-unknown", score=0.9, reasoning="hallucinated"),
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result):
            result = await run_respondent_recommendation(question, candidates)

        assert len(result["items"]) == 1
        assert result["items"][0]["user_id"] == "u-1"

    @pytest.mark.asyncio
    async def test_uses_recommendation_model(self):
        """When RECOMMENDATION_MODEL is set, it's used instead of LLM_MODEL."""
        question = {"title": "Q", "body": "B"}
        candidates = [{"user_id": "u-1", "display_name": "Alice", "answer_summaries": []}]

        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id="u-1", score=0.8, reasoning="good"),
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result) as mock_llm, \
             patch("worker.tasks.respondent_recommend.settings") as mock_settings:
            mock_settings.RECOMMENDATION_MODEL = "anthropic/claude-haiku-4-5-20251001"
            mock_settings.LLM_MODEL = "anthropic/claude-sonnet-4-6"
            await run_respondent_recommendation(question, candidates)

        call_kwargs = mock_llm.call_args
        assert call_kwargs.kwargs.get("model") == "anthropic/claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_defaults_to_haiku(self):
        """Default RECOMMENDATION_MODEL is Haiku."""
        question = {"title": "Q", "body": "B"}
        candidates = [{"user_id": "u-1", "display_name": "Alice", "answer_summaries": []}]

        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id="u-1", score=0.8, reasoning="good"),
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result) as mock_llm, \
             patch("worker.tasks.respondent_recommend.settings") as mock_settings:
            mock_settings.RECOMMENDATION_MODEL = "anthropic/claude-haiku-4-5-20251001"
            mock_settings.LLM_MODEL = "anthropic/claude-sonnet-4-6"
            await run_respondent_recommendation(question, candidates)

        call_kwargs = mock_llm.call_args
        assert call_kwargs.kwargs.get("model") == "anthropic/claude-haiku-4-5-20251001"
