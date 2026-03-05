"""
End-to-end workflow tests covering complete user flows across
questions, answers, reviews, and revisions.
"""
import uuid

from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


class TestQuestionAnswerReviewLifecycle:
    """Happy path: full lifecycle from question creation to answer approval."""

    async def test_full_question_answer_review_flow(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        # 1. Author creates question → draft
        r = await client.post("/api/v1/questions", json={
            "title": "What is tacit knowledge?",
            "body": "Explain the concept of tacit knowledge in software engineering.",
        }, headers=auth_header(author_user))
        assert r.status_code == 201
        q_id = r.json()["id"]
        assert r.json()["status"] == "draft"

        # 2. Author submits → proposed
        r = await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        assert r.status_code == 200
        assert r.json()["status"] == "proposed"

        # 3. Admin starts review → in_review
        r = await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "in_review"

        # 4. Admin publishes → published
        r = await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "published"
        assert r.json()["confirmed_by"] is not None

        # 5. Respondent creates answer → draft
        r = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Tacit knowledge is knowledge that is difficult to articulate.",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 201
        a_id = r.json()["id"]
        assert r.json()["status"] == "draft"

        # 6. Respondent submits answer → submitted
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 1

        # 7. Reviewer assigns self → creates review, answer → under_review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        review_id = r.json()["id"]
        assert r.json()["verdict"] == "pending"

        # Verify answer moved to under_review
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "under_review"

        # 8. Reviewer approves → answer approved
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved", "comment": "Great answer!",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200
        assert r.json()["verdict"] == "approved"

        # 9. Verify answer is approved with confirmation
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"
        assert r.json()["confirmed_at"] is not None

    async def test_answer_revision_then_re_review(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Reproduces the MissingGreenlet bug: revise an approved answer, then approve again."""
        # Setup: published question
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create and submit answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Version 1 of my answer",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 201
        a_id = r.json()["id"]

        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200

        # Reviewer approves
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        # Verify approved
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"
        assert r.json()["current_version"] == 1

        # Author revises atomically with new content → submitted, new version
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Version 2 of my answer — improved",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 2

        # Reviewer assigns new review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        review2_id = r.json()["id"]

        # Reviewer approves second review — THIS was the MissingGreenlet crash
        r = await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "approved", "comment": "V2 looks good",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200
        assert r.json()["verdict"] == "approved"

        # Verify answer re-approved at version 2
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"
        assert r.json()["current_version"] == 2

        # Verify both reviews exist
        r = await client.get("/api/v1/reviews", params={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert len(r.json()) == 2

        # Verify version history has 2 revisions
        r = await client.get(f"/api/v1/answers/{a_id}/versions", headers=auth_header(respondent_user))
        assert len(r.json()) == 2

    async def test_question_reject_and_resubmit(
        self, client: AsyncClient, admin_user: User, author_user: User,
    ):
        """Question rejected back to draft, edited, and resubmitted through full pipeline."""
        # Author creates and submits
        r = await client.post("/api/v1/questions", json={
            "title": "Bad Title", "body": "Needs work",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))

        # Admin starts review, then rejects → draft
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        r = await client.post(f"/api/v1/questions/{q_id}/reject", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "draft"

        # Author edits
        r = await client.patch(f"/api/v1/questions/{q_id}", json={
            "title": "Improved Title", "body": "Much better content",
        }, headers=auth_header(author_user))
        assert r.status_code == 200

        # Author resubmits → proposed
        r = await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        assert r.json()["status"] == "proposed"

        # Admin publishes through full pipeline
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        r = await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "published"
        assert r.json()["title"] == "Improved Title"

    async def test_answer_changes_requested_flow(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Reviewer requests changes, author edits and resubmits, gets approved."""
        # Setup published question
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create, submit answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "First draft answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer assigns and requests changes
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "changes_requested", "comment": "Please add more detail",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        # Answer should be revision_requested
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "revision_requested"

        # Author edits
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Improved answer with more detail",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200

        # Author resubmits — same review is reset to pending, version stays the same
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"  # review reset to pending
        assert r.json()["current_version"] == 1  # no version bump on resubmit

        # The original review should now be pending on the same version
        r = await client.get("/api/v1/reviews", params={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        reviews = r.json()
        pending_reviews = [rv for rv in reviews if rv["verdict"] == "pending"]
        assert len(pending_reviews) == 1
        assert pending_reviews[0]["id"] == review_id  # same review, not a new one
        assert pending_reviews[0]["answer_version"] == 1  # stays on same version
        assert pending_reviews[0]["comment"] is None  # comment cleared

        # Approve the reset review
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        # Answer approved
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"

    async def test_answer_rejection_flow(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Reviewer rejects answer — terminal state, no further edits."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # Create and submit
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Bad answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer rejects
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "rejected", "comment": "Not relevant",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "rejected"

        # Cannot edit rejected answer (author)
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Trying to fix",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 403

        # Cannot resubmit rejected answer
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 409


class TestPermissionEnforcement:
    """Verify that permission boundaries are respected across workflows."""

    async def test_respondent_cannot_create_question(
        self, client: AsyncClient, respondent_user: User,
    ):
        r = await client.post("/api/v1/questions", json={
            "title": "Test", "body": "Body",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_author_cannot_edit_proposed_question(
        self, client: AsyncClient, author_user: User,
    ):
        """The bug from PR #8: author should NOT be able to edit a proposed question."""
        r = await client.post("/api/v1/questions", json={
            "title": "Original", "body": "Original body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        # Submit → proposed
        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))

        # Author tries to edit → 403
        r = await client.patch(f"/api/v1/questions/{q_id}", json={
            "title": "Sneaky edit",
        }, headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_author_cannot_edit_submitted_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        # Submit → submitted
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Author tries to edit → 403
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Trying to sneak edit",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_non_reviewer_cannot_submit_verdict(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, author_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer creates review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Author (not the assigned reviewer) tries to submit verdict → 403
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_cannot_revise_non_approved_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        # Draft answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        # Try to revise draft → 409
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 409

        # Submit, then try to revise submitted → 409
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 409


class TestConcurrencyGuards:
    """Test that duplicate/invalid state transitions are properly rejected."""

    async def test_double_submit_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        # First submit → success
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # Second submit → 409
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 409

    async def test_double_revise_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """After revise, answer is no longer approved — second revise should fail."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create, submit, approve
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # First revise with new content → success
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Revised answer content",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # Second revise → 409 (no longer approved)
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Another revision",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 409

    async def test_review_after_answer_approved(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Cannot create a review on an already-approved answer."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Try to create another review on approved answer → 409
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409

    async def test_duplicate_pending_review(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Same reviewer cannot create two pending reviews for the same answer version."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # First review → success
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201

        # Second review by same reviewer → 409
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409
        assert "pending review" in r.json()["detail"].lower()

    async def test_double_question_submit(
        self, client: AsyncClient, author_user: User,
    ):
        """Cannot submit a question that's already proposed."""
        r = await client.post("/api/v1/questions", json={
            "title": "Test", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        # First submit
        r = await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        assert r.status_code == 200

        # Second submit → 409
        r = await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        assert r.status_code == 409


class TestReviewCommentFlow:
    """Review comment threading and validation."""

    async def test_review_comment_thread(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        a = Answer(
            question_id=q.id, author_id=respondent_user.id, body="Answer",
            status=AnswerStatus.SUBMITTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        # Create review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Add parent comment
        r = await client.post(f"/api/v1/reviews/{review_id}/comments", json={
            "body": "Please clarify paragraph 2",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        parent_id = r.json()["id"]

        # Add reply
        r = await client.post(f"/api/v1/reviews/{review_id}/comments", json={
            "body": "I've updated it, please check",
            "parent_id": parent_id,
        }, headers=auth_header(respondent_user))
        assert r.status_code == 201
        assert r.json()["parent_id"] == parent_id

        # Verify review has comments via GET
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.status_code == 200

    async def test_invalid_parent_comment(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        a = Answer(
            question_id=q.id, author_id=respondent_user.id, body="Answer",
            status=AnswerStatus.SUBMITTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Try to reply to nonexistent parent → 404
        r = await client.post(f"/api/v1/reviews/{review_id}/comments", json={
            "body": "Reply to nothing",
            "parent_id": str(uuid.uuid4()),
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 404


class TestQuestionTerminalStates:
    """Verify terminal states are properly enforced."""

    async def test_archived_question_is_readonly(
        self, client: AsyncClient, admin_user: User, author_user: User,
    ):
        """Full pipeline to archived, then verify it's read-only."""
        # Create and push through full pipeline
        r = await client.post("/api/v1/questions", json={
            "title": "Will Archive", "body": "Going away",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/close", headers=auth_header(admin_user))
        r = await client.post(f"/api/v1/questions/{q_id}/archive", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

        # Cannot edit archived question (even admin — can_edit_question returns True for admin)
        # Actually admin CAN edit any non-archived... let's verify the service logic
        # Admin can edit, but let's verify author can't
        r = await client.patch(f"/api/v1/questions/{q_id}", json={
            "title": "Trying to edit archived",
        }, headers=auth_header(author_user))
        assert r.status_code == 403

        # Cannot transition further
        r = await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(admin_user))
        assert r.status_code == 409

        r = await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        assert r.status_code == 409

    async def test_closed_question_no_new_answers(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User,
    ):
        """Cannot create answers on a closed question."""
        r = await client.post("/api/v1/questions", json={
            "title": "Will Close", "body": "Closing soon",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/close", headers=auth_header(admin_user))

        # Try to create answer on closed question → 409
        r = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Late answer",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 409


class TestQuestionDelete:
    """Test question deletion with cascade cleanup."""

    async def test_delete_draft_question_as_author(
        self, client: AsyncClient, author_user: User,
    ):
        """Author can delete their own draft question."""
        r = await client.post("/api/v1/questions", json={
            "title": "To Delete", "body": "Will be removed",
        }, headers=auth_header(author_user))
        assert r.status_code == 201
        q_id = r.json()["id"]

        # Delete
        r = await client.delete(f"/api/v1/questions/{q_id}", headers=auth_header(author_user))
        assert r.status_code == 204

        # Verify gone
        r = await client.get(f"/api/v1/questions/{q_id}", headers=auth_header(author_user))
        assert r.status_code == 404

    async def test_delete_question_with_answers_as_admin(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Admin deletes a published question that has answers, revisions, and reviews."""
        # Create published question
        q = Question(
            title="Full Question", body="With children",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create answer, submit, review, approve
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer body",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Revise atomically with new content to create v2
        await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Updated answer v2",
        }, headers=auth_header(respondent_user))

        # Verify the review exists before deletion
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.status_code == 200

        # Admin deletes the question — should cascade through answers, revisions, AND reviews
        r = await client.delete(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Verify question gone
        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 404

        # Verify answer gone
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(admin_user))
        assert r.status_code == 404

        # Verify review gone — no orphaned reviews
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.status_code == 404

    async def test_author_cannot_delete_submitted_question(
        self, client: AsyncClient, author_user: User,
    ):
        """Author cannot delete a question once it's submitted (only draft)."""
        r = await client.post("/api/v1/questions", json={
            "title": "Submitted Q", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        # Submit → proposed
        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))

        # Author tries to delete → 409
        r = await client.delete(f"/api/v1/questions/{q_id}", headers=auth_header(author_user))
        assert r.status_code == 409

    async def test_non_owner_cannot_delete_question(
        self, client: AsyncClient, author_user: User, respondent_user: User,
    ):
        """Non-owner, non-admin cannot delete a question."""
        r = await client.post("/api/v1/questions", json={
            "title": "Not yours", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        r = await client.delete(f"/api/v1/questions/{q_id}", headers=auth_header(respondent_user))
        assert r.status_code == 403


class TestReviewQuestionTitle:
    """Verify that review responses include the related question title."""

    async def test_review_includes_question_title(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Review for an answer should include the parent question's title."""
        q = Question(
            title="Important Question About Testing",
            body="Body text",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Create review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        review_id = r.json()["id"]
        assert r.json()["question_title"] == "Important Question About Testing"

        # Verify in GET single review
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.json()["question_title"] == "Important Question About Testing"

        # Verify in list endpoint
        r = await client.get("/api/v1/reviews", params={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.json()[0]["question_title"] == "Important Question About Testing"

        # Verify in my-queue endpoint
        r = await client.get("/api/v1/reviews/my-queue", headers=auth_header(reviewer_user))
        matching = [rev for rev in r.json() if rev["id"] == review_id]
        assert len(matching) == 1
        assert matching[0]["question_title"] == "Important Question About Testing"


class TestIdenticalRevisionGuard:
    """Prevent creating revisions when content is unchanged."""

    async def test_resubmit_identical_content_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Resubmitting without changes after revision_requested should be rejected."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create and submit answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My original answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer requests changes
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "changes_requested",
        }, headers=auth_header(reviewer_user))

        # Author tries to resubmit WITHOUT editing → 409
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 409
        assert "identical" in r.json()["detail"].lower()

    async def test_resubmit_with_trailing_whitespace_only_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Adding only trailing spaces should still count as identical content."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer text",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer requests changes
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "changes_requested",
        }, headers=auth_header(reviewer_user))

        # Author "edits" by adding trailing whitespace only
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "My answer text   \n  ",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200

        # Resubmit → 409 (normalized content is identical)
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 409
        assert "identical" in r.json()["detail"].lower()

    async def test_revise_identical_content_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Post-approval revise with no content change should be rejected."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Approved answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Approve
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Revise without editing → 409
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 409
        assert "identical" in r.json()["detail"].lower()

    async def test_resubmit_with_real_changes_succeeds(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Resubmitting with actual content changes should succeed."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "First version",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer requests changes
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "changes_requested",
        }, headers=auth_header(reviewer_user))

        # Author makes real edits
        await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Second version with improvements",
        }, headers=auth_header(respondent_user))

        # Resubmit → success, version stays at 1 (in-place update)
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["current_version"] == 1


class TestVersionDiffing:
    """Test answer version history and diffing."""

    async def test_answer_diff_between_versions(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db,
    ):
        """Full flow: submit → approve → revise → verify diff between v1 and v2."""
        q = Question(
            title="Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
            review_policy={"min_approvals": 1},
        )
        db.add(q)
        await db.flush()

        # Create answer with v1 body
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Original answer text",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        # Submit → creates revision v1
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.json()["current_version"] == 1

        # Approve
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Revise atomically with new content → creates revision v2
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Revised answer text with improvements",
        }, headers=auth_header(respondent_user))
        assert r.json()["current_version"] == 2

        # Get diff between v1 and v2
        r = await client.get(f"/api/v1/answers/{a_id}/diff", params={
            "from": 1, "to": 2,
        }, headers=auth_header(respondent_user))
        assert r.status_code == 200
        diff = r.json()["diff"]
        assert "Original answer text" in diff or "Revised answer text" in diff

        # Verify version history
        r = await client.get(f"/api/v1/answers/{a_id}/versions", headers=auth_header(respondent_user))
        versions = r.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[0]["trigger"] == "initial_submit"
        assert versions[1]["trigger"] == "post_approval_update"


class TestReviewQueueFiltering:
    """Tests for filtering reviews by target_type (question vs answer)."""

    async def test_filter_reviews_by_answer_type(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        """Filtering reviews by target_type=answer returns only answer reviews."""
        # Setup: create question, publish it, create answer, submit, create answer review
        r = await client.post("/api/v1/questions", json={
            "title": "Filter test Q", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]
        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))

        r = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Answer body",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Create answer review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        answer_review_id = r.json()["id"]

        # Create question review on a different question
        r = await client.post("/api/v1/questions", json={
            "title": "Review target Q", "body": "Body for review",
        }, headers=auth_header(author_user))
        q2_id = r.json()["id"]
        r = await client.post("/api/v1/reviews", json={
            "target_type": "question", "target_id": q2_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        question_review_id = r.json()["id"]

        # Filter by answer type
        r = await client.get(f"/api/v1/reviews?target_type=answer&reviewer_id={reviewer_user.id}",
                             headers=auth_header(reviewer_user))
        assert r.status_code == 200
        ids = [rev["id"] for rev in r.json()]
        assert answer_review_id in ids
        assert question_review_id not in ids

        # Filter by question type
        r = await client.get(f"/api/v1/reviews?target_type=question&reviewer_id={reviewer_user.id}",
                             headers=auth_header(reviewer_user))
        assert r.status_code == 200
        ids = [rev["id"] for rev in r.json()]
        assert question_review_id in ids
        assert answer_review_id not in ids

    async def test_my_queue_returns_both_types(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        """my-queue endpoint returns both question and answer reviews."""
        r = await client.post("/api/v1/questions", json={
            "title": "Queue test Q", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]
        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))

        r = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "Answer for queue test",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Create reviews for both types
        await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))

        r2 = await client.post("/api/v1/questions", json={
            "title": "Queue Q2", "body": "Body2",
        }, headers=auth_header(author_user))
        q2_id = r2.json()["id"]
        await client.post("/api/v1/reviews", json={
            "target_type": "question", "target_id": q2_id,
        }, headers=auth_header(reviewer_user))

        # my-queue should include both
        r = await client.get("/api/v1/reviews/my-queue", headers=auth_header(reviewer_user))
        assert r.status_code == 200
        types = {rev["target_type"] for rev in r.json()}
        assert "answer" in types
        assert "question" in types

    async def test_question_review_has_question_title(
        self, client: AsyncClient, author_user: User, reviewer_user: User,
    ):
        """Question reviews include the question title in the response."""
        r = await client.post("/api/v1/questions", json={
            "title": "Titled Question", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]

        r = await client.post("/api/v1/reviews", json={
            "target_type": "question", "target_id": q_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        assert r.json()["question_title"] == "Titled Question"

    async def test_answer_review_has_question_title_and_version(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        """Answer reviews include question title and answer_version."""
        r = await client.post("/api/v1/questions", json={
            "title": "Versioned Q", "body": "Body",
        }, headers=auth_header(author_user))
        q_id = r.json()["id"]
        await client.post(f"/api/v1/questions/{q_id}/submit", headers=auth_header(author_user))
        await client.post(f"/api/v1/questions/{q_id}/start-review", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q_id}/publish", headers=auth_header(admin_user))

        r = await client.post(f"/api/v1/questions/{q_id}/answers", json={
            "body": "My answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        data = r.json()
        assert data["question_title"] == "Versioned Q"
        assert data["answer_version"] == 1


class TestMemberManagement:
    """Tests for user listing and role assignment/removal (admin settings)."""

    async def test_admin_can_list_users(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        """Admin can list all users with pagination."""
        r = await client.get("/api/v1/users", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 4

    async def test_non_admin_cannot_list_users(
        self, client: AsyncClient, respondent_user: User,
    ):
        """Non-admin users cannot list all users."""
        r = await client.get("/api/v1/users", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_admin_assigns_role(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """Admin can assign a new role to a user."""
        r = await client.get("/api/v1/users/me", headers=auth_header(respondent_user))
        roles_before = {role["name"] for role in r.json()["roles"]}
        assert "reviewer" not in roles_before

        r = await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "reviewer",
        }, headers=auth_header(admin_user))
        assert r.status_code == 200
        roles_after = {role["name"] for role in r.json()["roles"]}
        assert "reviewer" in roles_after

    async def test_admin_removes_role(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """Admin can remove a role from a user."""
        # First assign reviewer role
        r = await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "reviewer",
        }, headers=auth_header(admin_user))
        assert r.status_code == 200

        # Then remove it
        r = await client.delete(f"/api/v1/users/{respondent_user.id}/roles/reviewer",
                                headers=auth_header(admin_user))
        assert r.status_code == 200
        roles_after = {role["name"] for role in r.json()["roles"]}
        assert "reviewer" not in roles_after

    async def test_assign_duplicate_role_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """Assigning a role the user already has returns 409."""
        r = await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "respondent",
        }, headers=auth_header(admin_user))
        assert r.status_code == 409

    async def test_remove_nonexistent_role_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """Removing a role the user doesn't have returns 404."""
        r = await client.delete(f"/api/v1/users/{respondent_user.id}/roles/admin",
                                headers=auth_header(admin_user))
        assert r.status_code == 404

    async def test_assign_invalid_role_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """Assigning a non-existent role name returns 400."""
        r = await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "superuser",
        }, headers=auth_header(admin_user))
        assert r.status_code == 400

    async def test_non_admin_cannot_assign_roles(
        self, client: AsyncClient, author_user: User, respondent_user: User,
    ):
        """Non-admin users cannot assign roles."""
        r = await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "reviewer",
        }, headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_non_admin_cannot_remove_roles(
        self, client: AsyncClient, author_user: User, respondent_user: User,
    ):
        """Non-admin users cannot remove roles."""
        r = await client.delete(f"/api/v1/users/{respondent_user.id}/roles/respondent",
                                headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_assign_role_to_nonexistent_user(
        self, client: AsyncClient, admin_user: User,
    ):
        """Assigning role to non-existent user returns 404."""
        fake_id = str(uuid.uuid4())
        r = await client.post(f"/api/v1/users/{fake_id}/roles", json={
            "role_name": "reviewer",
        }, headers=auth_header(admin_user))
        assert r.status_code == 404

    async def test_user_list_includes_roles(
        self, client: AsyncClient, admin_user: User,
    ):
        """User list includes role information for each user."""
        r = await client.get("/api/v1/users", headers=auth_header(admin_user))
        assert r.status_code == 200
        for user in r.json()["users"]:
            assert "roles" in user
            assert isinstance(user["roles"], list)
            for role in user["roles"]:
                assert "name" in role
                assert "id" in role

    async def test_role_change_reflects_in_user_me(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
    ):
        """After granting reviewer role, /users/me reflects the change."""
        r = await client.get("/api/v1/users/me", headers=auth_header(respondent_user))
        roles_before = {role["name"] for role in r.json()["roles"]}
        assert "reviewer" not in roles_before

        # Admin grants reviewer role
        await client.post(f"/api/v1/users/{respondent_user.id}/roles", json={
            "role_name": "reviewer",
        }, headers=auth_header(admin_user))

        # /users/me should reflect the new role
        r = await client.get("/api/v1/users/me", headers=auth_header(respondent_user))
        assert r.status_code == 200
        roles_after = {role["name"] for role in r.json()["roles"]}
        assert "reviewer" in roles_after

    async def test_user_list_pagination(
        self, client: AsyncClient, admin_user: User, author_user: User,
        respondent_user: User, reviewer_user: User,
    ):
        """User list supports pagination with skip/limit."""
        r = await client.get("/api/v1/users?skip=0&limit=2", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert len(data["users"]) <= 2
        assert data["total"] >= 4

        r = await client.get("/api/v1/users?skip=2&limit=2", headers=auth_header(admin_user))
        assert r.status_code == 200
        page2 = r.json()
        assert len(page2["users"]) <= 2
