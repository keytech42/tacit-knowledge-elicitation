"""Tests for respondent recommendation — strategy dispatch, LLM path, embedding path."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.recommendation import (
    _build_candidate_context,
    _resolve_strategy,
    recommend_respondents,
)
from tests.conftest import auth_header

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Strategy resolution
# ---------------------------------------------------------------------------


class TestResolveStrategy:
    def test_explicit_llm(self):
        with patch("app.services.recommendation.settings") as mock:
            mock.RECOMMENDATION_STRATEGY = "llm"
            assert _resolve_strategy() == "llm"

    def test_explicit_embedding(self):
        with patch("app.services.recommendation.settings") as mock:
            mock.RECOMMENDATION_STRATEGY = "embedding"
            assert _resolve_strategy() == "embedding"

    def test_auto_with_embedding_model(self):
        with patch("app.services.recommendation.settings") as mock:
            mock.RECOMMENDATION_STRATEGY = "auto"
            mock.EMBEDDING_MODEL = "openai/bge-m3"
            assert _resolve_strategy() == "embedding"

    def test_auto_without_embedding_model(self):
        with patch("app.services.recommendation.settings") as mock:
            mock.RECOMMENDATION_STRATEGY = "auto"
            mock.EMBEDDING_MODEL = ""
            assert _resolve_strategy() == "llm"


# ---------------------------------------------------------------------------
# LLM recommendation path
# ---------------------------------------------------------------------------


class TestLLMRecommendation:
    async def test_llm_requires_worker_url(self, db):
        """LLM strategy returns helpful message when WORKER_URL not set."""
        qid = uuid.uuid4()
        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings:
            mock_settings.WORKER_URL = ""
            result = await recommend_respondents(db, qid)
        assert result["items"] == []
        assert "WORKER_URL" in result["reason"]

    async def test_llm_question_not_found(self, db):
        """LLM strategy returns empty for nonexistent question."""
        qid = uuid.uuid4()
        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings:
            mock_settings.WORKER_URL = "http://worker:8001"
            result = await recommend_respondents(db, qid)
        assert result["items"] == []
        assert "not found" in result["reason"].lower()

    async def test_llm_worker_failure_returns_error(self, db, admin_user, respondent_user):
        """When worker doesn't respond, return helpful error."""
        from app.models.answer import Answer
        from app.models.question import Question

        q = Question(title="Test Q", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        a = Answer(body="An answer", question_id=q.id, author_id=respondent_user.id, status="approved")
        db.add(a)
        await db.flush()

        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings, \
             patch("app.services.worker_client.trigger_recommend", new_callable=AsyncMock, return_value=None):
            mock_settings.WORKER_URL = "http://worker:8001"
            result = await recommend_respondents(db, q.id)
        assert result["items"] == []
        assert "did not respond" in result["reason"].lower()

    async def test_llm_returns_worker_results(self, db, admin_user, respondent_user):
        """Worker results are passed through."""
        from app.models.answer import Answer
        from app.models.question import Question

        q = Question(title="Test Q", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        a = Answer(body="An answer", question_id=q.id, author_id=respondent_user.id, status="approved")
        db.add(a)
        await db.flush()

        worker_result = {
            "items": [
                {"user_id": str(uuid.uuid4()), "display_name": "Alice", "score": 0.9, "reasoning": "expert"},
            ],
            "reason": None,
        }

        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings, \
             patch("app.services.worker_client.trigger_recommend", new_callable=AsyncMock, return_value=worker_result):
            mock_settings.WORKER_URL = "http://worker:8001"
            result = await recommend_respondents(db, q.id)
        assert len(result["items"]) == 1
        assert result["items"][0]["display_name"] == "Alice"

    async def test_llm_no_candidates(self, db, admin_user):
        """LLM strategy returns empty when no candidates with answers exist."""
        from app.models.question import Question

        q = Question(title="Test Q", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        await db.refresh(q)

        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings:
            mock_settings.WORKER_URL = "http://worker:8001"
            result = await recommend_respondents(db, q.id)
        assert result["items"] == []
        assert "no respondents" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Build candidate context
# ---------------------------------------------------------------------------


class TestBuildCandidateContext:
    async def test_returns_none_for_missing_question(self, db):
        q, candidates = await _build_candidate_context(db, uuid.uuid4())
        assert q is None
        assert candidates == []

    async def test_returns_question_and_empty_candidates(self, db, admin_user):
        from app.models.question import Question

        q = Question(title="Test", body="Body", status="draft", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        await db.refresh(q)

        q_dict, candidates = await _build_candidate_context(db, q.id)
        assert q_dict["title"] == "Test"
        assert candidates == []

    async def test_builds_candidate_profiles(self, db, admin_user, respondent_user):
        from app.models.answer import Answer
        from app.models.question import Question

        q = Question(title="Test Q", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()

        a = Answer(body="My answer", question_id=q.id, author_id=respondent_user.id, status="approved")
        db.add(a)
        await db.flush()

        q_dict, candidates = await _build_candidate_context(db, q.id)
        assert q_dict is not None
        assert len(candidates) == 1
        assert candidates[0]["user_id"] == str(respondent_user.id)
        assert len(candidates[0]["answer_summaries"]) == 1
        assert candidates[0]["answer_summaries"][0]["status"] == "approved"


# ---------------------------------------------------------------------------
# Embedding recommendation path (existing behavior)
# ---------------------------------------------------------------------------


class TestEmbeddingRecommendation:
    async def test_embedding_missing_question(self, db):
        with patch("app.services.recommendation._resolve_strategy", return_value="embedding"):
            result = await recommend_respondents(db, uuid.uuid4())
        assert result["items"] == []
        assert "not found" in result["reason"].lower()

    async def test_embedding_no_embedding_on_question(self, db, admin_user):
        from app.models.question import Question

        q = Question(title="Test", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        await db.refresh(q)

        with patch("app.services.recommendation._resolve_strategy", return_value="embedding"):
            result = await recommend_respondents(db, q.id)
        assert result["items"] == []
        assert "no embedding" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Unknown strategy
# ---------------------------------------------------------------------------


class TestUnknownStrategy:
    async def test_unknown_strategy_returns_error(self, db):
        with patch("app.services.recommendation._resolve_strategy", return_value="quantum"):
            result = await recommend_respondents(db, uuid.uuid4())
        assert result["items"] == []
        assert "Unknown strategy" in result["reason"]


# ---------------------------------------------------------------------------
# Endpoint integration
# ---------------------------------------------------------------------------


class TestRecommendEndpoint:
    async def test_recommend_with_llm_strategy(self, client, admin_user, respondent_user, db):
        """End-to-end: endpoint → LLM strategy → mocked worker."""
        from app.models.answer import Answer
        from app.models.question import Question

        q = Question(title="Test Q", body="Body", status="published", created_by_id=admin_user.id)
        db.add(q)
        await db.flush()
        a = Answer(body="An answer", question_id=q.id, author_id=respondent_user.id, status="approved")
        db.add(a)
        await db.flush()

        worker_result = {
            "items": [
                {"user_id": str(uuid.uuid4()), "display_name": "Bob", "score": 0.85, "reasoning": "domain expert"},
            ],
            "reason": None,
        }

        with patch("app.services.recommendation._resolve_strategy", return_value="llm"), \
             patch("app.services.recommendation.settings") as mock_settings, \
             patch("app.services.worker_client.trigger_recommend", new_callable=AsyncMock, return_value=worker_result):
            mock_settings.WORKER_URL = "http://worker:8001"
            resp = await client.post(
                "/api/v1/ai/recommend",
                json={"question_id": str(q.id)},
                headers=auth_header(admin_user),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["display_name"] == "Bob"
