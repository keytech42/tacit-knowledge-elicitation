import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


@pytest.mark.asyncio
class TestAdminQueueEndpoint:
    """Tests for GET /api/v1/questions/admin-queue"""

    async def test_returns_grouped_questions(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        """Admin queue returns questions grouped by actionable status."""
        proposed = Question(title="Proposed Q", body="B", created_by_id=author_user.id, status=QuestionStatus.PROPOSED.value)
        in_review = Question(title="Review Q", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        published = Question(title="Published Q", body="B", created_by_id=author_user.id, status=QuestionStatus.PUBLISHED.value)
        closed = Question(title="Closed Q", body="B", created_by_id=author_user.id, status=QuestionStatus.CLOSED.value)
        # Draft and archived should NOT appear
        draft = Question(title="Draft Q", body="B", created_by_id=author_user.id, status=QuestionStatus.DRAFT.value)
        archived = Question(title="Archived Q", body="B", created_by_id=author_user.id, status=QuestionStatus.ARCHIVED.value)
        db.add_all([proposed, in_review, published, closed, draft, archived])
        await db.flush()

        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()

        assert len(data["proposed"]) == 1
        assert data["proposed"][0]["title"] == "Proposed Q"
        assert len(data["in_review"]) == 1
        assert data["in_review"][0]["title"] == "Review Q"
        assert len(data["published"]) == 1
        assert data["published"][0]["title"] == "Published Q"
        assert len(data["closed"]) == 1
        assert data["closed"][0]["title"] == "Closed Q"

    async def test_includes_answer_counts(self, client: AsyncClient, admin_user: User, author_user: User, respondent_user: User, db: AsyncSession):
        """Each queue item includes the number of answers for that question."""
        q = Question(title="Q with answers", body="B", created_by_id=author_user.id, status=QuestionStatus.PROPOSED.value)
        db.add(q)
        await db.flush()

        a1 = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer 1", status=AnswerStatus.DRAFT.value)
        a2 = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer 2", status=AnswerStatus.SUBMITTED.value)
        db.add_all([a1, a2])
        await db.flush()

        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["proposed"][0]["answer_count"] == 2

    async def test_zero_answers(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        """Questions with no answers show answer_count=0."""
        q = Question(title="No answers", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["in_review"][0]["answer_count"] == 0

    async def test_empty_queue(self, client: AsyncClient, admin_user: User, db: AsyncSession):
        """Returns empty lists when no questions are in actionable states."""
        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert data["proposed"] == []
        assert data["in_review"] == []
        assert data["published"] == []
        assert data["closed"] == []

    async def test_includes_created_by(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        """Queue items include author info."""
        q = Question(title="Author test", body="B", created_by_id=author_user.id, status=QuestionStatus.PROPOSED.value)
        db.add(q)
        await db.flush()

        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        item = r.json()["proposed"][0]
        assert item["created_by"]["display_name"] == "Author User"
        assert item["created_by"]["id"] == str(author_user.id)


@pytest.mark.asyncio
class TestAdminQueuePermissions:
    """Non-admin users must not access the admin queue."""

    async def test_author_forbidden(self, client: AsyncClient, author_user: User):
        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_respondent_forbidden(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_reviewer_forbidden(self, client: AsyncClient, reviewer_user: User):
        r = await client.get("/api/v1/questions/admin-queue", headers=auth_header(reviewer_user))
        assert r.status_code == 403

    async def test_unauthenticated_forbidden(self, client: AsyncClient):
        r = await client.get("/api/v1/questions/admin-queue")
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestAdminQueueWorkflowActions:
    """Test that workflow actions work correctly from the admin queue context
    (proposed→in_review, in_review→published, in_review→draft, published→closed, closed→archived)."""

    async def test_start_review_from_proposed(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Start review", body="B", created_by_id=author_user.id, status=QuestionStatus.PROPOSED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/start-review", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "in_review"

        # Verify it moved buckets in the queue
        queue = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        assert any(item["id"] == str(q.id) for item in queue.json()["in_review"])
        assert not any(item["id"] == str(q.id) for item in queue.json()["proposed"])

    async def test_publish_from_in_review(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Publish", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "published"
        assert r.json()["confirmed_by"]["id"] == str(admin_user.id)
        assert r.json()["published_at"] is not None

    async def test_reject_from_in_review(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Reject", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/reject", json={"comment": "Needs more detail"}, headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "draft"
        assert r.json()["confirmation"] == "rejected"

        # Should disappear from the queue entirely (draft is not actionable)
        queue = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        all_ids = []
        for bucket in ["proposed", "in_review", "published", "closed"]:
            all_ids.extend(item["id"] for item in queue.json()[bucket])
        assert str(q.id) not in all_ids

    async def test_reject_without_comment(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Reject no comment", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/reject", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "draft"

    async def test_close_from_published(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Close", body="B", created_by_id=author_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

    async def test_archive_from_closed(self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession):
        q = Question(title="Archive", body="B", created_by_id=author_user.id, status=QuestionStatus.CLOSED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/archive", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

        # Archived should not appear in queue
        queue = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        all_ids = []
        for bucket in ["proposed", "in_review", "published", "closed"]:
            all_ids.extend(item["id"] for item in queue.json()[bucket])
        assert str(q.id) not in all_ids

    async def test_non_admin_cannot_start_review(self, client: AsyncClient, author_user: User, db: AsyncSession):
        q = Question(title="No perms", body="B", created_by_id=author_user.id, status=QuestionStatus.PROPOSED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/start-review", headers=auth_header(author_user))
        assert r.status_code == 403
