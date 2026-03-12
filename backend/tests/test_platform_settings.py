"""Tests for the platform settings feature (runtime toggles)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.platform_setting import PlatformSetting
from app.models.question import Question, QuestionStatus
from app.models.answer import Answer, AnswerStatus
from app.services.platform_settings import DEFAULTS, get_all_settings, get_setting, set_setting
from tests.conftest import auth_header


# ---------------------------------------------------------------------------
# Service layer tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_setting_returns_default_when_no_row(db):
    """get_setting returns the default value when no DB row exists."""
    val = await get_setting(db, "auto_review_enabled")
    assert val is True


@pytest.mark.asyncio
async def test_get_setting_returns_db_value(db, admin_user):
    """get_setting returns the DB value when a row exists."""
    await set_setting(db, "auto_review_enabled", False, admin_user.id)
    val = await get_setting(db, "auto_review_enabled")
    assert val is False


@pytest.mark.asyncio
async def test_get_setting_unknown_key_raises(db):
    """get_setting raises KeyError for unknown keys."""
    with pytest.raises(KeyError, match="Unknown setting"):
        await get_setting(db, "nonexistent_key")


@pytest.mark.asyncio
async def test_get_all_settings_defaults(db):
    """get_all_settings returns all defaults when table is empty."""
    settings = await get_all_settings(db)
    assert settings == DEFAULTS


@pytest.mark.asyncio
async def test_get_all_settings_with_override(db, admin_user):
    """get_all_settings merges DB overrides onto defaults."""
    await set_setting(db, "auto_review_enabled", False, admin_user.id)
    settings = await get_all_settings(db)
    assert settings["auto_review_enabled"] is False
    assert settings["auto_scaffold_enabled"] is True


@pytest.mark.asyncio
async def test_set_setting_creates_row(db, admin_user):
    """set_setting creates a new row if none exists."""
    row = await set_setting(db, "auto_scaffold_enabled", False, admin_user.id)
    assert row.key == "auto_scaffold_enabled"
    assert row.value is False
    assert row.updated_by_id == admin_user.id


@pytest.mark.asyncio
async def test_set_setting_updates_existing_row(db, admin_user):
    """set_setting updates an existing row (upsert)."""
    await set_setting(db, "auto_review_enabled", False, admin_user.id)
    await set_setting(db, "auto_review_enabled", True, admin_user.id)
    val = await get_setting(db, "auto_review_enabled")
    assert val is True


@pytest.mark.asyncio
async def test_set_setting_rejects_unknown_key(db, admin_user):
    """set_setting rejects unknown keys."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await set_setting(db, "bad_key", True, admin_user.id)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_set_setting_rejects_wrong_type(db, admin_user):
    """set_setting rejects values with wrong type."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await set_setting(db, "auto_review_enabled", "yes", admin_user.id)
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_requires_admin(client, respondent_user):
    """GET /settings returns 403 for non-admin users."""
    resp = await client.get("/api/v1/settings", headers=auth_header(respondent_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client, admin_user):
    """GET /settings returns defaults when no overrides exist."""
    resp = await client.get("/api/v1/settings", headers=auth_header(admin_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["settings"]["auto_review_enabled"] is True
    assert data["settings"]["auto_scaffold_enabled"] is True


@pytest.mark.asyncio
async def test_put_setting_updates_value(client, admin_user):
    """PUT /settings/{key} updates a setting."""
    resp = await client.put(
        "/api/v1/settings/auto_review_enabled",
        json={"value": False},
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "auto_review_enabled"
    assert data["value"] is False

    # Verify it persists
    resp2 = await client.get("/api/v1/settings", headers=auth_header(admin_user))
    assert resp2.json()["settings"]["auto_review_enabled"] is False


@pytest.mark.asyncio
async def test_put_setting_rejects_unknown_key(client, admin_user):
    """PUT /settings/{key} returns 400 for unknown keys."""
    resp = await client.put(
        "/api/v1/settings/unknown_key",
        json={"value": True},
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_setting_rejects_wrong_type(client, admin_user):
    """PUT /settings/{key} returns 422 for wrong value type."""
    resp = await client.put(
        "/api/v1/settings/auto_review_enabled",
        json={"value": "yes"},
        headers=auth_header(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_setting_requires_admin(client, respondent_user):
    """PUT /settings/{key} returns 403 for non-admin users."""
    resp = await client.put(
        "/api/v1/settings/auto_review_enabled",
        json={"value": False},
        headers=auth_header(respondent_user),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Gating tests — verify auto-triggers respect settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_review_gated_by_setting(client, db, admin_user, author_user, respondent_user):
    """Disabling auto_review_enabled prevents trigger_review_assist from firing."""
    # Create a published question
    question = Question(
        title="Gating test Q", body="Body", created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)

    # Create a draft answer
    answer = Answer(
        question_id=question.id, author_id=respondent_user.id,
        body="My answer",
    )
    db.add(answer)
    await db.flush()
    await db.refresh(answer)

    # Disable auto review
    await set_setting(db, "auto_review_enabled", False, admin_user.id)
    await db.commit()

    with patch("app.api.v1.answers.worker_client.trigger_review_assist", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.answers.slack.notify_answer_submitted", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/v1/answers/{answer.id}/submit",
            headers=auth_header(respondent_user),
        )
        assert resp.status_code == 200
        mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_auto_review_fires_when_enabled(client, db, admin_user, respondent_user):
    """With auto_review_enabled=True (default), trigger fires on submit."""
    question = Question(
        title="Gating test Q2", body="Body", created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)

    answer = Answer(
        question_id=question.id, author_id=respondent_user.id,
        body="My answer",
    )
    db.add(answer)
    await db.flush()
    await db.refresh(answer)
    await db.commit()

    with patch("app.api.v1.answers.worker_client.trigger_review_assist", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.answers.slack.notify_answer_submitted", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/v1/answers/{answer.id}/submit",
            headers=auth_header(respondent_user),
        )
        assert resp.status_code == 200
        mock_trigger.assert_called_once()


@pytest.mark.asyncio
async def test_auto_scaffold_fires_when_enabled(client, db, admin_user, author_user):
    """With auto_scaffold_enabled=True (default), trigger fires on publish."""
    question = Question(
        title="Scaffold enabled test", body="Body", created_by_id=author_user.id,
        status=QuestionStatus.IN_REVIEW.value,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)
    await db.commit()

    with patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.questions.slack.notify_question_published", new_callable=AsyncMock, return_value=(None, None)):
        resp = await client.post(
            f"/api/v1/questions/{question.id}/publish",
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        mock_trigger.assert_called_once()


@pytest.mark.asyncio
async def test_auto_scaffold_gated_by_setting(client, db, admin_user, author_user):
    """Disabling auto_scaffold_enabled prevents trigger_scaffold_options from firing."""
    # Create a question in in_review state
    question = Question(
        title="Scaffold gate test", body="Body", created_by_id=author_user.id,
        status=QuestionStatus.IN_REVIEW.value,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)

    # Disable auto scaffold
    await set_setting(db, "auto_scaffold_enabled", False, admin_user.id)
    await db.commit()

    with patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock) as mock_trigger, \
         patch("app.api.v1.questions.slack.notify_question_published", new_callable=AsyncMock, return_value=(None, None)):
        resp = await client.post(
            f"/api/v1/questions/{question.id}/publish",
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 200
        mock_trigger.assert_not_called()
