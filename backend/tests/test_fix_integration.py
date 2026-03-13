"""
Integration tests for the 5 fixes in feat/slack-dm.

Each test exercises the actual user journey through the API,
verifying the fix end-to-end via route calls (not just unit mocks).

Fix A: Slack threading — notify_question_rejected posts to thread
Fix B: Service account visibility — GET question for non-published
Fix C: Worker 409 — tested in worker/ (no backend route test needed)
Fix D: Review comment preserved on resubmit
Fix E: Admin queue pending bucket for mixed answer states
Thread lifecycle: publish stores thread_ts → subsequent notifications use it
"""
import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import api_key_header, auth_header


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fix A: Slack threading for question rejection
# ---------------------------------------------------------------------------

class TestFixA_SlackThreadingOnReject:
    """Reject notification uses the question's thread when available."""

    async def test_reject_passes_thread_info_to_slack(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """When a question has slack_thread_ts, rejection posts to that thread."""
        q = Question(
            title="Threaded Reject Q", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        q.slack_channel = "#questions"
        q.slack_thread_ts = "1234567890.111"
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_rejected", new_callable=AsyncMock) as mock_reject:
            r = await client.post(
                f"/api/v1/questions/{q.id}/reject",
                json={"comment": "Vague"},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200

            mock_reject.assert_called_once()
            kwargs = mock_reject.call_args.kwargs
            assert kwargs["slack_channel"] == "#questions"
            assert kwargs["slack_thread_ts"] == "1234567890.111"
            assert kwargs["comment"] == "Vague"

    async def test_reject_without_thread_still_works(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """Questions without thread info still send rejection (to default channel)."""
        q = Question(
            title="No Thread Reject Q", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        with patch("app.api.v1.questions.slack.notify_question_rejected", new_callable=AsyncMock) as mock_reject:
            r = await client.post(
                f"/api/v1/questions/{q.id}/reject",
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200

            mock_reject.assert_called_once()
            kwargs = mock_reject.call_args.kwargs
            assert kwargs["slack_channel"] is None
            assert kwargs["slack_thread_ts"] is None


# ---------------------------------------------------------------------------
# Fix B: Service account can GET non-published questions
# ---------------------------------------------------------------------------

class TestFixB_ServiceAccountVisibility:
    """Service accounts (user_type=service) can view questions in any status."""

    async def test_service_account_can_get_proposed_question(
        self, client: AsyncClient, admin_user: User, service_user: tuple[User, str], db: AsyncSession,
    ):
        """Service account with API key can GET a proposed (non-published) question."""
        user, api_key = service_user

        q = Question(
            title="Proposed Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PROPOSED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=api_key_header(api_key),
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Proposed Q"

    async def test_service_account_can_get_in_review_question(
        self, client: AsyncClient, admin_user: User, service_user: tuple[User, str], db: AsyncSession,
    ):
        """Service account can GET a question in in_review status."""
        user, api_key = service_user

        q = Question(
            title="In Review Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=api_key_header(api_key),
        )
        assert r.status_code == 200
        assert r.json()["title"] == "In Review Q"

    async def test_regular_user_cannot_get_others_proposed_question(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Non-admin human users still cannot see other users' non-published questions."""
        q = Question(
            title="Hidden Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PROPOSED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.get(
            f"/api/v1/questions/{q.id}",
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Fix D: Review comment preserved after answer resubmit
# ---------------------------------------------------------------------------

class TestFixD_ReviewCommentPreserved:
    """Review comment survives answer resubmission."""

    async def test_resubmit_preserves_review_comment(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Full journey: submit → changes_requested with comment → resubmit → comment still there."""
        # Setup: published question
        q = Question(
            title="Comment Test Q", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # Create and submit answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 201
        a_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/answers/{a_id}/submit",
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 200

        # Create review and request changes with comment
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        review_id = r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "changes_requested",
            "comment": "Please expand on section 2",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        # Verify comment is set
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.json()["comment"] == "Please expand on section 2"

        # Edit and resubmit
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Expanded answer with more detail on section 2",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/answers/{a_id}/submit",
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 200

        # Verify: review verdict is preserved (not reset) along with comment
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        review_data = r.json()
        assert review_data["verdict"] == "changes_requested"  # verdict preserved
        assert review_data["comment"] == "Please expand on section 2"  # comment preserved


# ---------------------------------------------------------------------------
# Fix E: Admin queue pending bucket
# ---------------------------------------------------------------------------

class TestFixE_AdminQueuePendingBucket:
    """Published questions with in-progress answers land in the pending bucket."""

    async def test_full_journey_mixed_answers(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User, db: AsyncSession,
    ):
        """
        Full journey:
        1. Create and publish question
        2. Submit two answers
        3. Approve one answer
        4. Leave the other under_review
        5. Verify question is in pending bucket (not published)
        6. Approve second answer
        7. Verify question moves to published bucket
        """
        # 1. Create and publish question
        r = await client.post("/api/v1/questions", json={
            "title": "Multi Answer Q", "body": "A question with multiple answers",
        }, headers=auth_header(author_user))
        assert r.status_code == 201
        q_id = r.json()["id"]

        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        r = await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))
        assert r.json()["status"] == "published"

        # 2. Submit two answers
        r1 = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Answer one",
        }, headers=auth_header(respondent_user))
        a1_id = r1.json()["id"]
        await client.post(f"/api/v1/answers/{a1_id}/submit", headers=auth_header(respondent_user))

        r2 = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Answer two",
        }, headers=auth_header(respondent_user))
        a2_id = r2.json()["id"]
        await client.post(f"/api/v1/answers/{a2_id}/submit", headers=auth_header(respondent_user))

        # 3. Create reviews for both answers
        rev1 = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a1_id,
        }, headers=auth_header(reviewer_user))
        rev1_id = rev1.json()["id"]

        rev2 = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a2_id,
        }, headers=auth_header(reviewer_user))
        rev2_id = rev2.json()["id"]

        # 4. Approve answer 1, leave answer 2 under review
        await client.patch(f"/api/v1/reviews/{rev1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Verify answer 1 is approved
        r = await client.get(f"/api/v1/answers/{a1_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"

        # Answer 2 is still under_review (submitted)
        r = await client.get(f"/api/v1/answers/{a2_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] in ("submitted", "under_review")

        # 5. Check admin queue: question should be in PENDING (not published)
        queue = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        data = queue.json()
        pending_ids = [item["id"] for item in data["pending"]]
        published_ids = [item["id"] for item in data["published"]]
        assert q_id in pending_ids, f"Expected {q_id} in pending, got {pending_ids}"
        assert q_id not in published_ids

        # Verify counts
        pending_item = next(item for item in data["pending"] if item["id"] == q_id)
        assert pending_item["approved_count"] == 1
        assert pending_item["pending_count"] >= 1

        # 6. Approve answer 2
        await client.patch(f"/api/v1/reviews/{rev2_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # 7. Now question should move to PUBLISHED bucket (no more pending answers)
        queue = await client.get("/api/v1/questions/admin-queue", headers=auth_header(admin_user))
        data = queue.json()
        pending_ids = [item["id"] for item in data["pending"]]
        published_ids = [item["id"] for item in data["published"]]
        assert q_id not in pending_ids
        assert q_id in published_ids


# ---------------------------------------------------------------------------
# Slack Thread Lifecycle: full data-flow test across multiple requests
# ---------------------------------------------------------------------------

class TestSlackThreadLifecycle:
    """Verify thread_ts persists across requests: publish → submit → review → reject.

    This tests the ACTUAL data flow — publish stores thread_ts in the DB,
    then subsequent requests read it back and pass it to Slack notifications.
    Slack functions are mocked, but the DB round-trip is real.
    """

    async def test_publish_then_answer_submit_uses_stored_thread(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, db: AsyncSession,
    ):
        """
        1. Publish question → Slack mock returns thread_ts → stored on question
        2. Submit answer → verify notify_answer_submitted receives the stored thread_ts
        """
        # Create question through to in_review
        q = Question(
            title="Thread Lifecycle Q", body="Testing thread data persistence",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        # Step 1: Publish — mock Slack returns thread_ts
        with patch("app.api.v1.questions.slack.notify_question_published",
                    new_callable=AsyncMock, return_value=("9999.8888", "#test-channel")) as mock_pub, \
             patch("app.api.v1.questions.update_question_embedding", new_callable=AsyncMock), \
             patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock):
            r = await client.post(
                f"/api/v1/questions/{q.id}/publish",
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200
            mock_pub.assert_called_once()

        # Verify thread_ts is stored in DB (real DB, not mocked)
        await db.refresh(q)
        assert q.slack_thread_ts == "9999.8888"
        assert q.slack_channel == "#test-channel"

        # Step 2: Submit answer — verify notification uses the STORED thread data
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer to the question",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 201
        a_id = r.json()["id"]

        with patch("app.api.v1.answers.slack.notify_answer_submitted",
                    new_callable=AsyncMock) as mock_submit:
            r = await client.post(
                f"/api/v1/answers/{a_id}/submit",
                headers=auth_header(respondent_user),
            )
            assert r.status_code == 200
            mock_submit.assert_called_once()

            # THE KEY ASSERTION: thread data from publish is passed to answer submit
            kwargs = mock_submit.call_args.kwargs
            assert kwargs["slack_channel"] == "#test-channel", \
                f"Expected #test-channel, got {kwargs.get('slack_channel')}"
            assert kwargs["slack_thread_ts"] == "9999.8888", \
                f"Expected 9999.8888, got {kwargs.get('slack_thread_ts')}"

    async def test_publish_then_review_verdict_uses_stored_thread(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User, db: AsyncSession,
    ):
        """
        1. Publish question → thread_ts stored
        2. Submit answer
        3. Review answer → verify notify_review_verdict receives stored thread_ts
        """
        q = Question(
            title="Review Thread Q", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        # Publish with mocked Slack
        with patch("app.api.v1.questions.slack.notify_question_published",
                    new_callable=AsyncMock, return_value=("1111.2222", "#reviews")) as mock_pub, \
             patch("app.api.v1.questions.update_question_embedding", new_callable=AsyncMock), \
             patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock):
            await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))

        # Create and submit answer (no need to mock Slack here — it's fire-and-forget)
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer text",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        with patch("app.api.v1.answers.slack.notify_answer_submitted", new_callable=AsyncMock):
            await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Create review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Submit verdict — verify Slack thread data flows through
        with patch("app.api.v1.reviews.slack.notify_review_verdict",
                    new_callable=AsyncMock) as mock_verdict, \
             patch("app.api.v1.reviews.slack.notify_answer_approved", new_callable=AsyncMock), \
             patch("app.api.v1.reviews.slack.notify_changes_requested_dm", new_callable=AsyncMock):
            r = await client.patch(f"/api/v1/reviews/{review_id}", json={
                "verdict": "approved",
            }, headers=auth_header(reviewer_user))
            assert r.status_code == 200

            mock_verdict.assert_called_once()
            kwargs = mock_verdict.call_args.kwargs
            assert kwargs["slack_channel"] == "#reviews"
            assert kwargs["slack_thread_ts"] == "1111.2222"

    async def test_publish_then_reject_uses_stored_thread(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """
        1. Publish question → thread_ts stored
        2. Reject question → verify notify_question_rejected receives stored thread_ts

        Note: A question can be published, then go back to in_review via a workflow,
        but in this test we set status directly to simulate the scenario.
        """
        q = Question(
            title="Reject Thread Q", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        # Publish — store thread
        with patch("app.api.v1.questions.slack.notify_question_published",
                    new_callable=AsyncMock, return_value=("3333.4444", "#qa")) as mock_pub, \
             patch("app.api.v1.questions.update_question_embedding", new_callable=AsyncMock), \
             patch("app.api.v1.questions.worker_client.trigger_scaffold_options", new_callable=AsyncMock):
            await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))

        await db.refresh(q)
        assert q.slack_thread_ts == "3333.4444"

        # Now simulate question going back to in_review (manually set status)
        q.status = QuestionStatus.IN_REVIEW.value
        await db.flush()

        # Reject — should use the stored thread
        with patch("app.api.v1.questions.slack.notify_question_rejected",
                    new_callable=AsyncMock) as mock_reject:
            r = await client.post(
                f"/api/v1/questions/{q.id}/reject",
                json={"comment": "Needs rework"},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 200

            mock_reject.assert_called_once()
            kwargs = mock_reject.call_args.kwargs
            assert kwargs["slack_channel"] == "#qa"
            assert kwargs["slack_thread_ts"] == "3333.4444"
            assert kwargs["comment"] == "Needs rework"


# ---------------------------------------------------------------------------
# Slack SDK-level test: verify chat_postMessage receives thread_ts
# ---------------------------------------------------------------------------

class TestSlackSDKThreading:
    """Test at the Slack SDK mock level — NOT mocking our notification functions,
    but mocking the underlying AsyncWebClient. This catches bugs in _post_message
    and the notification functions' if/elif thread logic.
    """

    async def test_notify_answer_submitted_calls_sdk_with_thread_ts(self):
        """When thread data is provided, chat_postMessage must receive thread_ts."""
        from unittest.mock import MagicMock
        from app.services import slack

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.get = lambda key, default=None: {"ts": "reply.ts"}.get(key, default)
        mock_client.chat_postMessage.return_value = mock_response

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_answer_submitted(
                question_title="What is tacit knowledge?",
                question_id="q-123",
                answer_id="a-456",
                author_name="Respondent User",
                slack_channel="#testing-k",
                slack_thread_ts="9999.8888",
            )

        # Verify chat_postMessage was called exactly ONCE (no double-posting)
        assert mock_client.chat_postMessage.call_count == 1, \
            f"Expected 1 call, got {mock_client.chat_postMessage.call_count}"

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        # Verify thread_ts is passed to the SDK
        assert call_kwargs["thread_ts"] == "9999.8888", \
            f"Expected thread_ts='9999.8888', got {call_kwargs.get('thread_ts')}"
        assert call_kwargs["channel"] == "#testing-k"
        assert "Answer submitted" in call_kwargs["text"]

    async def test_notify_answer_submitted_without_thread_posts_to_default(self):
        """When no thread data, posts to default channel WITHOUT thread_ts."""
        from unittest.mock import MagicMock
        from app.services import slack

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.get = lambda key, default=None: {"ts": "msg.ts"}.get(key, default)
        mock_client.chat_postMessage.return_value = mock_response

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack, "_channel", return_value="#default-channel"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_answer_submitted(
                question_title="Q",
                question_id="q-1",
                answer_id="a-1",
                author_name="User",
                slack_channel=None,
                slack_thread_ts=None,
            )

        assert mock_client.chat_postMessage.call_count == 1
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        # Should post to default channel, thread_ts should be None (not threaded)
        assert call_kwargs["channel"] == "#default-channel"
        assert call_kwargs.get("thread_ts") is None

    async def test_notify_review_verdict_calls_sdk_with_thread_ts(self):
        """Review verdict notification uses thread_ts at the SDK level."""
        from unittest.mock import MagicMock
        from app.services import slack

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.get = lambda key, default=None: {"ts": "reply.ts"}.get(key, default)
        mock_client.chat_postMessage.return_value = mock_response

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack, "_mention_or_name", new_callable=AsyncMock, return_value="Respondent"), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):
            await slack.notify_review_verdict(
                question_title="What is tacit knowledge?",
                answer_id="a-456",
                verdict="approved",
                reviewer_name="Reviewer User",
                author_email="respondent@test.com",
                author_name="Respondent User",
                comment="Great answer!",
                slack_channel="#testing-k",
                slack_thread_ts="9999.8888",
            )

        assert mock_client.chat_postMessage.call_count == 1
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "9999.8888"
        assert call_kwargs["channel"] == "#testing-k"

    async def test_full_thread_lifecycle_at_sdk_level(self):
        """Complete flow: publish creates thread → answer submit uses thread_ts.
        All at the SDK mock level, verifying actual chat_postMessage calls.
        """
        from unittest.mock import MagicMock
        from app.services import slack

        mock_client = AsyncMock()
        mock_response = MagicMock()
        # Simulate Slack returning a thread_ts for the first message
        resp_data = {"ts": "1709900000.000001", "ok": True, "channel": "C_TESTING_K"}
        mock_response.__getitem__ = lambda self, key: resp_data[key]
        mock_response.get = lambda key, default=None: resp_data.get(key, default)
        mock_client.chat_postMessage.return_value = mock_response

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#testing-k"), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):

            # Step 1: Publish question — creates thread
            thread_ts, channel = await slack.notify_question_published(
                question_title="What is tacit knowledge?",
                question_id="q-123",
                question_body="Explain tacit knowledge in software engineering.",
                publisher_name="Admin User",
            )

        assert thread_ts == "1709900000.000001"
        assert channel == "C_TESTING_K"  # resolved channel ID from API response
        # Publish makes 2 calls: parent message + body reply
        assert mock_client.chat_postMessage.call_count == 2
        parent_call = mock_client.chat_postMessage.call_args_list[0].kwargs
        body_call = mock_client.chat_postMessage.call_args_list[1].kwargs
        # Parent has no thread_ts (it IS the thread)
        assert parent_call.get("thread_ts") is None
        # Body reply has thread_ts
        assert body_call["thread_ts"] == "1709900000.000001"

        # Reset mock for next call
        mock_client.chat_postMessage.reset_mock()

        with patch.object(slack, "_is_enabled", return_value=True), \
             patch.object(slack, "_channel", return_value="#testing-k"), \
             patch.object(slack, "_get_client", return_value=mock_client), \
             patch.object(slack.settings, "FRONTEND_URL", "http://localhost:5173"):

            # Step 2: Answer submitted — should use stored thread_ts
            await slack.notify_answer_submitted(
                question_title="What is tacit knowledge?",
                question_id="q-123",
                answer_id="a-456",
                author_name="Respondent User",
                slack_channel=channel,
                slack_thread_ts=thread_ts,
            )

        # Should make exactly 1 call, to the thread
        assert mock_client.chat_postMessage.call_count == 1
        submit_call = mock_client.chat_postMessage.call_args.kwargs
        assert submit_call["thread_ts"] == "1709900000.000001", \
            f"Expected thread_ts from publish, got {submit_call.get('thread_ts')}"
        assert submit_call["channel"] == "C_TESTING_K"  # uses resolved channel ID from publish
        assert "Answer submitted" in submit_call["text"]
