import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus, SourceType
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import User
from tests.conftest import auth_header


@pytest.fixture
async def sample_data(db, admin_user, respondent_user, reviewer_user):
    """Create a question, answer, and review for export tests."""
    q = Question(
        title="Export Test Question",
        body="What is tacit knowledge?",
        category="philosophy",
        created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
        source_type=SourceType.MANUAL.value,
        quality_score=0.85,
    )
    db.add(q)
    await db.flush()

    a = Answer(
        question_id=q.id,
        author_id=respondent_user.id,
        body="Knowledge that is hard to articulate.",
        status=AnswerStatus.APPROVED.value,
        current_version=1,
    )
    db.add(a)
    await db.flush()

    r = Review(
        target_type=ReviewTargetType.ANSWER.value,
        target_id=a.id,
        reviewer_id=reviewer_user.id,
        verdict=ReviewVerdict.APPROVED.value,
        comment="Good answer.",
        answer_version=1,
    )
    db.add(r)
    await db.flush()

    return {"question": q, "answer": a, "review": r}


@pytest.fixture
async def pending_review_data(db, admin_user, respondent_user, reviewer_user):
    """Create data with a pending review (should be excluded from review-pairs)."""
    q = Question(
        title="Pending Review Q",
        body="Body",
        created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
    )
    db.add(q)
    await db.flush()

    a = Answer(
        question_id=q.id,
        author_id=respondent_user.id,
        body="Pending answer body",
        status=AnswerStatus.UNDER_REVIEW.value,
        current_version=1,
    )
    db.add(a)
    await db.flush()

    r = Review(
        target_type=ReviewTargetType.ANSWER.value,
        target_id=a.id,
        reviewer_id=reviewer_user.id,
        verdict=ReviewVerdict.PENDING.value,
    )
    db.add(r)
    await db.flush()

    return {"question": q, "answer": a, "review": r}


class TestExportAuth:
    """Verify admin-only access for all export endpoints."""

    @pytest.mark.asyncio
    async def test_training_data_admin_ok(self, client: AsyncClient, admin_user: User):
        resp = await client.get("/api/v1/export/training-data", headers=auth_header(admin_user))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_training_data_non_admin_forbidden(self, client: AsyncClient, author_user: User):
        resp = await client.get("/api/v1/export/training-data", headers=auth_header(author_user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_embeddings_admin_ok(self, client: AsyncClient, admin_user: User):
        resp = await client.get("/api/v1/export/embeddings", headers=auth_header(admin_user))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_embeddings_non_admin_forbidden(self, client: AsyncClient, respondent_user: User):
        resp = await client.get("/api/v1/export/embeddings", headers=auth_header(respondent_user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_review_pairs_admin_ok(self, client: AsyncClient, admin_user: User):
        resp = await client.get("/api/v1/export/review-pairs", headers=auth_header(admin_user))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_review_pairs_non_admin_forbidden(self, client: AsyncClient, reviewer_user: User):
        resp = await client.get("/api/v1/export/review-pairs", headers=auth_header(reviewer_user))
        assert resp.status_code == 403


class TestTrainingDataExport:
    @pytest.mark.asyncio
    async def test_returns_valid_jsonl(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get("/api/v1/export/training-data", headers=auth_header(admin_user))
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")

        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1

        row = json.loads(lines[0])
        assert "question_id" in row
        assert "question_title" in row
        assert "question_body" in row
        assert "answer_id" in row
        assert "answer_body" in row
        assert "review_verdicts" in row
        assert "source_type" in row
        assert "quality_score" in row

    @pytest.mark.asyncio
    async def test_includes_review_verdicts(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get("/api/v1/export/training-data", headers=auth_header(admin_user))
        lines = [line for line in resp.text.strip().split("\n") if line]
        row = json.loads(lines[0])
        assert "approved" in row["review_verdicts"]

    @pytest.mark.asyncio
    async def test_status_filter(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/training-data",
            params={"question_status": "published"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1
        for line in lines:
            row = json.loads(line)
            assert row["question_status"] == "published"

    @pytest.mark.asyncio
    async def test_status_filter_no_match(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/training-data",
            params={"question_status": "draft"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_category_filter(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/training-data",
            params={"category": "philosophy"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1
        for line in lines:
            row = json.loads(line)
            assert row["question_category"] == "philosophy"

    @pytest.mark.asyncio
    async def test_category_filter_no_match(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/training-data",
            params={"category": "nonexistent"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_date_filter(self, client: AsyncClient, admin_user: User, sample_data):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        resp = await client.get(
            "/api/v1/export/training-data",
            params={"date_from": future},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0


class TestEmbeddingsExport:
    @pytest.mark.asyncio
    async def test_no_embeddings_returns_empty(self, client: AsyncClient, admin_user: User, sample_data):
        """Questions and answers without embeddings should not appear."""
        resp = await client.get("/api/v1/export/embeddings", headers=auth_header(admin_user))
        assert resp.status_code == 200
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_with_embedding(self, client: AsyncClient, admin_user: User, db):
        """Questions with embeddings should be exported."""
        q = Question(
            title="Embedded Q",
            body="Body",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            embedding=[0.1] * 1024,
        )
        db.add(q)
        await db.flush()

        resp = await client.get(
            "/api/v1/export/embeddings",
            params={"entity_type": "question"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1
        row = json.loads(lines[0])
        assert row["entity_type"] == "question"
        assert len(row["embedding"]) == 1024

    @pytest.mark.asyncio
    async def test_entity_type_filter(self, client: AsyncClient, admin_user: User, respondent_user: User, db):
        """entity_type=answer should only return answers."""
        q = Question(
            title="Q with embedding",
            body="Body",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            embedding=[0.2] * 1024,
        )
        db.add(q)
        await db.flush()

        a = Answer(
            question_id=q.id,
            author_id=respondent_user.id,
            body="Answer with embedding",
            status=AnswerStatus.SUBMITTED.value,
            embedding=[0.3] * 1024,
        )
        db.add(a)
        await db.flush()

        resp = await client.get(
            "/api/v1/export/embeddings",
            params={"entity_type": "answer"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1
        for line in lines:
            row = json.loads(line)
            assert row["entity_type"] == "answer"


class TestReviewPairsExport:
    @pytest.mark.asyncio
    async def test_returns_valid_jsonl(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get("/api/v1/export/review-pairs", headers=auth_header(admin_user))
        assert resp.status_code == 200

        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1

        row = json.loads(lines[0])
        assert "answer_id" in row
        assert "question_id" in row
        assert "question_title" in row
        assert "answer_body" in row
        assert "review_verdict" in row
        assert "review_comment" in row
        assert "reviewer_id" in row

    @pytest.mark.asyncio
    async def test_excludes_pending_reviews(self, client: AsyncClient, admin_user: User, pending_review_data):
        resp = await client.get("/api/v1/export/review-pairs", headers=auth_header(admin_user))
        lines = [line for line in resp.text.strip().split("\n") if line]
        for line in lines:
            row = json.loads(line)
            assert row["review_verdict"] != "pending"

    @pytest.mark.asyncio
    async def test_verdict_filter(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/review-pairs",
            params={"verdict": "approved"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) >= 1
        for line in lines:
            row = json.loads(line)
            assert row["review_verdict"] == "approved"

    @pytest.mark.asyncio
    async def test_verdict_filter_no_match(self, client: AsyncClient, admin_user: User, sample_data):
        resp = await client.get(
            "/api/v1/export/review-pairs",
            params={"verdict": "rejected"},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        # sample_data only has approved verdict
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_date_filter(self, client: AsyncClient, admin_user: User, sample_data):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        resp = await client.get(
            "/api/v1/export/review-pairs",
            params={"date_from": future},
            headers=auth_header(admin_user),
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0
