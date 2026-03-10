"""Tests for async AI task engine — persistent task tracking and cancellation."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.ai_task import AITask, AITaskType, AITaskStatus
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_aitasktype_values_are_lowercase():
    for member in AITaskType:
        assert member.value == member.value.lower(), f"{member.name} has non-lowercase value"


@pytest.mark.asyncio
async def test_aitaskstatus_values_are_lowercase():
    for member in AITaskStatus:
        assert member.value == member.value.lower(), f"{member.name} has non-lowercase value"


@pytest.mark.asyncio
async def test_generate_questions_creates_ai_task(client, db, admin_user):
    with patch("app.services.worker_client.trigger_generate_questions", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = {"task_id": "worker-123", "status": "accepted"}

        resp = await client.post("/api/v1/ai/generate-questions", json={
            "topic": "Test topic",
            "domain": "testing",
            "count": 2,
        }, headers=auth_header(admin_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_type"] == "generate_questions"
    assert data["status"] == "running"
    assert data["worker_task_id"] == "worker-123"

    # Verify DB row
    result = await db.execute(select(AITask).where(AITask.id == uuid.UUID(data["id"])))
    task = result.scalar_one()
    assert task.user_id == admin_user.id
    assert task.task_type == AITaskType.GENERATE_QUESTIONS


@pytest.mark.asyncio
async def test_scaffold_options_creates_ai_task(client, db, admin_user):
    question_id = str(uuid.uuid4())
    with patch("app.services.worker_client.trigger_scaffold_options", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = {"task_id": "worker-456", "status": "accepted"}

        resp = await client.post("/api/v1/ai/scaffold-options", json={
            "question_id": question_id,
            "num_options": 3,
        }, headers=auth_header(admin_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_type"] == "scaffold_options"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_review_assist_creates_ai_task(client, db, admin_user):
    answer_id = str(uuid.uuid4())
    with patch("app.services.worker_client.trigger_review_assist", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = {"task_id": "worker-789", "status": "accepted"}

        resp = await client.post("/api/v1/ai/review-assist", json={
            "answer_id": answer_id,
        }, headers=auth_header(admin_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_type"] == "review_assist"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_worker_failure_marks_task_failed(client, db, admin_user):
    with patch("app.services.worker_client.trigger_generate_questions", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = None  # Worker didn't respond

        resp = await client.post("/api/v1/ai/generate-questions", json={
            "topic": "Test topic",
        }, headers=auth_header(admin_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"] == "Worker did not respond"
    assert data["worker_task_id"] is None


@pytest.mark.asyncio
async def test_list_tasks(client, db, admin_user):
    # Create some tasks directly in DB
    for i, task_type in enumerate([AITaskType.GENERATE_QUESTIONS, AITaskType.SCAFFOLD_OPTIONS]):
        task = AITask(
            task_type=task_type,
            status=AITaskStatus.COMPLETED if i == 0 else AITaskStatus.RUNNING,
            user_id=admin_user.id,
            worker_task_id=f"worker-{i}",
        )
        db.add(task)
    await db.flush()

    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(admin_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client, db, admin_user):
    task_running = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
    )
    task_completed = AITask(
        task_type=AITaskType.SCAFFOLD_OPTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=admin_user.id,
    )
    db.add(task_running)
    db.add(task_completed)
    await db.flush()

    resp = await client.get(
        "/api/v1/ai/tasks?status=running",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_get_task_syncs_from_worker(client, db, admin_user):
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-sync-test",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.get_task_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = {
            "task_id": "worker-sync-test",
            "status": "completed",
            "result": {"questions": ["q1", "q2"]},
            "error": None,
        }

        resp = await client.get(
            f"/api/v1/ai/tasks/{task.id}",
            headers=auth_header(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["result"] == {"questions": ["q1", "q2"]}


@pytest.mark.asyncio
async def test_get_task_not_found(client, admin_user):
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/ai/tasks/{fake_id}",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_running_task(client, db, admin_user):
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-cancel-test",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.cancel_task", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = {"task_id": "worker-cancel-test", "status": "cancelled"}

        resp = await client.post(
            f"/api/v1/ai/tasks/{task.id}/cancel",
            headers=auth_header(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"

    # Verify DB
    await db.refresh(task)
    assert task.status == AITaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_pending_task(client, db, admin_user):
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.PENDING,
        user_id=admin_user.id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.post(
        f"/api/v1/ai/tasks/{task.id}/cancel",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_completed_task_returns_409(client, db, admin_user):
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=admin_user.id,
        result={"ok": True},
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.post(
        f"/api/v1/ai/tasks/{task.id}/cancel",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_failed_task_returns_409(client, db, admin_user):
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.FAILED,
        user_id=admin_user.id,
        error="Something went wrong",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.post(
        f"/api/v1/ai/tasks/{task.id}/cancel",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_nonexistent_task_returns_404(client, admin_user):
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/ai/tasks/{fake_id}/cancel",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tasks_require_admin(client, respondent_user):
    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(respondent_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_requires_admin(client, respondent_user):
    resp = await client.post("/api/v1/ai/generate-questions", json={
        "topic": "test",
    }, headers=auth_header(respondent_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_worker_not_configured(client, admin_user):
    with patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = ""
        resp = await client.post("/api/v1/ai/generate-questions", json={
            "topic": "test",
        }, headers=auth_header(admin_user))
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_tasks_only_shows_own_tasks(client, db, admin_user, author_user):
    """Admin should only see their own tasks, not other users' tasks."""
    # Give author_user admin role for this test
    from app.models.user import Role, RoleName
    result = await db.execute(select(Role).where(Role.name == RoleName.ADMIN.value))
    admin_role = result.scalar_one()
    await db.refresh(author_user, ["roles"])
    author_user.roles.append(admin_role)
    await db.flush()

    # Create tasks for both users
    task1 = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=admin_user.id,
    )
    task2 = AITask(
        task_type=AITaskType.SCAFFOLD_OPTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=author_user.id,
    )
    db.add(task1)
    db.add(task2)
    await db.flush()

    # admin_user should only see their task
    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(admin_user))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["task_type"] == "generate_questions"

    # author_user should only see their task
    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(author_user))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["task_type"] == "scaffold_options"
