from httpx import AsyncClient

from app.models.user import User
from tests.conftest import auth_header


class TestPermissions:
    async def test_respondent_cannot_create_question(self, client: AsyncClient, respondent_user: User):
        r = await client.post("/api/v1/questions", json={"title": "T", "body": "B"}, headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_respondent_cannot_list_users(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/users", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_respondent_cannot_list_service_accounts(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/service-accounts", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_respondent_cannot_list_ai_logs(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/ai-logs", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_author_cannot_publish(self, client: AsyncClient, author_user: User, db):
        from app.models.question import Question, QuestionStatus
        q = Question(title="T", body="B", created_by_id=author_user.id, status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()
        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_admin_can_do_everything(self, client: AsyncClient, admin_user: User):
        r = await client.get("/api/v1/users", headers=auth_header(admin_user))
        assert r.status_code == 200
        r = await client.get("/api/v1/service-accounts", headers=auth_header(admin_user))
        assert r.status_code == 200
        r = await client.get("/api/v1/ai-logs", headers=auth_header(admin_user))
        assert r.status_code == 200
