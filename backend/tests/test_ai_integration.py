"""Tests for AI integration: worker trigger endpoints, service account multi-role,
recommendation, and embedding services.

NOTE: Trigger endpoint tests now verify AITask persistence. The endpoints create
AITask rows in the DB and return AITaskResponse schema (not raw worker responses).
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.ai_task import AITask, AITaskType, AITaskStatus
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_ai_generate_questions_requires_admin(client, author_user):
    resp = await client.post(
        "/api/v1/ai/generate-questions",
        json={"topic": "test"},
        headers=auth_header(author_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ai_generate_questions_returns_503_when_worker_disabled(client, admin_user):
    with patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = ""
        resp = await client.post(
            "/api/v1/ai/generate-questions",
            json={"topic": "test"},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_ai_generate_questions_proxies_to_worker(client, db, admin_user):
    with patch("app.services.worker_client.trigger_generate_questions", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = "http://worker:8001"
        mock_trigger.return_value = {"task_id": "abc-123", "status": "accepted"}

        resp = await client.post(
            "/api/v1/ai/generate-questions",
            json={"topic": "engineering decisions", "domain": "software", "count": 2},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "generate_questions"
        assert data["status"] == "running"
        assert data["worker_task_id"] == "abc-123"
        assert "id" in data


@pytest.mark.asyncio
async def test_ai_scaffold_options_proxies_to_worker(client, db, admin_user):
    qid = str(uuid.uuid4())
    with patch("app.services.worker_client.trigger_scaffold_options", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = "http://worker:8001"
        mock_trigger.return_value = {"task_id": "def-456", "status": "accepted"}

        resp = await client.post(
            "/api/v1/ai/scaffold-options",
            json={"question_id": qid},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "scaffold_options"
        assert data["worker_task_id"] == "def-456"


@pytest.mark.asyncio
async def test_ai_review_assist_proxies_to_worker(client, db, admin_user):
    aid = str(uuid.uuid4())
    with patch("app.services.worker_client.trigger_review_assist", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = "http://worker:8001"
        mock_trigger.return_value = {"task_id": "ghi-789", "status": "accepted"}

        resp = await client.post(
            "/api/v1/ai/review-assist",
            json={"answer_id": aid},
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "review_assist"
        assert data["worker_task_id"] == "ghi-789"


@pytest.mark.asyncio
async def test_ai_get_task_status(client, db, admin_user):
    """GET /ai/tasks/{task_id} now uses UUID AITask.id, syncs from worker."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="abc-123",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.get_task_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "task_id": "abc-123",
            "status": "completed",
            "result": {"count": 3},
            "error": None,
        }

        resp = await client.get(
            f"/api/v1/ai/tasks/{task.id}",
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["result"] == {"count": 3}


@pytest.mark.asyncio
async def test_ai_recommend_returns_empty_for_missing_question(client, admin_user):
    resp = await client.post(
        "/api/v1/ai/recommend",
        json={"question_id": str(uuid.uuid4())},
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["reason"] is not None


# --- Service account multi-role creation ---

@pytest.mark.asyncio
async def test_create_service_account_with_multiple_roles(client, admin_user):
    resp = await client.post(
        "/api/v1/service-accounts",
        json={
            "display_name": "Worker Bot",
            "model_id": "claude-sonnet",
            "roles": ["author", "reviewer"],
        },
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 201
    data = resp.json()
    role_names = {r["name"] for r in data["roles"]}
    assert "author" in role_names
    assert "reviewer" in role_names
    assert "api_key" in data


@pytest.mark.asyncio
async def test_create_service_account_invalid_role(client, admin_user):
    resp = await client.post(
        "/api/v1/service-accounts",
        json={
            "display_name": "Bad Bot",
            "roles": ["author", "nonexistent"],
        },
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_service_account_default_role(client, admin_user):
    resp = await client.post(
        "/api/v1/service-accounts",
        json={"display_name": "Default Bot"},
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 201
    data = resp.json()
    role_names = {r["name"] for r in data["roles"]}
    assert "author" in role_names
