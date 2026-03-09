"""Tests for Plan B: Targeted Slack Notifications & DMs.

Tests cover:
1. _send_dm infrastructure (conversations.open + chat.postMessage)
2. DM on respondent assignment
3. DM on changes_requested review verdict
4. Error handling and graceful degradation

These tests are written TDD-style — they will FAIL until Plan B is implemented.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from slack_sdk.errors import SlackApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import User
from app.services import slack
from tests.conftest import auth_header


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_slack_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.__getitem__ = lambda self, key: data[key]
    resp.get = data.get
    return resp


@pytest.fixture(autouse=True)
def _clear_slack_cache():
    slack._slack_user_cache.clear()
    yield
    slack._slack_user_cache.clear()


# ---------------------------------------------------------------------------
# Unit tests: _send_dm
# ---------------------------------------------------------------------------

class TestSendDm:
    """_send_dm opens a conversation with a Slack user and posts a message."""

    async def test_send_dm_opens_conversation_and_posts(self):
        """Opens a DM channel via conversations.open, then posts to it."""
        mock_client = AsyncMock()
        mock_client.conversations_open.return_value = _mock_slack_response({
            "channel": {"id": "D12345"},
        })
        mock_client.chat_postMessage.return_value = _mock_slack_response({
            "ts": "999.888", "ok": True,
        })

        with patch.object(slack, "_get_client", return_value=mock_client):
            await slack._send_dm("U12345", "Hello from the platform!")

        mock_client.conversations_open.assert_called_once_with(users="U12345")
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "D12345"
        assert "Hello from the platform!" in call_kwargs["text"]

    async def test_send_dm_handles_conversation_open_error(self):
        """If conversations.open fails, no message is posted, no exception raised."""
        mock_client = AsyncMock()
        error_resp = MagicMock()
        error_resp.get.return_value = "user_not_found"
        mock_client.conversations_open.side_effect = SlackApiError(
            message="user_not_found", response=error_resp,
        )

        with patch.object(slack, "_get_client", return_value=mock_client):
            # Should not raise
            await slack._send_dm("U_INVALID", "Hello")

        mock_client.chat_postMessage.assert_not_called()

    async def test_send_dm_handles_post_error(self):
        """If chat.postMessage fails after opening, no exception propagated."""
        mock_client = AsyncMock()
        mock_client.conversations_open.return_value = _mock_slack_response({
            "channel": {"id": "D12345"},
        })
        mock_client.chat_postMessage.side_effect = ConnectionError("network down")

        with patch.object(slack, "_get_client", return_value=mock_client):
            # Should not raise
            await slack._send_dm("U12345", "Hello")

    async def test_send_dm_handles_generic_exception(self):
        """Any unexpected exception is caught."""
        mock_client = AsyncMock()
        mock_client.conversations_open.side_effect = RuntimeError("unexpected")

        with patch.object(slack, "_get_client", return_value=mock_client):
            await slack._send_dm("U12345", "Hello")


# ---------------------------------------------------------------------------
# Unit tests: notify_respondent_assigned
# ---------------------------------------------------------------------------

class TestNotifyRespondentAssigned:
    """DM sent to the assigned respondent with question details."""

    async def test_sends_dm_with_question_info(self):
        """DM is sent via _send_dm with question title and assigner name."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_RESP"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_respondent_assigned(
                question_title="Important Question",
                question_id="q-123",
                respondent_email="respondent@test.com",
                respondent_name="Respondent User",
                assigner_name="Admin User",
            )

        mock_dm.assert_called_once()
        slack_user_id = mock_dm.call_args[0][0]
        msg = mock_dm.call_args[0][1]
        assert slack_user_id == "U_RESP"
        assert "Important Question" in msg
        assert "Admin User" in msg

    async def test_no_dm_when_no_email(self):
        """If respondent has no email, DM is skipped."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email=None,
                respondent_name="No Email User",
                assigner_name="Admin",
            )

        mock_dm.assert_not_called()

    async def test_no_dm_when_slack_user_not_found(self):
        """If Slack user lookup returns None, DM is skipped."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value=None), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email="unknown@test.com",
                respondent_name="Unknown User",
                assigner_name="Admin",
            )

        mock_dm.assert_not_called()

    async def test_no_dm_when_disabled(self):
        """When Slack is disabled, no DM attempt."""
        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email="r@test.com",
                respondent_name="R",
                assigner_name="Admin",
            )

        mock_dm.assert_not_called()

    async def test_dm_includes_link_when_frontend_url_set(self):
        """DM should contain a clickable link to the question."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_RESP"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm, \
             patch.object(slack.settings, "FRONTEND_URL", "https://app.example.com"):
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-123",
                respondent_email="r@test.com",
                respondent_name="R",
                assigner_name="Admin",
            )

        msg = mock_dm.call_args[0][1]
        assert "https://app.example.com/questions/q-123" in msg


# ---------------------------------------------------------------------------
# Unit tests: notify_respondent_assigned — Slack thread mention
# ---------------------------------------------------------------------------

class TestRespondentAssignedThreadMention:
    """When a question has a Slack thread, assigning a respondent posts a thread reply."""

    async def test_thread_reply_posted_with_mention(self):
        """Thread reply is posted mentioning the respondent when thread info provided."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_RESP"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email="r@test.com",
                respondent_name="Respondent",
                assigner_name="Admin",
                slack_channel="C123",
                slack_thread_ts="1234.5678",
            )

        # _post_message called for the thread reply
        thread_calls = [c for c in mock_post.call_args_list if c.kwargs.get("thread_ts") == "1234.5678"]
        assert len(thread_calls) == 1
        thread_text = thread_calls[0].args[1]
        assert "<@U_RESP>" in thread_text
        assert "Admin" in thread_text

    async def test_no_thread_reply_without_thread_info(self):
        """No thread reply when slack_channel/slack_thread_ts not provided."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_RESP"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email="r@test.com",
                respondent_name="Respondent",
                assigner_name="Admin",
                # No slack_channel/slack_thread_ts
            )

        mock_post.assert_not_called()

    async def test_thread_reply_uses_display_name_when_no_email(self):
        """Thread reply falls back to display name when email is None."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock), \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email=None,
                respondent_name="No Email User",
                assigner_name="Admin",
                slack_channel="C123",
                slack_thread_ts="1234.5678",
            )

        thread_calls = [c for c in mock_post.call_args_list if c.kwargs.get("thread_ts") == "1234.5678"]
        assert len(thread_calls) == 1
        thread_text = thread_calls[0].args[1]
        assert "No Email User" in thread_text

    async def test_dm_and_thread_reply_independent(self):
        """DM failure doesn't prevent thread reply from being posted."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value=None), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm, \
             patch.object(slack, "_post_message", new_callable=AsyncMock) as mock_post:
            await slack.notify_respondent_assigned(
                question_title="Q",
                question_id="q-1",
                respondent_email="unknown@test.com",
                respondent_name="Unknown",
                assigner_name="Admin",
                slack_channel="C123",
                slack_thread_ts="1234.5678",
            )

        # DM not sent (user lookup failed)
        mock_dm.assert_not_called()
        # Thread reply still posted
        thread_calls = [c for c in mock_post.call_args_list if c.kwargs.get("thread_ts") == "1234.5678"]
        assert len(thread_calls) == 1

    async def test_route_passes_thread_info(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """assign-respondent route passes slack_channel and slack_thread_ts to notification."""
        q = Question(
            title="Thread Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            slack_channel="C_THREAD",
            slack_thread_ts="9999.0001",
        )
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_respondent_assigned", new_callable=AsyncMock) as mock_notify:
            r = await client.post(
                f"/api/v1/questions/{q.id}/assign-respondent",
                json={"user_id": str(respondent_user.id)},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            call_kwargs = mock_notify.call_args.kwargs
            assert call_kwargs["slack_channel"] == "C_THREAD"
            assert call_kwargs["slack_thread_ts"] == "9999.0001"


# ---------------------------------------------------------------------------
# Unit tests: notify_changes_requested_dm
# ---------------------------------------------------------------------------

class TestNotifyChangesRequestedDm:
    """DM sent to the answer author when changes are requested."""

    async def test_sends_dm_to_author(self):
        """DM is sent to the answer author with review details."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_AUTH"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_changes_requested_dm(
                question_title="My Question",
                question_id="q-1",
                answer_id="a-1",
                author_email="author@test.com",
                author_name="Author",
                reviewer_name="Reviewer",
                comment="Please fix section 3",
            )

        mock_dm.assert_called_once()
        msg = mock_dm.call_args[0][1]
        assert "My Question" in msg
        assert "Please fix section 3" in msg
        assert "Reviewer" in msg

    async def test_dm_without_comment(self):
        """DM is sent even without a reviewer comment."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_lookup_slack_user", new_callable=AsyncMock, return_value="U_AUTH"), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_changes_requested_dm(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_email="author@test.com",
                author_name="Author",
                reviewer_name="Reviewer",
                comment=None,
            )

        mock_dm.assert_called_once()

    async def test_no_dm_when_no_email(self):
        """If author has no email, DM is skipped."""
        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_changes_requested_dm(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_email=None,
                author_name="Author",
                reviewer_name="Reviewer",
                comment="Fix it",
            )

        mock_dm.assert_not_called()

    async def test_no_dm_when_disabled(self):
        """When Slack is disabled, no DM."""
        with patch.object(slack, "_is_enabled", return_value=False), \
             patch.object(slack, "_send_dm", new_callable=AsyncMock) as mock_dm:
            await slack.notify_changes_requested_dm(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_email="a@test.com",
                author_name="A",
                reviewer_name="R",
                comment="Fix",
            )

        mock_dm.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: Route-level DM triggers
# ---------------------------------------------------------------------------

class TestDmRouteIntegration:
    """Verify routes trigger DM functions at the correct points."""

    async def test_assign_respondent_triggers_dm(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """POST /questions/{id}/assign-respondent triggers a DM to the respondent."""
        q = Question(
            title="DM Test Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_respondent_assigned", new_callable=AsyncMock) as mock_notify:
            r = await client.post(
                f"/api/v1/questions/{q.id}/assign-respondent",
                json={"user_id": str(respondent_user.id)},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args.kwargs
            assert call_kwargs["respondent_email"] == respondent_user.email
            assert call_kwargs["respondent_name"] == respondent_user.display_name

    async def test_changes_requested_review_triggers_dm(
        self, client: AsyncClient, reviewer_user: User, respondent_user: User,
        admin_user: User, db: AsyncSession,
    ):
        """Submitting a changes_requested verdict triggers a DM to the answer author."""
        q = Question(
            title="DM Review Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="My answer", status=AnswerStatus.SUBMITTED.value,
            current_version=1,
        )
        db.add(a)
        await db.flush()

        # Create a review
        review_r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        with patch("app.api.v1.reviews.slack.notify_review_verdict", new_callable=AsyncMock), \
             patch("app.api.v1.reviews.slack.notify_revision_requested", new_callable=AsyncMock), \
             patch("app.api.v1.reviews.slack.notify_changes_requested_dm", new_callable=AsyncMock) as mock_dm:
            r = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": "changes_requested", "comment": "Fix section 3"},
                headers=auth_header(reviewer_user),
            )
            assert r.status_code == 200
            mock_dm.assert_called_once()
            call_kwargs = mock_dm.call_args.kwargs
            assert call_kwargs["author_email"] == respondent_user.email
            assert call_kwargs["comment"] == "Fix section 3"

    async def test_approved_review_does_not_trigger_dm(
        self, client: AsyncClient, reviewer_user: User, respondent_user: User,
        admin_user: User, db: AsyncSession,
    ):
        """An approved verdict should NOT trigger a changes_requested DM."""
        q = Question(
            title="Approved No DM Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="A", status=AnswerStatus.SUBMITTED.value,
            current_version=1,
        )
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        with patch("app.api.v1.reviews.slack.notify_review_verdict", new_callable=AsyncMock), \
             patch("app.api.v1.reviews.slack.notify_answer_approved", new_callable=AsyncMock), \
             patch("app.api.v1.reviews.slack.notify_changes_requested_dm", new_callable=AsyncMock) as mock_dm:
            r = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": "approved"},
                headers=auth_header(reviewer_user),
            )
            assert r.status_code == 200
            mock_dm.assert_not_called()
