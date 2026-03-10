"""Tests for multi-respondent pool with optimistic concurrency."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


pytestmark = pytest.mark.asyncio


async def _make_published_question(db: AsyncSession, admin_user: User) -> Question:
    q = Question(
        title="Pool Test Q", body="Body",
        created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
    )
    db.add(q)
    await db.flush()
    return q


class TestUpdateRespondentPool:

    async def test_add_single_respondent(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["respondents"]) == 1
        assert data["respondents"][0]["user"]["id"] == str(respondent_user.id)
        assert data["version"] == 1

    async def test_add_multiple_respondents(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, author_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        user_ids = [str(respondent_user.id), str(reviewer_user.id), str(author_user.id)]
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": user_ids, "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["respondents"]) == 3
        assert data["version"] == 1

    async def test_replace_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r1 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        r2 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(reviewer_user.id)], "expected_version": 1},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        data = r2.json()
        assert len(data["respondents"]) == 1
        assert data["respondents"][0]["user"]["id"] == str(reviewer_user.id)
        assert data["version"] == 2

    async def test_empty_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r1 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        r2 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [], "expected_version": 1},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        assert len(r2.json()["respondents"]) == 0
        assert r2.json()["version"] == 2


class TestOptimisticConcurrency:

    async def test_version_mismatch_returns_409(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r1 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        r2 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 409

    async def test_version_increments(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        for version in range(3):
            r = await client.put(
                f"/api/v1/questions/{q.id}/respondents",
                json={"user_ids": [str(respondent_user.id)], "expected_version": version},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            assert r.json()["version"] == version + 1


class TestGetRespondentPool:

    async def test_get_empty_pool(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.get(
            f"/api/v1/questions/{q.id}/respondents",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["respondents"] == []
        assert data["version"] == 0

    async def test_get_populated_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        r = await client.get(
            f"/api/v1/questions/{q.id}/respondents",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["respondents"]) == 1
        assert data["respondents"][0]["user"]["id"] == str(respondent_user.id)
        assert data["version"] == 1

    async def test_get_pool_question_not_found(
        self, client: AsyncClient, admin_user: User,
    ):
        r = await client.get(
            f"/api/v1/questions/{uuid.uuid4()}/respondents",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 404


class TestRespondentPoolValidation:

    async def test_exceed_max_respondents(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        fake_ids = [str(uuid.uuid4()) for _ in range(6)]
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": fake_ids, "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 400

    async def test_duplicate_user_ids(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={
                "user_ids": [str(respondent_user.id), str(respondent_user.id)],
                "expected_version": 0,
            },
            headers=auth_header(admin_user),
        )
        assert r.status_code == 400

    async def test_nonexistent_user_id(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(uuid.uuid4())], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 404

    async def test_not_published_question(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = Question(
            title="Draft Q", body="Body",
            created_by_id=admin_user.id,
            status=QuestionStatus.DRAFT.value,
        )
        db.add(q)
        await db.flush()
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 409


class TestRespondentPoolPermissions:

    async def test_author_forbidden(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(author_user),
        )
        assert r.status_code == 403

    async def test_respondent_forbidden(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient):
        r = await client.put(
            f"/api/v1/questions/{uuid.uuid4()}/respondents",
            json={"user_ids": [], "expected_version": 0},
        )
        assert r.status_code in (401, 403)


class TestPoolClearedOnClose:

    async def test_close_clears_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r1 = await client.put(
            f"/api/v1/questions/{q.id}/respondents",
            json={"user_ids": [str(respondent_user.id)], "expected_version": 0},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        assert len(r1.json()["respondents"]) == 1
        r2 = await client.post(
            f"/api/v1/questions/{q.id}/close",
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        assert r2.json()["assigned_respondents"] == []


class TestBackwardCompat:

    async def test_single_assign_adds_to_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assigned_respondent"]["id"] == str(respondent_user.id)
        assert len(data["assigned_respondents"]) == 1
        assert data["assigned_respondents"][0]["user"]["id"] == str(respondent_user.id)
        assert data["respondent_pool_version"] == 1

    async def test_single_assign_idempotent_in_pool(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r1 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 200
        assert len(r1.json()["assigned_respondents"]) == 1
        r2 = await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 200
        assert len(r2.json()["assigned_respondents"]) == 1
        assert r2.json()["respondent_pool_version"] == 1


class TestQuestionResponseSchema:

    async def test_question_response_includes_pool_fields(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        q = await _make_published_question(db, admin_user)
        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert "assigned_respondents" in data
        assert "respondent_pool_version" in data
        assert data["assigned_respondents"] == []
        assert data["respondent_pool_version"] == 0
