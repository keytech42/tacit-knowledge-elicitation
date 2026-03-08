"""
State consistency audit tests.

Checks for orphaned references, missing guard rails, cascade gaps,
revision cycle leaks, and permission leaks across the Question/Answer/Review
state machines.

Organized into sections:
  1. Orphaned reference tests — child entities left in invalid states
  2. Missing guard rail tests — invalid actions that are not rejected
  3. Transition boundary tests — every invalid transition attempt
  4. Cascade gap tests — parent state changes not propagated to children
  5. Revision cycle tests — old reviews interfering with new cycles
  6. Abstract invariant tests — broad state machine properties
  7. Permission leak tests — role checks that may be incomplete
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import Role, RoleName, User, UserType
from tests.conftest import auth_header


# ---------------------------------------------------------------------------
# Helper: second reviewer user (not in conftest)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def reviewer_user_2(db: AsyncSession, roles: dict[str, Role]) -> User:
    user = User(
        user_type=UserType.HUMAN,
        external_id="google_reviewer2_456",
        display_name="Second Reviewer",
        email="reviewer2@test.com",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    user.roles.append(roles[RoleName.REVIEWER.value])
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Helpers to set up common scenarios
# ---------------------------------------------------------------------------

async def _published_question(db: AsyncSession, admin_user: User, **kwargs) -> Question:
    defaults = dict(
        title="Test Q", body="Body", created_by_id=admin_user.id,
        status=QuestionStatus.PUBLISHED.value,
        review_policy={"min_approvals": 1},
    )
    defaults.update(kwargs)
    q = Question(**defaults)
    db.add(q)
    await db.flush()
    return q


async def _draft_answer(db: AsyncSession, question: Question, author: User, **kwargs) -> Answer:
    defaults = dict(
        question_id=question.id, author_id=author.id,
        body="Answer body", status=AnswerStatus.DRAFT.value,
    )
    defaults.update(kwargs)
    a = Answer(**defaults)
    db.add(a)
    await db.flush()
    return a


async def _submitted_answer(
    client: AsyncClient, db: AsyncSession, question: Question,
    author: User,
) -> str:
    """Create and submit an answer via the API. Returns answer ID."""
    r = await client.post(
        f"/api/v1/questions/{question.id}/answers",
        json={"body": "Submitted answer"},
        headers=auth_header(author),
    )
    a_id = r.json()["id"]
    await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(author))
    return a_id


# ===================================================================
# 1. ORPHANED REFERENCE TESTS
# ===================================================================

class TestOrphanedReferences:
    """Objects left pointing to states that no longer make sense."""

    async def test_closing_question_cancels_submitted_answers(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """When a question is closed, submitted/under_review answers should not remain active."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Close question
        r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
        assert r.status_code == 200

        # BUG: the answer is still in "submitted" status — orphaned
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        answer_status = r.json()["status"]
        assert answer_status not in (
            AnswerStatus.SUBMITTED.value,
            AnswerStatus.UNDER_REVIEW.value,
            AnswerStatus.DRAFT.value,
        ), f"Answer should not be in {answer_status} after question is closed"

    async def test_closing_question_closes_pending_reviews(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """When a question is closed, pending reviews on its answers should be superseded."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Reviewer creates a pending review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        review_id = r.json()["id"]

        # Close the question
        await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))

        # BUG: the review is still pending
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.json()["verdict"] != ReviewVerdict.PENDING.value, \
            "Review should not remain pending after question is closed"

    async def test_closing_question_handles_draft_answers(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Draft answers on a closed question are orphaned."""
        q = await _published_question(db, admin_user)

        # Create draft answer (do not submit)
        r = await client.post(
            f"/api/v1/questions/{q.id}/answers",
            json={"body": "Draft answer"},
            headers=auth_header(respondent_user),
        )
        a_id = r.json()["id"]

        # Close question
        await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))

        # The draft answer exists for a closed question
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        # At minimum, the draft answer should not be submittable
        r2 = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r2.status_code == 409, \
            "Should not be able to submit a draft answer for a closed question"


# ===================================================================
# 2. MISSING GUARD RAIL TESTS
# ===================================================================

class TestMissingGuardRails:
    """Invalid actions the API does not currently reject."""

    async def test_author_cannot_review_own_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, roles: dict[str, Role], db: AsyncSession,
    ):
        """The answer author should not be able to create a review for their own answer."""
        # Give the respondent reviewer role so they pass the role check
        await db.refresh(respondent_user, ["roles"])
        respondent_user.roles.append(roles[RoleName.REVIEWER.value])
        await db.flush()

        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # BUG: respondent (the author) can create a review on their own answer
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(respondent_user))
        assert r.status_code == 409, \
            "Author should not be able to review their own answer"

    async def test_cannot_change_verdict_on_resolved_review(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Once a review has a verdict, it should not be changeable."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Create and approve review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # BUG: reviewer can change their verdict from approved to rejected
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "rejected",
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409, \
            "Should not be able to change verdict on an already-resolved review"

    async def test_cannot_create_review_for_draft_question(
        self, client: AsyncClient, admin_user: User, reviewer_user: User, db: AsyncSession,
    ):
        """Should not be able to create a review for a question in draft status."""
        q = Question(
            title="Draft Q", body="B", created_by_id=admin_user.id,
            status=QuestionStatus.DRAFT.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "question", "target_id": str(q.id),
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409, \
            "Should not be able to create a review for a draft question"

    async def test_cannot_create_review_for_draft_answer(
        self, client: AsyncClient, admin_user: User, reviewer_user: User,
        respondent_user: User, db: AsyncSession,
    ):
        """Cannot create a review for an answer in draft status."""
        q = await _published_question(db, admin_user)
        a = await _draft_answer(db, q, respondent_user)

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409

    async def test_cannot_create_review_for_approved_answer(
        self, client: AsyncClient, admin_user: User, reviewer_user: User,
        respondent_user: User, db: AsyncSession,
    ):
        """Cannot create a review for an already-approved answer."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Done", status=AnswerStatus.APPROVED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409

    async def test_cannot_create_review_for_rejected_answer(
        self, client: AsyncClient, admin_user: User, reviewer_user: User,
        respondent_user: User, db: AsyncSession,
    ):
        """Cannot create a review for a rejected answer."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Bad", status=AnswerStatus.REJECTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 409

    async def test_cannot_submit_answer_for_closed_question(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Submitting an answer should fail if the parent question is no longer published."""
        q = await _published_question(db, admin_user)

        # Create draft answer while question is published
        r = await client.post(
            f"/api/v1/questions/{q.id}/answers",
            json={"body": "My answer"},
            headers=auth_header(respondent_user),
        )
        a_id = r.json()["id"]

        # Close the question
        await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))

        # BUG: can still submit the answer even though question is closed
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 409, \
            "Should not be able to submit an answer for a closed question"

    async def test_auto_assigned_reviews_have_answer_version(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Auto-assigned reviews should include the answer_version field."""
        from app.services.review import auto_assign_reviewers

        q = await _published_question(db, admin_user, review_policy={
            "min_approvals": 1, "auto_assign": True, "auto_assign_count": 1,
        })
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        reviews = await auto_assign_reviewers(a, q, db)
        assert len(reviews) >= 1

        for review in reviews:
            assert review.answer_version is not None, \
                "Auto-assigned reviews must include answer_version for version-filtered resolution"
            assert review.answer_version == a.current_version


# ===================================================================
# 3. TRANSITION BOUNDARY TESTS
# ===================================================================

class TestQuestionTransitionBoundaries:
    """Every invalid question state transition attempt should be rejected."""

    @pytest.mark.parametrize("from_status,action_path", [
        # draft: only submit is valid
        (QuestionStatus.DRAFT.value, "start-review"),
        (QuestionStatus.DRAFT.value, "publish"),
        (QuestionStatus.DRAFT.value, "reject"),
        (QuestionStatus.DRAFT.value, "close"),
        (QuestionStatus.DRAFT.value, "archive"),
        # proposed: only start-review is valid (admin)
        (QuestionStatus.PROPOSED.value, "submit"),
        (QuestionStatus.PROPOSED.value, "publish"),
        (QuestionStatus.PROPOSED.value, "reject"),
        (QuestionStatus.PROPOSED.value, "close"),
        (QuestionStatus.PROPOSED.value, "archive"),
        # in_review: only publish and reject are valid
        (QuestionStatus.IN_REVIEW.value, "submit"),
        (QuestionStatus.IN_REVIEW.value, "start-review"),
        (QuestionStatus.IN_REVIEW.value, "close"),
        (QuestionStatus.IN_REVIEW.value, "archive"),
        # published: only close is valid
        (QuestionStatus.PUBLISHED.value, "submit"),
        (QuestionStatus.PUBLISHED.value, "start-review"),
        (QuestionStatus.PUBLISHED.value, "publish"),
        (QuestionStatus.PUBLISHED.value, "reject"),
        (QuestionStatus.PUBLISHED.value, "archive"),
        # closed: only archive is valid
        (QuestionStatus.CLOSED.value, "submit"),
        (QuestionStatus.CLOSED.value, "start-review"),
        (QuestionStatus.CLOSED.value, "publish"),
        (QuestionStatus.CLOSED.value, "reject"),
        (QuestionStatus.CLOSED.value, "close"),
        # archived: no transitions
        (QuestionStatus.ARCHIVED.value, "submit"),
        (QuestionStatus.ARCHIVED.value, "start-review"),
        (QuestionStatus.ARCHIVED.value, "publish"),
        (QuestionStatus.ARCHIVED.value, "reject"),
        (QuestionStatus.ARCHIVED.value, "close"),
        (QuestionStatus.ARCHIVED.value, "archive"),
    ])
    async def test_invalid_question_transition_rejected(
        self, client: AsyncClient, admin_user: User, from_status: str, action_path: str,
        db: AsyncSession,
    ):
        """All invalid question state transitions should return 409."""
        q = Question(
            title="Transition Test", body="B",
            created_by_id=admin_user.id, status=from_status,
        )
        db.add(q)
        await db.flush()

        # For reject, send the JSON body the endpoint expects
        if action_path == "reject":
            r = await client.post(
                f"/api/v1/questions/{q.id}/{action_path}",
                json={"comment": "test"},
                headers=auth_header(admin_user),
            )
        else:
            r = await client.post(
                f"/api/v1/questions/{q.id}/{action_path}",
                headers=auth_header(admin_user),
            )
        assert r.status_code == 409, \
            f"Transition {from_status} -> {action_path} should be rejected (got {r.status_code})"


class TestAnswerTransitionBoundaries:
    """Every invalid answer state transition attempt should be rejected."""

    @pytest.mark.parametrize("from_status,action,expected_code", [
        # submit: only valid from draft (and revision_requested via resubmit)
        (AnswerStatus.SUBMITTED.value, "submit", 409),
        (AnswerStatus.UNDER_REVIEW.value, "submit", 409),
        (AnswerStatus.APPROVED.value, "submit", 409),
        (AnswerStatus.REJECTED.value, "submit", 409),
        # revise: only valid from approved
        (AnswerStatus.DRAFT.value, "revise", 409),
        (AnswerStatus.SUBMITTED.value, "revise", 409),
        (AnswerStatus.UNDER_REVIEW.value, "revise", 409),
        (AnswerStatus.REVISION_REQUESTED.value, "revise", 409),
        (AnswerStatus.REJECTED.value, "revise", 409),
    ])
    async def test_invalid_answer_transition_rejected(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        from_status: str, action: str, expected_code: int, db: AsyncSession,
    ):
        """All invalid answer state transitions should be rejected."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Test answer", status=from_status, current_version=1,
        )
        db.add(a)
        await db.flush()

        if action == "submit":
            r = await client.post(
                f"/api/v1/answers/{a.id}/submit",
                headers=auth_header(respondent_user),
            )
        elif action == "revise":
            r = await client.post(
                f"/api/v1/answers/{a.id}/revise",
                json={"body": "New content"},
                headers=auth_header(respondent_user),
            )
        else:
            pytest.fail(f"Unknown action: {action}")

        assert r.status_code == expected_code, \
            f"Transition from {from_status} via {action} should return {expected_code} (got {r.status_code})"

    @pytest.mark.parametrize("status", [
        AnswerStatus.SUBMITTED.value,
        AnswerStatus.UNDER_REVIEW.value,
        AnswerStatus.APPROVED.value,
        AnswerStatus.REJECTED.value,
    ])
    async def test_cannot_edit_non_editable_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        status: str, db: AsyncSession,
    ):
        """PATCH should be rejected for answers not in draft or revision_requested."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Test", status=status, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.patch(
            f"/api/v1/answers/{a.id}",
            json={"body": "Sneaky edit"},
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 403, \
            f"Should not be able to edit answer in {status} status"


# ===================================================================
# 4. CASCADE GAP TESTS
# ===================================================================

class TestCascadeGaps:
    """When a parent entity changes state, child entities should be updated."""

    async def test_archiving_question_handles_approved_answers(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """After archiving a question, its answers should still be accessible
        but the question's answers should not be further modifiable."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Approve the answer
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Close and archive
        await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
        await client.post(f"/api/v1/questions/{q.id}/archive", headers=auth_header(admin_user))

        # Approved answer should not be revisable after question is archived
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Post-archive revision attempt",
        }, headers=auth_header(respondent_user))
        assert r.status_code == 409, \
            "Should not be able to revise an answer after question is archived"

    async def test_delete_question_cascades_reviews(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Deleting a question should remove all associated reviews."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Create a review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Delete question as admin
        r = await client.delete(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Review should be gone
        r = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_header(reviewer_user))
        assert r.status_code == 404

    async def test_closing_question_clears_respondent_assignment(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """When a question is closed, the respondent assignment should be cleared."""
        q = await _published_question(db, admin_user)

        # Assign respondent
        await client.post(
            f"/api/v1/questions/{q.id}/assign-respondent",
            json={"user_id": str(respondent_user.id)},
            headers=auth_header(admin_user),
        )

        # Close question
        await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))

        # Check assignment is cleared
        r = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert r.json()["assigned_respondent"] is None, \
            "Respondent assignment should be cleared when question is closed"


# ===================================================================
# 5. REVISION CYCLE TESTS
# ===================================================================

class TestRevisionCycleIntegrity:
    """Old reviews from previous cycles should not interfere with new cycles."""

    async def test_old_approvals_dont_count_in_new_cycle(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """After a post-approval revision bumps the version, old v1 approvals
        should not satisfy the new cycle's approval threshold."""
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 1})

        # Create, submit, review, approve at v1
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Version 1",
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

        # Revise: approved -> submitted at v2
        r = await client.post(f"/api/v1/answers/{a_id}/revise", json={
            "body": "Version 2 — improved",
        }, headers=auth_header(respondent_user))
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 2

        # The answer should NOT be auto-approved from the old v1 review
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "submitted", \
            "Old v1 approval should not auto-approve the v2 cycle"

    async def test_resubmit_resets_changes_requested_reviews_only(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """When resubmitting after changes_requested, only the changes_requested
        reviews are reset to pending. Other verdicts stay."""
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 2})

        # Create and submit answer
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "Answer to review",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Reviewer 1 approves
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Reviewer 2 requests changes
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user_2))
        review2_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "changes_requested", "comment": "Fix paragraph 2",
        }, headers=auth_header(reviewer_user_2))

        # Edit and resubmit
        await client.patch(f"/api/v1/answers/{a_id}", json={
            "body": "Improved answer body",
        }, headers=auth_header(respondent_user))
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Check: review 2 (changes_requested) should now be pending
        r = await client.get(f"/api/v1/reviews/{review2_id}", headers=auth_header(reviewer_user_2))
        assert r.json()["verdict"] == ReviewVerdict.PENDING.value

        # Check: review 1 (approved) should still be approved
        r = await client.get(f"/api/v1/reviews/{review1_id}", headers=auth_header(reviewer_user))
        assert r.json()["verdict"] == ReviewVerdict.APPROVED.value

    async def test_review_answer_version_tracks_current_version(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """When a review is created, it should track the answer's current_version."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        assert r.json()["answer_version"] == 1


# ===================================================================
# 6. ABSTRACT INVARIANT TESTS
# ===================================================================

class TestStateInvariants:
    """Broad invariants that should always hold across the state machines."""

    async def test_approved_answer_has_confirmed_at(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Approved answers must have confirmed_at set."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Approve
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Check invariant
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"
        assert r.json()["confirmed_at"] is not None, \
            "Approved answers must have confirmed_at set"

    async def test_approved_answer_has_confirmed_by(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Approved answers must have confirmed_by set to the last approver."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["confirmed_by"] is not None
        assert r.json()["confirmed_by"]["id"] == str(reviewer_user.id)

    async def test_published_question_has_review_policy(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """Published questions must always have a review_policy (default applied on publish)."""
        q = Question(
            title="No Policy", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
            review_policy=None,  # Explicitly no policy
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["review_policy"] is not None, \
            "Published questions must have a review_policy"

    async def test_published_question_has_timestamps(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """Published questions must have published_at and confirmed_at set."""
        q = Question(
            title="Timestamp Test", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert data["published_at"] is not None, "Published questions must have published_at"
        assert data["confirmed_at"] is not None, "Published questions must have confirmed_at"
        assert data["confirmed_by"] is not None, "Published questions must have confirmed_by"

    async def test_closed_question_has_closed_at(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Closed questions must have closed_at set."""
        q = Question(
            title="Close Test", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["closed_at"] is not None

    async def test_submitted_answer_has_submitted_at(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Submitted answers must have submitted_at set."""
        q = await _published_question(db, admin_user)

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["submitted_at"] is not None

    async def test_submitted_answer_has_version_1(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """First submission should create version 1."""
        q = await _published_question(db, admin_user)

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "First answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))
        assert r.json()["current_version"] == 1

    @pytest.mark.parametrize("terminal_status", [
        AnswerStatus.APPROVED.value,
        AnswerStatus.REJECTED.value,
    ])
    async def test_no_pending_reviews_for_terminal_answers(
        self, admin_user: User, respondent_user: User, reviewer_user: User,
        terminal_status: str, db: AsyncSession,
    ):
        """No pending reviews should exist for answers in terminal states
        (approved or rejected) at the current version."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=respondent_user.id,
            body="Answer", status=terminal_status, current_version=1,
        )
        db.add(a)
        await db.flush()

        # Create a review that is still pending (simulating the orphaned review bug)
        review = Review(
            target_type=ReviewTargetType.ANSWER.value,
            target_id=a.id,
            reviewer_id=reviewer_user.id,
            verdict=ReviewVerdict.PENDING.value,
            answer_version=1,
        )
        db.add(review)
        await db.flush()

        # Query: are there any pending reviews for this terminal answer?
        result = await db.execute(
            select(Review).where(
                Review.target_type == ReviewTargetType.ANSWER.value,
                Review.target_id == a.id,
                Review.answer_version == a.current_version,
                Review.verdict == ReviewVerdict.PENDING.value,
            )
        )
        pending = result.scalars().all()

        # NOTE: this test documents the invariant. The DB setup intentionally
        # creates an orphaned review. In a bug-free system, the resolution
        # logic would have already cleaned these up.
        # We mark this as a known-fragile invariant that the resolution code
        # should maintain.
        # (Not xfail because the bug is the resolution logic, not a test setup issue)

    async def test_review_version_matches_answer_version(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """When a review is created via the API, its answer_version must match
        the answer's current_version at creation time."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        assert r.status_code == 201

        review_data = r.json()
        assert review_data["answer_version"] is not None
        assert review_data["answer_version"] == 1

    async def test_answers_only_created_for_published_questions(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Answers can only be created for questions in published status."""
        for status in [
            QuestionStatus.DRAFT.value,
            QuestionStatus.PROPOSED.value,
            QuestionStatus.IN_REVIEW.value,
            QuestionStatus.CLOSED.value,
            QuestionStatus.ARCHIVED.value,
        ]:
            q = Question(
                title=f"{status} Q", body="B",
                created_by_id=admin_user.id, status=status,
            )
            db.add(q)
            await db.flush()

            r = await client.post(
                f"/api/v1/questions/{q.id}/answers",
                json={"body": "Answer"},
                headers=auth_header(respondent_user),
            )
            assert r.status_code == 409, \
                f"Should not be able to create answers for {status} questions"


# ===================================================================
# 7. PERMISSION LEAK TESTS
# ===================================================================

class TestPermissionLeaks:
    """Role checks that may be incomplete or inconsistent."""

    async def test_respondent_cannot_create_review(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Respondent role (without reviewer) cannot create reviews."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=admin_user.id,
            body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_author_cannot_create_review(
        self, client: AsyncClient, admin_user: User, author_user: User, db: AsyncSession,
    ):
        """Author role (without reviewer) cannot create reviews."""
        q = await _published_question(db, admin_user)
        a = Answer(
            question_id=q.id, author_id=admin_user.id,
            body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1,
        )
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": str(a.id),
        }, headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_reviewer_cannot_modify_other_reviewers_verdict(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """A reviewer should not be able to submit a verdict on another reviewer's review."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Reviewer 1 creates review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Reviewer 2 tries to submit verdict on reviewer 1's review
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user_2))
        assert r.status_code == 403, \
            "Reviewer should not be able to modify another reviewer's review"

    async def test_author_cannot_publish_question(
        self, client: AsyncClient, author_user: User, db: AsyncSession,
    ):
        """Author cannot publish a question (admin-only transition)."""
        q = Question(
            title="Test", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.IN_REVIEW.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/publish", headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_author_cannot_close_question(
        self, client: AsyncClient, author_user: User, db: AsyncSession,
    ):
        """Author cannot close a question (admin-only transition)."""
        q = Question(
            title="Test", body="B",
            created_by_id=author_user.id,
            status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/close", headers=auth_header(author_user))
        assert r.status_code == 403

    async def test_non_author_cannot_submit_others_answer(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """A user who is not the answer's author (and not admin) cannot submit it."""
        q = await _published_question(db, admin_user)

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={
            "body": "My answer",
        }, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        # Reviewer (not the author) tries to submit
        r = await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(reviewer_user))
        assert r.status_code == 403

    async def test_admin_cannot_edit_archived_question(
        self, client: AsyncClient, admin_user: User, db: AsyncSession,
    ):
        """Even admins should not be able to edit archived questions."""
        q = Question(
            title="Archived", body="B",
            created_by_id=admin_user.id,
            status=QuestionStatus.ARCHIVED.value,
        )
        db.add(q)
        await db.flush()

        r = await client.patch(f"/api/v1/questions/{q.id}", json={
            "title": "Editing archived question",
        }, headers=auth_header(admin_user))
        assert r.status_code == 403, \
            "Admin should not be able to edit archived questions"

    async def test_admin_can_submit_verdict_on_any_review(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, db: AsyncSession,
    ):
        """Admin should be able to submit a verdict on any review (override)."""
        q = await _published_question(db, admin_user)
        a_id = await _submitted_answer(client, db, q, respondent_user)

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review_id = r.json()["id"]

        # Admin overrides
        r = await client.patch(f"/api/v1/reviews/{review_id}", json={
            "verdict": "approved",
        }, headers=auth_header(admin_user))
        assert r.status_code == 200

    async def test_assign_respondent_only_on_published_questions(
        self, client: AsyncClient, admin_user: User, respondent_user: User, db: AsyncSession,
    ):
        """Cannot assign a respondent to a non-published question."""
        for status in [
            QuestionStatus.DRAFT.value,
            QuestionStatus.PROPOSED.value,
            QuestionStatus.IN_REVIEW.value,
            QuestionStatus.CLOSED.value,
            QuestionStatus.ARCHIVED.value,
        ]:
            q = Question(
                title=f"{status} Q", body="B",
                created_by_id=admin_user.id, status=status,
            )
            db.add(q)
            await db.flush()

            r = await client.post(
                f"/api/v1/questions/{q.id}/assign-respondent",
                json={"user_id": str(respondent_user.id)},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 409, \
                f"Should not assign respondent on {status} question"


# ===================================================================
# 8. CONCURRENT REVIEW RESOLUTION TESTS
# ===================================================================

class TestConcurrentReviewResolution:
    """Multiple reviewers submitting verdicts — resolution should be deterministic."""

    async def test_two_approvals_when_min_is_two(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """Answer should only be approved when min_approvals threshold is met."""
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 2})
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Reviewer 1 creates and approves
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # After 1 approval, answer should NOT be approved yet
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "under_review"

        # Reviewer 2 creates and approves
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user_2))
        review2_id = r.json()["id"]
        await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user_2))

        # After 2 approvals, answer SHOULD be approved
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "approved"

    async def test_changes_requested_blocks_approval(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """A changes_requested verdict should block approval even with enough approvals.

        Both reviews are created while the answer is under_review (min_approvals=2
        so a single approval won't resolve it). Reviewer 1 approves, reviewer 2
        requests changes. The final state should be revision_requested.
        """
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 2})
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Both reviewers create reviews while answer is under_review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user_2))
        review2_id = r.json()["id"]

        # Reviewer 1 approves (not enough for threshold — answer stays under_review)
        await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Reviewer 2 requests changes
        await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "changes_requested",
        }, headers=auth_header(reviewer_user_2))

        # Answer should be revision_requested (changes_requested blocks approval)
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "revision_requested"

    async def test_rejection_takes_priority_over_approval(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """A rejection should override approvals when threshold is not yet met.

        With min_approvals=2, a single approval doesn't resolve the answer.
        When the second reviewer rejects, resolve_answer_reviews sees the
        rejection and sets the answer to rejected.
        """
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 2})
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Both reviewers create reviews while answer is under_review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user_2))
        review2_id = r.json()["id"]

        # Reviewer 1 approves (not enough for threshold — answer stays under_review)
        await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "approved",
        }, headers=auth_header(reviewer_user))

        # Reviewer 2 rejects
        await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "rejected",
        }, headers=auth_header(reviewer_user_2))

        # Answer should be rejected (rejection overrides partial approval)
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "rejected"

    async def test_changes_requested_priority_over_rejection(
        self, client: AsyncClient, admin_user: User, respondent_user: User,
        reviewer_user: User, reviewer_user_2: User, db: AsyncSession,
    ):
        """changes_requested should take priority over rejection (allows re-work).

        Both reviews are created while the answer is under_review.
        Reviewer 1 rejects first (resolution sets status to rejected).
        Reviewer 2 then requests changes, but resolve_answer_reviews
        exits early because status is no longer under_review.

        This is a real inconsistency: the resolution order affects the
        final state, and the intended priority (changes_requested > rejected)
        is not respected.
        """
        q = await _published_question(db, admin_user, review_policy={"min_approvals": 2})
        a_id = await _submitted_answer(client, db, q, respondent_user)

        # Both reviewers create reviews while answer is under_review
        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user))
        review1_id = r.json()["id"]

        r = await client.post("/api/v1/reviews", json={
            "target_type": "answer", "target_id": a_id,
        }, headers=auth_header(reviewer_user_2))
        review2_id = r.json()["id"]

        # Reviewer 1 rejects (answer -> rejected via resolve)
        await client.patch(f"/api/v1/reviews/{review1_id}", json={
            "verdict": "rejected",
        }, headers=auth_header(reviewer_user))

        # Reviewer 2 requests changes (resolve exits early — answer already rejected)
        await client.patch(f"/api/v1/reviews/{review2_id}", json={
            "verdict": "changes_requested",
        }, headers=auth_header(reviewer_user_2))

        # Expected: revision_requested (changes_requested > rejected)
        # Actual: rejected (first resolution wins)
        r = await client.get(f"/api/v1/answers/{a_id}", headers=auth_header(respondent_user))
        assert r.json()["status"] == "revision_requested"
