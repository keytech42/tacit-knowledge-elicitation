"""Tests for Plan C: Respondent Assignment.

Tests cover:
1. POST /questions/{id}/assign-respondent endpoint (admin-only)
2. assigned_respondent_id FK on questions table
3. QuestionResponse schema includes assigned_respondent
4. Permission checks and edge cases

These tests are written TDD-style — they will FAIL until Plan C is implemented.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Endpoint: Assign Respondent
# ---------------------------------------------------------------------------

class TestAssignRespondentEndpoint:
    """POST /questions/{id}/assign-respondent — admin-only."""

    async def test_assign_success(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Admin can assign a respondent to a published question."""
        q = Question(
            title="Assign Test", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assigned_respondent"] is not None
        assert data["assigned_respondent"]["id"] == str(respondent_user.id)

    async def test_assign_replaces_singular_fk_and_adds_to_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Assigning a new respondent replaces the singular FK but adds both to pool."""
        q = Question(
            title="Replace Test", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # First assignment
        r1 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        assert r1.json()["assigned_respondent"]["id"] == str(respondent_user.id)
        assert len(r1.json()["assigned_respondents"]) == 1

        # Second assignment with different user
        r2 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        # Singular FK replaced
        assert r2.json()["assigned_respondent"]["id"] == str(reviewer_user.id)
        # Both users in the pool
        pool_ids = {m["user"]["id"] for m in r2.json()["assigned_respondents"]}
        assert str(respondent_user.id) in pool_ids
        assert str(reviewer_user.id) in pool_ids

    async def test_assign_same_respondent_idempotent(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Assigning the same respondent twice is idempotent (200 OK both times)."""
        q = Question(
            title="Idempotent Test", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r1 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        assert r2.json()["assigned_respondent"]["id"] == str(respondent_user.id)
        # Pool should still have only 1 member (not duplicated)
        assert len(r2.json()["assigned_respondents"]) == 1
        assert r2.json()["respondent_pool_version"] == 1


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

class TestAssignRespondentPermissions:
    """Only admins can assign respondents."""

    async def test_author_forbidden(
        self, client: AsyncClient, author_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Author role cannot assign respondents."""
        q = Question(
            title="Author Forbidden", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(author_user),
        )
        assert r.status_code == 403

    async def test_respondent_forbidden(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Respondent role cannot assign."""
        q = Question(
            title="Respondent Forbidden", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 403

    async def test_reviewer_forbidden(
        self, client: AsyncClient, admin_user: User, reviewer_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Reviewer role cannot assign."""
        q = Question(
            title="Reviewer Forbidden", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(reviewer_user),
        )
        assert r.status_code == 403

    async def test_unauthenticated_forbidden(
        self, client: AsyncClient, db: AsyncSession,
    ):
        """No auth header returns 401/403."""
        r = await client.post(
            f"/api/v1/questions/{uuid.uuid4()}/assign-respondent",
            json={"user_id": str(uuid.uuid4())},
        )
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestAssignRespondentErrors:
    """Error handling for the assign endpoint."""

    async def test_question_not_found(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Returns 404 for nonexistent question ID."""
        r = await client.post(
            f"/api/v1/questions/{uuid.uuid4()}/assign-respondent",
            json={"user_id": str(uuid.uuid4())},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 404

    async def test_user_not_found(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Returns 404 when the target user_id does not exist."""
        q = Question(
            title="User Not Found", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(uuid.uuid4())},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 404

    async def test_assign_to_draft_question(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Assignment to a draft question should fail (409 or similar)."""
        q = Question(
            title="Draft Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.DRAFT.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        # Draft questions shouldn't accept respondent assignment
        assert r.status_code in (400, 409)

    async def test_assign_to_closed_question(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Assignment to a closed question should fail."""
        q = Question(
            title="Closed Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.CLOSED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code in (400, 409)


# ---------------------------------------------------------------------------
# Schema: assigned_respondent in responses
# ---------------------------------------------------------------------------

class TestAssignedRespondentInSchema:
    """QuestionResponse should include assigned_respondent field."""

    async def test_get_question_includes_assigned_respondent_null(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Unassigned question has assigned_respondent = null and empty pool."""
        q = Question(
            title="No Assignment", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert "assigned_respondent" in data
        assert data["assigned_respondent"] is None
        assert data["assigned_respondents"] == []
        assert data["respondent_pool_version"] == 0

    async def test_get_question_includes_assigned_respondent_populated(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Assigned question has assigned_respondent with user details."""
        q = Question(
            title="With Assignment", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # Assign respondent
        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200

        # Fetch question
        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assigned_respondent"] is not None
        assert data["assigned_respondent"]["id"] == str(respondent_user.id)
        assert data["assigned_respondent"]["display_name"] == respondent_user.display_name
        assert len(data["assigned_respondents"]) == 1
        assert data["respondent_pool_version"] == 1

    async def test_question_list_includes_assigned_respondent(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """GET /questions list response includes assigned_respondent per item."""
        q = Question(
            title="List Assignment", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # Assign
        await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )

        # List
        r = await client.get(
            "/api/v1/questions",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        questions = r.json()["questions"]
        matched = [item for item in questions if item["id"] == str(q.id)]
        assert len(matched) == 1
        assert matched[0]["assigned_respondent"] is not None


# ---------------------------------------------------------------------------
# Model: assigned_respondent_id column
# ---------------------------------------------------------------------------

class TestAssignedRespondentColumn:
    """The Question model should have assigned_respondent_id FK and pool fields."""

    async def test_question_has_assigned_respondent_id(self, db: AsyncSession):
        """Questions should have a nullable assigned_respondent_id column."""
        q = Question(
            title="Column Test", body="B",
            created_by_id=uuid.uuid4(),
        )
        assert hasattr(q, "assigned_respondent_id")
        assert q.assigned_respondent_id is None

    async def test_question_has_assigned_respondent_relationship(self, db: AsyncSession):
        """Questions should have an assigned_respondent relationship."""
        q = Question(
            title="Relation Test", body="B",
            created_by_id=uuid.uuid4(),
        )
        assert hasattr(q, "assigned_respondent")

    async def test_question_has_pool_version(self, db: AsyncSession):
        """Questions should have a respondent_pool_version column defaulting to 0."""
        q = Question(
            title="Pool Version Test", body="B",
            created_by_id=uuid.uuid4(),
        )
        assert hasattr(q, "respondent_pool_version")
        # Python-side default may be None before INSERT; server_default="0" applies on flush
        assert q.respondent_pool_version in (0, None)

    async def test_question_has_assigned_respondents_relationship(self, db: AsyncSession):
        """Questions should have an assigned_respondents relationship (pool)."""
        q = Question(
            title="Pool Rel Test", body="B",
            created_by_id=uuid.uuid4(),
        )
        assert hasattr(q, "assigned_respondents")
