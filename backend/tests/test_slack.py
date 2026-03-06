"""Tests for the Slack notification service and its integration with state transitions.

Tests are organized into:
1. Unit tests for the slack service module (mocked Slack SDK)
2. Integration tests verifying notifications fire at correct state transitions
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from slack_sdk.errors import SlackApiError

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from app.services import slack
from tests.conftest import auth_header


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_slack_response(data: dict) -> MagicMock:
    """Create a mock Slack API response."""
    resp = MagicMock()
    resp.__getitem__ = lambda self, key: data[key]
    resp.get = data.get
    return resp


@pytest.fixture(autouse=True)
def _clear_slack_cache():
    """Clear the in-memory Slack user cache between tests."""
    slack._slack_user_cache.clear()
    yield
    slack._slack_user_cache.clear()


# ---------------------------------------------------------------------------
# Unit tests: _is_enabled
# ---------------------------------------------------------------------------

class TestSlackEnabled:
    async def test_disabled_when_no_token(self):
        with patch.object(slack.settings, "SLACK_BOT_TOKEN", ""):
            assert slack._is_enabled() is False

    async def test_enabled_when_token_set(self):
        with patch.object(slack.settings, "SLACK_BOT_TOKEN", "xoxb-test-token"):
            assert slack._is_enabled() is True


# ---------------------------------------------------------------------------
# Unit tests: _lookup_slack_user
# ---------------------------------------------------------------------------

class TestSlackUserLookup:
    async def test_lookup_success(self):
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.return_value = _mock_slack_response({
            "user": {"id": "U12345"}
        })
        with patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack._lookup_slack_user("test@example.com")
        assert result == "U12345"
        mock_client.users_lookupByEmail.assert_called_once_with(email="test@example.com")

    async def test_lookup_caches_result(self):
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.return_value = _mock_slack_response({
            "user": {"id": "U12345"}
        })
        with patch.object(slack, "_get_client", return_value=mock_client):
            r1 = await slack._lookup_slack_user("cached@example.com")
            r2 = await slack._lookup_slack_user("cached@example.com")
        assert r1 == r2 == "U12345"
        # Only called once — second call uses cache
        assert mock_client.users_lookupByEmail.call_count == 1

    async def test_lookup_caches_not_found(self):
        error_resp = MagicMock()
        error_resp.get.return_value = "users_not_found"
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.side_effect = SlackApiError(
            message="users_not_found", response=error_resp
        )
        with patch.object(slack, "_get_client", return_value=mock_client):
            r1 = await slack._lookup_slack_user("missing@example.com")
            r2 = await slack._lookup_slack_user("missing@example.com")
        assert r1 is None
        assert r2 is None
        # Only called once — not-found is cached too
        assert mock_client.users_lookupByEmail.call_count == 1

    async def test_lookup_handles_api_error_gracefully(self):
        error_resp = MagicMock()
        error_resp.get.return_value = "internal_error"
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.side_effect = SlackApiError(
            message="internal_error", response=error_resp
        )
        with patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack._lookup_slack_user("error@example.com")
        assert result is None

    async def test_lookup_handles_generic_exception(self):
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.side_effect = ConnectionError("network down")
        with patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack._lookup_slack_user("down@example.com")
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests: _mention_or_name
# ---------------------------------------------------------------------------

class TestMentionOrName:
    async def test_returns_mention_when_slack_user_found(self):
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.return_value = _mock_slack_response({
            "user": {"id": "U99999"}
        })
        with patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack._mention_or_name("user@test.com", "Fallback Name")
        assert result == "<@U99999>"

    async def test_returns_display_name_when_no_email(self):
        result = await slack._mention_or_name(None, "Display Name")
        assert result == "Display Name"

    async def test_returns_display_name_when_lookup_fails(self):
        mock_client = AsyncMock()
        mock_client.users_lookupByEmail.side_effect = ConnectionError("offline")
        with patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack._mention_or_name("user@test.com", "Fallback")
        assert result == "Fallback"


# ---------------------------------------------------------------------------
# Unit tests: _post_message
# ---------------------------------------------------------------------------

class TestPostMessage:
    async def test_returns_ts_on_success(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({"ts": "1234567890.123456"})
        with patch.object(slack, "_get_client", return_value=mock_client):
            ts = await slack._post_message("#test", "hello")
        assert ts == "1234567890.123456"
        mock_client.chat_postMessage.assert_called_once_with(channel="#test", text="hello", thread_ts=None)

    async def test_passes_thread_ts(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({"ts": "1234567890.999"})
        with patch.object(slack, "_get_client", return_value=mock_client):
            ts = await slack._post_message("#test", "reply", thread_ts="1234567890.123456")
        assert ts == "1234567890.999"
        mock_client.chat_postMessage.assert_called_once_with(
            channel="#test", text="reply", thread_ts="1234567890.123456"
        )

    async def test_returns_none_on_failure(self):
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = ConnectionError("network down")
        with patch.object(slack, "_get_client", return_value=mock_client):
            ts = await slack._post_message("#test", "hello")
        assert ts is None

    async def test_returns_none_on_slack_api_error(self):
        error_resp = MagicMock()
        error_resp.get.return_value = "channel_not_found"
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="channel_not_found", response=error_resp
        )
        with patch.object(slack, "_get_client", return_value=mock_client):
            ts = await slack._post_message("#nonexistent", "hello")
        assert ts is None


# ---------------------------------------------------------------------------
# Unit tests: notification functions
# ---------------------------------------------------------------------------

class TestNotifyQuestionPublished:
    async def test_creates_thread_and_returns_ts(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock, side_effect=["1234.5678", "reply.ts"]):
            thread_ts, channel = await slack.notify_question_published(
                question_title="What is TDD?",
                question_id="q-123",
                question_body="Tell me about TDD",
                publisher_name="Admin User",
            )
        assert thread_ts == "1234.5678"
        assert channel == "#test"

    async def test_posts_body_as_thread_reply(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock, side_effect=["1234.5678", "reply.ts"]) as mock_post:
            await slack.notify_question_published(
                question_title="Q",
                question_id="q-1",
                question_body="Body text here",
                publisher_name="Admin",
            )
        # First call: main message (no thread_ts)
        assert mock_post.call_count == 2
        first_call = mock_post.call_args_list[0]
        assert first_call[0][0] == "#test"
        assert "Q" in first_call[0][1]
        # Second call: body as thread reply
        second_call = mock_post.call_args_list[1]
        assert second_call[0][0] == "#test"
        assert second_call[0][1] == "Body text here"
        assert second_call[1]["thread_ts"] == "1234.5678"

    async def test_includes_link(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock, side_effect=["1234.5678", "reply.ts"]) as mock_post:
            await slack.notify_question_published(
                question_title="Q",
                question_id="q-123",
                question_body="Body",
                publisher_name="Admin",
            )
        msg = mock_post.call_args_list[0][0][1]
        assert "http://localhost:5173/questions/q-123" in msg

    async def test_no_op_when_disabled(self):
        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            thread_ts, channel = await slack.notify_question_published("T", "id", "body", "N")
        assert thread_ts is None
        assert channel is None
        mock_post.assert_not_called()

    async def test_no_op_when_no_channel(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value=""), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            thread_ts, channel = await slack.notify_question_published("T", "id", "body", "N")
        assert thread_ts is None
        assert channel is None
        mock_post.assert_not_called()

    async def test_returns_none_when_post_fails(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock, return_value=None):
            thread_ts, channel = await slack.notify_question_published("T", "id", "body", "N")
        assert thread_ts is None
        assert channel is None


class TestNotifyThreadUpdate:
    async def test_posts_to_thread(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_thread_update("#channel", "1234.5678", "Update text")
        mock_post.assert_called_once_with("#channel", "Update text", thread_ts="1234.5678")

    async def test_no_op_when_disabled(self):
        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_thread_update("#channel", "1234.5678", "Update")
        mock_post.assert_not_called()


class TestNotifyQuestionRejected:
    async def test_includes_mention_and_comment(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="<@U123>"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_question_rejected(
                question_title="Bad question",
                question_id="q-456",
                author_email="author@test.com",
                author_name="Author",
                comment="Too vague",
            )
        msg = mock_send.call_args[0][1]
        assert "<@U123>" in msg
        assert "Too vague" in msg
        assert "Bad question" in msg
        assert "http://localhost:5173/questions/q-456" in msg

    async def test_works_without_comment(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Author"):
            await slack.notify_question_rejected(
                question_title="Q",
                question_id="q-789",
                author_email=None,
                author_name="Author",
            )
        msg = mock_send.call_args[0][1]
        assert "Reason:" not in msg


class TestNotifyAnswerSubmitted:
    async def test_posts_to_thread_when_available(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_answer_submitted(
                question_title="What is TDD?",
                question_id="q-1",
                answer_id="a-123",
                author_name="Respondent",
                slack_channel="#test",
                slack_thread_ts="1234.5678",
            )
        mock_post.assert_called_once()
        msg = mock_post.call_args[0][1]
        assert "Respondent" in msg
        assert "What is TDD?" in msg
        assert "http://localhost:5173/answers/a-123" in msg
        assert mock_post.call_args[1]["thread_ts"] == "1234.5678"

    async def test_falls_back_to_default_channel(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#default"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send:
            await slack.notify_answer_submitted(
                question_title="Q",
                question_id="q-1",
                answer_id="a-123",
                author_name="Respondent",
            )
        mock_send.assert_called_once()


class TestNotifyReviewVerdict:
    async def test_approved_verdict(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="<@U456>"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_review_verdict(
                question_title="Q",
                answer_id="a-1",
                verdict="approved",
                reviewer_name="Reviewer",
                author_email="author@test.com",
                author_name="Author",
            )
        msg = mock_send.call_args[0][1]
        assert ":white_check_mark:" in msg
        assert "approved" in msg
        assert "<@U456>" in msg
        assert "http://localhost:5173/answers/a-1" in msg

    async def test_posts_to_thread_when_available(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Author"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_review_verdict(
                question_title="Q",
                answer_id="a-1",
                verdict="approved",
                reviewer_name="Reviewer",
                author_email=None,
                author_name="Author",
                slack_channel="#ch",
                slack_thread_ts="1234.5678",
            )
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["thread_ts"] == "1234.5678"

    async def test_changes_requested_verdict_with_comment(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Author"):
            await slack.notify_review_verdict(
                question_title="Q",
                answer_id="a-2",
                verdict="changes_requested",
                reviewer_name="Reviewer",
                author_email=None,
                author_name="Author",
                comment="Fix section 3",
            )
        msg = mock_send.call_args[0][1]
        assert ":memo:" in msg
        assert "Fix section 3" in msg

    async def test_rejected_verdict(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Author"):
            await slack.notify_review_verdict(
                question_title="Q", answer_id="a-3", verdict="rejected",
                reviewer_name="R", author_email=None, author_name="Author",
            )
        msg = mock_send.call_args[0][1]
        assert ":no_entry:" in msg


class TestNotifyAnswerApproved:
    async def test_sends_celebration_message(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="<@U789>"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_answer_approved(
                question_title="Important Q",
                answer_id="a-100",
                author_email="author@test.com",
                author_name="Author",
            )
        msg = mock_send.call_args[0][1]
        assert ":tada:" in msg
        assert "<@U789>" in msg
        assert "Important Q" in msg
        assert "http://localhost:5173/answers/a-100" in msg

    async def test_posts_to_thread_when_available(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Author"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_answer_approved(
                question_title="Q",
                answer_id="a-1",
                author_email=None,
                author_name="Author",
                slack_channel="#ch",
                slack_thread_ts="1234.5678",
            )
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["thread_ts"] == "1234.5678"


class TestNotifyRevisionRequested:
    async def test_sends_revision_message(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_send_message", new_callable=AsyncMock) as mock_send, \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="<@U111>"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_revision_requested(
                question_title="Q",
                answer_id="a-200",
                author_email="author@test.com",
                author_name="Author",
            )
        msg = mock_send.call_args[0][1]
        assert "<@U111>" in msg
        assert "revise" in msg.lower()
        assert "http://localhost:5173/answers/a-200" in msg


class TestNotifyQuestionClosed:
    async def test_posts_closure_to_thread(self):
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_question_closed(
                slack_channel="#test",
                slack_thread_ts="1234.5678",
                question_title="Closed Q",
                question_id="q-1",
            )
        mock_post.assert_called_once()
        msg = mock_post.call_args[0][1]
        assert ":lock:" in msg
        assert "Closed Q" in msg
        assert "http://localhost:5173/questions/q-1" in msg
        assert mock_post.call_args[1]["thread_ts"] == "1234.5678"

    async def test_no_op_when_disabled(self):
        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_question_closed("#ch", "1234.5678", "Q", "q-1")
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests: _send_message error handling (backward compat)
# ---------------------------------------------------------------------------

class TestSendMessageResilience:
    async def test_send_message_handles_exception(self):
        """_send_message catches exceptions and does not propagate."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = ConnectionError("network down")
        with patch.object(slack, "_get_client", return_value=mock_client):
            # Should not raise
            await slack._send_message("#test", "hello")

    async def test_send_message_handles_slack_api_error(self):
        error_resp = MagicMock()
        error_resp.get.return_value = "channel_not_found"
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="channel_not_found", response=error_resp
        )
        with patch.object(slack, "_get_client", return_value=mock_client):
            await slack._send_message("#nonexistent", "hello")


# ---------------------------------------------------------------------------
# Integration tests: Slack notifications fire at correct state transitions
# ---------------------------------------------------------------------------

class TestSlackIntegrationWithRoutes:
    """Verify that Slack notification functions are called from the correct
    API routes at the correct state transitions."""

    async def test_publish_triggers_slack_notification_and_stores_thread(
        self, client: AsyncClient, author_user: User, admin_user: User, db,
    ):
        q = Question(title="Slack Test Q", body="Body text", created_by_id=author_user.id,
                     status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_published",
                    new_callable=AsyncMock, return_value=("1234.5678", "#test-channel")) as mock_notify:
            r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
            assert r.status_code == 200
            mock_notify.assert_called_once_with(
                question_title="Slack Test Q",
                question_id=str(q.id),
                question_body="Body text",
                publisher_name=admin_user.display_name,
            )

    async def test_reject_triggers_slack_notification(
        self, client: AsyncClient, author_user: User, admin_user: User, db,
    ):
        q = Question(title="Reject Q", body="B", created_by_id=author_user.id,
                     status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_rejected", new_callable=AsyncMock) as mock_notify:
            r = await client.post(
                f"/api/v1/questions/{q.id}/reject",
                json={"comment": "Needs work"},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args[1]
            assert call_kwargs["question_title"] == "Reject Q"
            assert call_kwargs["comment"] == "Needs work"
            assert call_kwargs["author_email"] == author_user.email

    async def test_close_triggers_thread_notification(
        self, client: AsyncClient, admin_user: User, db,
    ):
        q = Question(title="Close Q", body="B", created_by_id=admin_user.id,
                     status=QuestionStatus.PUBLISHED.value,
                     slack_thread_ts="1234.5678", slack_channel="#test")
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_closed", new_callable=AsyncMock) as mock_notify:
            r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
            assert r.status_code == 200
            mock_notify.assert_called_once_with(
                slack_channel="#test",
                slack_thread_ts="1234.5678",
                question_title="Close Q",
                question_id=str(q.id),
            )

    async def test_close_without_thread_skips_notification(
        self, client: AsyncClient, admin_user: User, db,
    ):
        q = Question(title="No Thread Q", body="B", created_by_id=admin_user.id,
                     status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_closed", new_callable=AsyncMock) as mock_notify:
            r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
            assert r.status_code == 200
            mock_notify.assert_not_called()

    async def test_answer_submit_triggers_slack_notification(
        self, client: AsyncClient, respondent_user: User, admin_user: User, db,
    ):
        q = Question(title="Q for Answer", body="B", created_by_id=admin_user.id,
                     status=QuestionStatus.PUBLISHED.value,
                     slack_thread_ts="1234.5678", slack_channel="#test")
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="My answer")
        db.add(a)
        await db.flush()

        with patch("app.api.v1.answers.slack.notify_answer_submitted", new_callable=AsyncMock) as mock_notify:
            r = await client.post(f"/api/v1/answers/{a.id}/submit", headers=auth_header(respondent_user))
            assert r.status_code == 200
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args[1]
            assert call_kwargs["question_title"] == "Q for Answer"
            assert call_kwargs["author_name"] == respondent_user.display_name
            assert call_kwargs["slack_channel"] == "#test"
            assert call_kwargs["slack_thread_ts"] == "1234.5678"

    async def test_review_approved_triggers_slack_notifications(
        self, client: AsyncClient, reviewer_user: User, respondent_user: User,
        admin_user: User, db,
    ):
        q = Question(title="Review Q", body="B", created_by_id=admin_user.id,
                     status=QuestionStatus.PUBLISHED.value,
                     review_policy={"min_approvals": 1},
                     slack_thread_ts="1234.5678", slack_channel="#test")
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="A",
                   status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        with patch("app.api.v1.reviews.slack.notify_review_verdict", new_callable=AsyncMock) as mock_verdict, \
             patch("app.api.v1.reviews.slack.notify_answer_approved", new_callable=AsyncMock) as mock_approved:
            r = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": "approved"},
                headers=auth_header(reviewer_user),
            )
            assert r.status_code == 200
            mock_verdict.assert_called_once()
            assert mock_verdict.call_args[1]["verdict"] == "approved"
            assert mock_verdict.call_args[1]["slack_channel"] == "#test"
            assert mock_verdict.call_args[1]["slack_thread_ts"] == "1234.5678"
            # With min_approvals=1, approval triggers the approved notification
            mock_approved.assert_called_once()
            assert mock_approved.call_args[1]["slack_channel"] == "#test"

    async def test_review_changes_requested_triggers_revision_notification(
        self, client: AsyncClient, reviewer_user: User, respondent_user: User,
        admin_user: User, db,
    ):
        q = Question(title="Changes Q", body="B", created_by_id=admin_user.id,
                     status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="A",
                   status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        with patch("app.api.v1.reviews.slack.notify_review_verdict", new_callable=AsyncMock) as mock_verdict, \
             patch("app.api.v1.reviews.slack.notify_revision_requested", new_callable=AsyncMock) as mock_revision:
            r = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": "changes_requested", "comment": "Fix it"},
                headers=auth_header(reviewer_user),
            )
            assert r.status_code == 200
            mock_verdict.assert_called_once()
            assert mock_verdict.call_args[1]["verdict"] == "changes_requested"
            mock_revision.assert_called_once()

    async def test_no_slack_when_disabled(
        self, client: AsyncClient, author_user: User, admin_user: User, db,
    ):
        """When SLACK_BOT_TOKEN is empty, no Slack calls should be made."""
        q = Question(title="No Slack", body="B", created_by_id=author_user.id,
                     status=QuestionStatus.IN_REVIEW.value)
        db.add(q)
        await db.flush()

        with patch.object(slack.settings, "SLACK_BOT_TOKEN", ""), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
            assert r.status_code == 200
            mock_post.assert_not_called()
