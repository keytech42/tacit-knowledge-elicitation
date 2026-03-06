"""Tests for answer options endpoints: CREATE, LIST, DELETE, and show_suggestions visibility."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import AnswerOption, Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_question(db: AsyncSession, user: User, **overrides) -> Question:
    """Insert a question directly in the DB and return it."""
    defaults = dict(title="Test Q", body="Body", created_by_id=user.id)
    defaults.update(overrides)
    q = Question(**defaults)
    db.add(q)
    await db.flush()
    await db.refresh(q)
    return q


async def _publish_question(
    client: AsyncClient, db: AsyncSession, author: User, admin: User,
) -> Question:
    """Create a question and advance it through the lifecycle to published."""
    q = await _create_question(db, author)
    await client.post(f"/api/v1/questions/{q.id}/submit", headers=auth_header(author))
    await client.post(f"/api/v1/questions/{q.id}/start-review", headers=auth_header(admin))
    await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin))
    await db.refresh(q)
    return q


async def _create_options_via_api(
    client: AsyncClient, question_id: uuid.UUID, user: User, count: int = 2,
) -> list[dict]:
    """Create answer options through the API and return the response JSON."""
    options = [{"body": f"Option {i}", "display_order": i} for i in range(count)]
    resp = await client.post(
        f"/api/v1/questions/{question_id}/options",
        json={"options": options},
        headers=auth_header(user),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# DELETE /questions/{id}/options
# ---------------------------------------------------------------------------

class TestDeleteAnswerOptions:
    async def test_admin_can_delete_options(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        await _create_options_via_api(client, q.id, admin_user, count=3)

        # Verify options exist
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        assert len(r.json()) == 3

        # Delete all options
        r = await client.delete(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Verify options are gone
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        assert r.json() == []

    async def test_author_can_delete_options(
        self, client: AsyncClient, author_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, author_user)
        await _create_options_via_api(client, q.id, author_user)

        r = await client.delete(f"/api/v1/questions/{q.id}/options", headers=auth_header(author_user))
        assert r.status_code == 204

        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(author_user))
        assert r.json() == []

    async def test_respondent_cannot_delete_options(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        await _create_options_via_api(client, q.id, admin_user)

        r = await client.delete(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_delete_returns_404_for_nonexistent_question(
        self, client: AsyncClient, admin_user: User,
    ):
        fake_id = uuid.uuid4()
        r = await client.delete(f"/api/v1/questions/{fake_id}/options", headers=auth_header(admin_user))
        assert r.status_code == 404

    async def test_delete_is_idempotent(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Deleting options when there are none still returns 204."""
        q = await _create_question(db, admin_user)
        r = await client.delete(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        assert r.status_code == 204


# ---------------------------------------------------------------------------
# POST /questions/{id}/options
# ---------------------------------------------------------------------------

class TestCreateAnswerOptions:
    async def test_admin_can_create_options(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        data = await _create_options_via_api(client, q.id, admin_user, count=2)
        assert len(data) == 2
        assert data[0]["body"] == "Option 0"
        assert data[1]["body"] == "Option 1"

    async def test_author_can_create_options(
        self, client: AsyncClient, author_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, author_user)
        data = await _create_options_via_api(client, q.id, author_user, count=2)
        assert len(data) == 2

    async def test_options_have_correct_display_order(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        options = [
            {"body": "Third", "display_order": 2},
            {"body": "First", "display_order": 0},
            {"body": "Second", "display_order": 1},
        ]
        resp = await client.post(
            f"/api/v1/questions/{q.id}/options",
            json={"options": options},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data[0]["display_order"] == 2
        assert data[1]["display_order"] == 0
        assert data[2]["display_order"] == 1

        # GET returns sorted by display_order
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        ordered = r.json()
        assert ordered[0]["body"] == "First"
        assert ordered[1]["body"] == "Second"
        assert ordered[2]["body"] == "Third"

    async def test_can_create_more_than_four_options(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """The API has no cap on option count; the cap is in the worker."""
        q = await _create_question(db, admin_user)
        data = await _create_options_via_api(client, q.id, admin_user, count=6)
        assert len(data) == 6

    async def test_respondent_cannot_create_options(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        resp = await client.post(
            f"/api/v1/questions/{q.id}/options",
            json={"options": [{"body": "Nope", "display_order": 0}]},
            headers=auth_header(respondent_user),
        )
        assert resp.status_code == 403

    async def test_create_options_404_for_nonexistent_question(
        self, client: AsyncClient, admin_user: User,
    ):
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/questions/{fake_id}/options",
            json={"options": [{"body": "X", "display_order": 0}]},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /questions/{id}/options  (visibility / show_suggestions)
# ---------------------------------------------------------------------------

class TestListAnswerOptions:
    async def test_admin_sees_options_regardless_of_show_suggestions(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user, show_suggestions=False)
        await _create_options_via_api(client, q.id, admin_user, count=2)

        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_author_sees_options_regardless_of_show_suggestions(
        self, client: AsyncClient, author_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, author_user, show_suggestions=False)
        await _create_options_via_api(client, q.id, author_user, count=2)

        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(author_user))
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_respondent_sees_options_when_show_suggestions_true(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _create_question(
            db, admin_user, show_suggestions=True, status=QuestionStatus.PUBLISHED.value,
        )
        await _create_options_via_api(client, q.id, admin_user, count=2)

        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_respondent_gets_empty_list_when_show_suggestions_false(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _create_question(
            db, admin_user, show_suggestions=False, status=QuestionStatus.PUBLISHED.value,
        )
        await _create_options_via_api(client, q.id, admin_user, count=2)

        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# show_suggestions flag via PATCH
# ---------------------------------------------------------------------------

class TestShowSuggestionsFlag:
    async def test_default_show_suggestions_is_false(
        self, client: AsyncClient, author_user: User,
    ):
        resp = await client.post(
            "/api/v1/questions",
            json={"title": "Default flag test", "body": "B"},
            headers=auth_header(author_user),
        )
        assert resp.status_code == 201
        assert resp.json()["show_suggestions"] is False

    async def test_patch_show_suggestions_true(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _create_question(
            db, admin_user, show_suggestions=False, status=QuestionStatus.PUBLISHED.value,
        )
        await _create_options_via_api(client, q.id, admin_user, count=2)

        # Respondent cannot see options yet
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert r.json() == []

        # Admin flips show_suggestions on
        r = await client.patch(
            f"/api/v1/questions/{q.id}",
            json={"show_suggestions": True},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        assert r.json()["show_suggestions"] is True

        # Now respondent can see them
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert len(r.json()) == 2

    async def test_create_question_with_show_suggestions_true(
        self, client: AsyncClient, author_user: User,
    ):
        resp = await client.post(
            "/api/v1/questions",
            json={"title": "Visible", "body": "B", "show_suggestions": True},
            headers=auth_header(author_user),
        )
        assert resp.status_code == 201
        assert resp.json()["show_suggestions"] is True


# ---------------------------------------------------------------------------
# answer_options in question detail response
# ---------------------------------------------------------------------------

class TestOptionsInQuestionDetail:
    async def test_get_question_includes_answer_options(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        await _create_options_via_api(client, q.id, admin_user, count=2)

        # Expire cached relationship so the GET endpoint re-loads it
        db.expire(q, ["answer_options"])

        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert "answer_options" in data
        assert len(data["answer_options"]) == 2

    async def test_admin_sees_answer_options_when_show_suggestions_false(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user, show_suggestions=False)
        await _create_options_via_api(client, q.id, admin_user, count=2)

        # Expire cached relationship so the GET endpoint re-loads it
        db.expire(q, ["answer_options"])

        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 200
        # The question detail always returns the relationship (admin can see)
        assert len(r.json()["answer_options"]) == 2

    async def test_question_detail_empty_options_by_default(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _create_question(db, admin_user)
        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["answer_options"] == []
