from httpx import AsyncClient

from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


class TestQuestionCRUD:
    async def test_create_question(self, client: AsyncClient, author_user: User):
        response = await client.post("/api/v1/questions", json={"title": "How do we handle tech debt?", "body": "Details here", "category": "tech"}, headers=auth_header(author_user))
        assert response.status_code == 201
        assert response.json()["status"] == "draft"
        assert response.json()["created_by"]["id"] == str(author_user.id)

    async def test_respondent_cannot_create(self, client: AsyncClient, respondent_user: User):
        response = await client.post("/api/v1/questions", json={"title": "T", "body": "B"}, headers=auth_header(respondent_user))
        assert response.status_code == 403

    async def test_list_questions(self, client: AsyncClient, admin_user: User, db):
        q = Question(title="Q1", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        response = await client.get("/api/v1/questions", headers=auth_header(admin_user))
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_update_question(self, client: AsyncClient, author_user: User, db):
        q = Question(title="Old", body="B", created_by_id=author_user.id)
        db.add(q)
        await db.flush()
        response = await client.patch(f"/api/v1/questions/{q.id}", json={"title": "New"}, headers=auth_header(author_user))
        assert response.status_code == 200
        assert response.json()["title"] == "New"


class TestQuestionLifecycle:
    async def test_full_lifecycle(self, client: AsyncClient, author_user: User, admin_user: User, db):
        q = Question(title="Lifecycle", body="B", created_by_id=author_user.id)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/submit", headers=auth_header(author_user))
        assert r.json()["status"] == "proposed"

        r = await client.post(f"/api/v1/questions/{q.id}/start-review", headers=auth_header(admin_user))
        assert r.json()["status"] == "in_review"

        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
        assert r.json()["status"] == "published"
        assert r.json()["confirmed_by"]["id"] == str(admin_user.id)

        r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
        assert r.json()["status"] == "closed"

        r = await client.post(f"/api/v1/questions/{q.id}/archive", headers=auth_header(admin_user))
        assert r.json()["status"] == "archived"

    async def test_reject_and_resubmit(self, client: AsyncClient, author_user: User, admin_user: User, db):
        q = Question(title="Reject", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/reject", json={"comment": "Vague"}, headers=auth_header(admin_user))
        assert r.json()["status"] == "draft"
        assert r.json()["confirmation"] == "rejected"

        r = await client.post(f"/api/v1/questions/{q.id}/submit", headers=auth_header(author_user))
        assert r.json()["status"] == "proposed"

    async def test_invalid_transition(self, client: AsyncClient, author_user: User, db):
        q = Question(title="Invalid", body="B", created_by_id=author_user.id)
        db.add(q)
        await db.flush()
        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(author_user))
        assert r.status_code in (403, 409)


class TestAnswerOptions:
    async def test_create_options(self, client: AsyncClient, author_user: User, db):
        q = Question(title="Opts", body="B", created_by_id=author_user.id)
        db.add(q)
        await db.flush()
        r = await client.post(f"/api/v1/questions/{q.id}/options", json={"options": [{"body": "A", "display_order": 0}, {"body": "B", "display_order": 1}]}, headers=auth_header(author_user))
        assert r.status_code == 201
        assert len(r.json()) == 2

    async def test_respondent_cannot_see_hidden_options(self, client: AsyncClient, author_user: User, respondent_user: User, db):
        q = Question(title="Hidden", body="B", created_by_id=author_user.id, show_suggestions=False, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        r = await client.get(f"/api/v1/questions/{q.id}/options", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json() == []
