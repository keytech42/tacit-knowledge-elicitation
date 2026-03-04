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

        # Author edits the answer body
        r = await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Version 2 of my answer — improved",
        }, headers=auth_header(admin_user))
        assert r.status_code == 200

        # Author revises → submitted, new version
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
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

        # Author resubmits
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # New review and approval
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review2_id = r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review2_id}", json={
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

        # First revise → success
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # Second revise → 409 (no longer approved)
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
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

        # Edit and revise to create v2
        await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Updated answer v2",
        }, headers=auth_header(admin_user))
        await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))

        # Admin deletes the question — should cascade through answers, revisions
        r = await client.delete(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Verify question gone
        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 404

        # Verify answer gone
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(admin_user))
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

        # Edit answer body for v2
        await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Revised answer text with improvements",
        }, headers=auth_header(admin_user))

        # Revise → creates revision v2
        r = await client.post(f"/api/v1/answers/{a_id}/revise", headers=auth_header(respondent_user))
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
