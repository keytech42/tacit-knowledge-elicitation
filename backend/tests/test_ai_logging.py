from httpx import AsyncClient

from app.models.ai_log import AIInteractionLog
from app.models.user import User
from tests.conftest import auth_header


class TestAILogEndpoints:
    async def test_list_ai_logs(self, client: AsyncClient, admin_user: User, service_user: tuple[User, str], db):
        svc_user, _ = service_user
        log = AIInteractionLog(
            service_user_id=svc_user.id, model_id="claude-sonnet", endpoint="POST /api/v1/questions",
            request_body={"title": "Test"}, response_status=201,
        )
        db.add(log)
        await db.flush()

        r = await client.get("/api/v1/ai-logs", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_submit_feedback(self, client: AsyncClient, admin_user: User, service_user: tuple[User, str], db):
        svc_user, _ = service_user
        log = AIInteractionLog(
            service_user_id=svc_user.id, endpoint="POST /api/v1/questions",
            request_body={}, response_status=201,
        )
        db.add(log)
        await db.flush()

        r = await client.post(f"/api/v1/ai-logs/{log.id}/feedback", json={"rating": 4, "comment": "Good"}, headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["feedback_rating"] == 4
        assert r.json()["feedback_comment"] == "Good"

    async def test_non_admin_cannot_list_logs(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/ai-logs", headers=auth_header(respondent_user))
        assert r.status_code == 403
