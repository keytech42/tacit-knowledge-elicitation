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


# ---------------------------------------------------------------------------
# Task creation via trigger endpoints
# ---------------------------------------------------------------------------


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
async def test_extract_questions_creates_source_doc_and_ai_task(client, db, admin_user):
    """Extract-questions trigger should create both a SourceDocument and an AITask."""
    with patch("app.services.worker_client.trigger_extract_questions", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = {"task_id": "worker-extract-1", "status": "accepted"}

        resp = await client.post("/api/v1/ai/extract-questions", json={
            "source_text": "Some document content for extraction.",
            "document_title": "Test Doc",
            "domain": "engineering",
            "max_questions": 5,
        }, headers=auth_header(admin_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_type"] == "extract_questions"
    assert data["status"] == "running"
    assert data["worker_task_id"] == "worker-extract-1"

    # Verify SourceDocument was created
    from app.models.source_document import SourceDocument
    result = await db.execute(select(SourceDocument).where(SourceDocument.title == "Test Doc"))
    doc = result.scalar_one()
    assert doc.domain == "engineering"
    assert doc.uploaded_by_id == admin_user.id


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


# ---------------------------------------------------------------------------
# List tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_empty(client, admin_user):
    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(admin_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_tasks(client, db, admin_user):
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
async def test_tasks_only_shows_own_tasks(client, db, admin_user, author_user):
    """Admin should only see their own tasks, not other users' tasks."""
    from app.models.user import Role, RoleName
    result = await db.execute(select(Role).where(Role.name == RoleName.ADMIN.value))
    admin_role = result.scalar_one()
    await db.refresh(author_user, ["roles"])
    author_user.roles.append(admin_role)
    await db.flush()

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

    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(admin_user))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["task_type"] == "generate_questions"

    resp = await client.get("/api/v1/ai/tasks", headers=auth_header(author_user))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["task_type"] == "scaffold_options"


# ---------------------------------------------------------------------------
# Get task + worker sync
# ---------------------------------------------------------------------------


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
async def test_get_task_syncs_failed_from_worker(client, db, admin_user):
    """Worker reporting failure should update AITask to failed with error."""
    task = AITask(
        task_type=AITaskType.SCAFFOLD_OPTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-fail-test",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.get_task_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = {
            "task_id": "worker-fail-test",
            "status": "failed",
            "result": None,
            "error": "LLM rate limit exceeded",
        }

        resp = await client.get(
            f"/api/v1/ai/tasks/{task.id}",
            headers=auth_header(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"] == "LLM rate limit exceeded"


@pytest.mark.asyncio
async def test_get_task_worker_unreachable_returns_db_state(client, db, admin_user):
    """When worker is unreachable during status sync, return existing DB state."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-unreachable",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.get_task_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = None  # Worker unreachable

        resp = await client.get(
            f"/api/v1/ai/tasks/{task.id}",
            headers=auth_header(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    # Should still return the DB state (running), not error out
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_get_task_not_found(client, admin_user):
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/ai/tasks/{fake_id}",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_completed_task_does_not_sync(client, db, admin_user):
    """Completed tasks should NOT trigger a worker status sync."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=admin_user.id,
        worker_task_id="worker-done",
        result={"questions": ["q1"]},
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.get_task_status", new_callable=AsyncMock) as mock_status:
        resp = await client.get(
            f"/api/v1/ai/tasks/{task.id}",
            headers=auth_header(admin_user),
        )
        mock_status.assert_not_called()

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Cancel task
# ---------------------------------------------------------------------------


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
    """Pending task (no worker_task_id) should cancel without calling worker."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.PENDING,
        user_id=admin_user.id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.cancel_task", new_callable=AsyncMock) as mock_cancel:
        resp = await client.post(
            f"/api/v1/ai/tasks/{task.id}/cancel",
            headers=auth_header(admin_user),
        )
        # Pending task has no worker_task_id, so cancel_task should not be called
        mock_cancel.assert_not_called()

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
async def test_cancel_cancelled_task_returns_409(client, db, admin_user):
    """Cancelling an already-cancelled task should return 409."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.CANCELLED,
        user_id=admin_user.id,
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
async def test_cancel_running_task_worker_unreachable(client, db, admin_user):
    """Cancel should succeed locally even if worker is unreachable."""
    task = AITask(
        task_type=AITaskType.REVIEW_ASSIST,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-gone",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    with patch("app.services.worker_client.cancel_task", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = None  # Worker unreachable

        resp = await client.post(
            f"/api/v1/ai/tasks/{task.id}/cancel",
            headers=auth_header(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"

    await db.refresh(task)
    assert task.status == AITaskStatus.CANCELLED


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


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
async def test_cancel_requires_admin(client, db, admin_user, respondent_user):
    """Non-admin cannot cancel tasks."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.RUNNING,
        user_id=admin_user.id,
        worker_task_id="worker-perm-test",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.post(
        f"/api/v1/ai/tasks/{task.id}/cancel",
        headers=auth_header(respondent_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_worker_not_configured(client, admin_user):
    with patch("app.api.v1.worker_triggers.settings") as mock_settings:
        mock_settings.WORKER_URL = ""
        resp = await client.post("/api/v1/ai/generate-questions", json={
            "topic": "test",
        }, headers=auth_header(admin_user))
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Task result/error storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_result_json_stored_correctly(client, db, admin_user):
    """Verify JSONB result column stores and returns complex data."""
    task = AITask(
        task_type=AITaskType.GENERATE_QUESTIONS,
        status=AITaskStatus.COMPLETED,
        user_id=admin_user.id,
        result={"questions": [{"title": "Q1", "body": "details"}], "count": 1},
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.get(
        f"/api/v1/ai/tasks/{task.id}",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["count"] == 1
    assert data["result"]["questions"][0]["title"] == "Q1"


@pytest.mark.asyncio
async def test_task_error_stored_correctly(client, db, admin_user):
    """Verify error text column stores and returns error messages."""
    task = AITask(
        task_type=AITaskType.SCAFFOLD_OPTIONS,
        status=AITaskStatus.FAILED,
        user_id=admin_user.id,
        error="Connection timeout after 10s",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    resp = await client.get(
        f"/api/v1/ai/tasks/{task.id}",
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] == "Connection timeout after 10s"
    assert data["result"] is None
