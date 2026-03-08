"""Tests for Plan A: Slack Thread Lifecycle.

Tests cover:
1. Thread creation on question publish (main message + body reply)
2. slack_thread_ts storage on the question model
3. Clickable link formatting with FRONTEND_URL
4. State change replies posted to the question's thread
5. Integration with API routes

These tests are written TDD-style — they will FAIL until Plan A is implemented.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
# Thread Creation
# ---------------------------------------------------------------------------

class TestThreadCreation:
    """notify_question_published should create a Slack thread:
    1. Main message (title + link) — returns thread_ts
    2. Reply in thread with the question body
    """

    async def test_notify_published_creates_thread(self):
        """Main message is sent first, then a reply in the thread with the body."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "1234567890.123456",
            "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_question_published(
                question_title="What is TDD?",
                question_id="q-123",
                publisher_name="Admin",
                question_body="Tell us about test-driven development.",
            )

        # Two calls: main message + thread reply
        assert mock_client.chat_postMessage.call_count == 2

        # First call: main message (no thread_ts)
        first_call = mock_client.chat_postMessage.call_args_list[0]
        assert first_call.kwargs.get("thread_ts") is None or "thread_ts" not in first_call.kwargs

        # Second call: reply in thread
        second_call = mock_client.chat_postMessage.call_args_list[1]
        assert second_call.kwargs.get("thread_ts") == "1234567890.123456"
        # Reply should contain the question body
        msg = second_call.kwargs.get("text", "")
        assert "test-driven development" in msg

    async def test_notify_published_returns_thread_ts(self):
        """notify_question_published should return the thread_ts for storage."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "1234567890.999",
            "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack.notify_question_published(
                question_title="Q",
                question_id="q-1",
                publisher_name="Admin",
                question_body="Body text",
            )

        # The function should return (thread_ts, channel) tuple
        assert result == ("1234567890.999", "#test")

    async def test_notify_published_no_op_when_disabled(self):
        """When Slack is disabled, no messages sent, returns None."""
        mock_client = AsyncMock()

        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack.notify_question_published(
                question_title="Q",
                question_id="q-1",
                publisher_name="Admin",
                question_body="Body",
            )

        mock_client.chat_postMessage.assert_not_called()
        assert result == (None, None)

    async def test_thread_creation_failure_returns_none(self):
        """If the main message fails, return None without raising."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = ConnectionError("network down")

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client):
            result = await slack.notify_question_published(
                question_title="Q",
                question_id="q-1",
                publisher_name="Admin",
                question_body="Body",
            )

        assert result == (None, None)


# ---------------------------------------------------------------------------
# Link Formatting
# ---------------------------------------------------------------------------

class TestAnswerBodyThreadReply:
    """notify_answer_submitted should post the answer body as a thread reply."""

    async def test_answer_body_posted_as_thread_reply(self):
        """When answer_body is provided in a thread, it's posted as a follow-up reply."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "1234567890.123456", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_answer_submitted(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_name="Respondent",
                answer_body="My **detailed** answer with [a link](https://example.com)",
                slack_channel="#test",
                slack_thread_ts="1111.2222",
            )

        # Two calls: notification message + body reply
        assert mock_client.chat_postMessage.call_count == 2

        # First call: notification message in thread
        first_call = mock_client.chat_postMessage.call_args_list[0]
        assert first_call.kwargs["thread_ts"] == "1111.2222"
        assert "Answer submitted" in first_call.kwargs["text"]

        # Second call: body reply in same thread with mrkdwn conversion
        second_call = mock_client.chat_postMessage.call_args_list[1]
        assert second_call.kwargs["thread_ts"] == "1111.2222"
        body_text = second_call.kwargs["text"]
        assert "*detailed*" in body_text
        assert "**detailed**" not in body_text
        assert "<https://example.com|a link>" in body_text

    async def test_no_body_reply_without_answer_body(self):
        """When answer_body is None, only the notification message is posted."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "1234567890.123456", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_answer_submitted(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_name="Respondent",
                slack_channel="#test",
                slack_thread_ts="1111.2222",
            )

        assert mock_client.chat_postMessage.call_count == 1


class TestLinkFormatting:
    """All Slack messages should use clickable links when FRONTEND_URL is set."""

    async def test_message_contains_clickable_link(self):
        """With FRONTEND_URL set, messages should contain Slack-formatted links."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "123.456", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", "https://app.example.com"):
            await slack.notify_question_published(
                question_title="Test Q",
                question_id="abc-123",
                publisher_name="Admin",
                question_body="Body",
            )

        # The main message should contain a clickable link, not a raw ID
        first_call = mock_client.chat_postMessage.call_args_list[0]
        msg = first_call.kwargs.get("text", "")
        assert "<https://app.example.com/questions/abc-123|View question>" in msg
        assert "Question ID: `abc-123`" not in msg

    async def test_link_includes_question_id(self):
        """Even with empty FRONTEND_URL, message still includes the question ID."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "123.456", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", ""):
            await slack.notify_question_published(
                question_title="Test Q",
                question_id="abc-123",
                publisher_name="Admin",
                question_body="Body",
            )

        first_call = mock_client.chat_postMessage.call_args_list[0]
        msg = first_call.kwargs.get("text", "")
        assert "abc-123" in msg

    async def test_answer_notification_uses_link(self):
        """notify_answer_submitted should also use clickable links."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "123.456", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#test"), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", "https://app.example.com"):
            await slack.notify_answer_submitted(
                question_title="Q",
                question_id="q-789",
                answer_id="ans-456",
                author_name="Respondent",
            )

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        msg = call_kwargs.get("text", "")
        assert "https://app.example.com" in msg


# ---------------------------------------------------------------------------
# State Change Thread Replies
# ---------------------------------------------------------------------------

class TestThreadUpdateAndClosure:
    """notify_thread_update and notify_question_closed post to existing threads."""

    async def test_thread_update_posts_to_thread(self):
        """Posts a reply using the stored slack_thread_ts."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "999.999", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_thread_update(
                slack_channel="#test",
                slack_thread_ts="1234567890.123456",
                text="Status update",
            )

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "1234567890.123456"

    async def test_thread_update_disabled_no_op(self):
        """When Slack is disabled, thread update is a no-op."""
        mock_client = AsyncMock()

        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_thread_update(
                slack_channel="#test",
                slack_thread_ts="123.456",
                text="Update",
            )

        mock_client.chat_postMessage.assert_not_called()

    async def test_question_closed_posts_to_thread(self):
        """notify_question_closed posts a closure message to the thread."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "999.999", "ok": True,
        })

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_question_closed(
                slack_channel="#test",
                slack_thread_ts="123.456",
                question_title="My Question",
                question_id="q-1",
            )

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "123.456"
        assert "closed" in call_kwargs["text"].lower()

    async def test_question_closed_disabled_no_op(self):
        """When Slack is disabled, closure notification is a no-op."""
        mock_client = AsyncMock()

        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_get_client", return_value=mock_client):
            await slack.notify_question_closed(
                slack_channel="#test",
                slack_thread_ts="123.456",
                question_title="Q",
                question_id="q-1",
            )

        mock_client.chat_postMessage.assert_not_called()

    async def test_thread_update_handles_error_gracefully(self):
        """Slack API errors during thread reply don't propagate."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = ConnectionError("network down")

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client):
            # Should not raise
            await slack.notify_thread_update(
                slack_channel="#test",
                slack_thread_ts="123.456",
                text="Update",
            )


# ---------------------------------------------------------------------------
# Integration: Route-level tests
# ---------------------------------------------------------------------------

class TestSlackThreadRouteIntegration:
    """Verify routes trigger the correct thread-aware Slack functions."""

    async def test_publish_creates_thread_and_stores_ts(
        self, client: AsyncClient, author_user: User, admin_user: User, db: AsyncSession,
    ):
        """Publishing a question creates a Slack thread and stores thread_ts."""
        q = Question(
            title="Thread Test Q", body="Body text",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_published",
                    new_callable=AsyncMock, return_value=("1234567890.thread", "#test")) as mock_notify, \
             patch("app.api.v1.questions.update_question_embedding", new_callable=AsyncMock), \
             patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock):
            r = await client.post(
                f"/api/v1/questions/{q.id}/publish",
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_notify.assert_called_once()

            # Verify question_body is passed to the notification
            call_kwargs = mock_notify.call_args.kwargs
            assert "question_body" in call_kwargs

        # The route should store the returned thread_ts and channel on the question
        await db.refresh(q)
        assert q.slack_thread_ts == "1234567890.thread"
        assert q.slack_channel == "#test"

    async def test_close_triggers_thread_reply(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Closing a question triggers a thread closure notification."""
        q = Question(
            title="Close Thread Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        # Simulate question already having a thread
        q.slack_thread_ts = "111.222"
        q.slack_channel = "#test"
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_closed", new_callable=AsyncMock) as mock_closed:
            r = await client.post(
                f"/api/v1/questions/{q.id}/close",
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_closed.assert_called_once()
            call_kwargs = mock_closed.call_args.kwargs
            assert call_kwargs["slack_thread_ts"] == "111.222"
            assert call_kwargs["slack_channel"] == "#test"

    async def test_no_thread_reply_when_no_thread_ts(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """If question has no slack_thread_ts, no closure notification is sent."""
        q = Question(
            title="No Thread Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        # No slack_thread_ts set
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_closed", new_callable=AsyncMock) as mock_closed:
            r = await client.post(
                f"/api/v1/questions/{q.id}/close",
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_closed.assert_not_called()


# ---------------------------------------------------------------------------
# Model: slack_thread_ts column
# ---------------------------------------------------------------------------

class TestSlackThreadTsColumn:
    """The Question model should have a slack_thread_ts column."""

    async def test_question_has_slack_thread_ts_column(self, db: AsyncSession):
        """Questions should have a nullable slack_thread_ts string column."""
        q = Question(
            title="Column Test", body="B",
            created_by_id=uuid.uuid4(),  # Will fail FK but tests column existence
        )
        # Access the attribute — will fail with AttributeError if column doesn't exist
        assert hasattr(q, "slack_thread_ts")
        assert q.slack_thread_ts is None

    async def test_question_response_includes_slack_thread_ts(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """GET /questions/{id} response should NOT expose slack_thread_ts (internal field)."""
        q = Question(
            title="Schema Test", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        q.slack_thread_ts = "123.456"
        db.add(q)
        await db.flush()

        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        # slack_thread_ts is an internal field, should not be in the API response
        assert "slack_thread_ts" not in data
