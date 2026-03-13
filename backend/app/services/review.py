from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.answer import Answer, AnswerStatus
from app.models.question import Question
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import RoleName, User


async def resolve_answer_reviews(answer_id, db: AsyncSession) -> None:
    """Check if an answer has met its approval threshold and update status accordingly.

    Only considers reviews from the current revision cycle (matching the
    answer's current_version) so that old verdicts from previous cycles
    don't block new approvals.

    When the answer is resolved (approved, rejected, or revision_requested),
    any remaining pending reviews for the same answer+version are
    automatically superseded so they don't linger in reviewer queues.
    """
    answer_result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = answer_result.scalar_one_or_none()
    # Allow re-resolution from non-terminal answer states where new verdicts
    # may change priority (e.g. changes_requested arriving after rejection)
    re_evaluable = {
        AnswerStatus.UNDER_REVIEW.value,
        AnswerStatus.REJECTED.value,
        AnswerStatus.REVISION_REQUESTED.value,
    }
    if not answer or answer.status not in re_evaluable:
        return

    question_result = await db.execute(select(Question).where(Question.id == answer.question_id))
    question = question_result.scalar_one_or_none()
    if not question:
        return

    review_policy = question.review_policy or {"min_approvals": 1}
    min_approvals = review_policy.get("min_approvals", 1)

    # Only consider reviews from the current answer version cycle
    review_query = select(Review).where(
        Review.target_type == ReviewTargetType.ANSWER.value,
        Review.target_id == answer_id,
        Review.answer_version == answer.current_version,
    )

    reviews_result = await db.execute(review_query)
    reviews = reviews_result.scalars().all()

    resolved = False

    # Check for any changes_requested — blocks approval
    for review in reviews:
        if review.verdict == ReviewVerdict.CHANGES_REQUESTED.value:
            answer.status = AnswerStatus.REVISION_REQUESTED.value
            resolved = True
            break

    # Check for rejected
    if not resolved:
        for review in reviews:
            if review.verdict == ReviewVerdict.REJECTED.value:
                answer.status = AnswerStatus.REJECTED.value
                resolved = True
                break

    # Count approvals
    if not resolved:
        approval_count = sum(1 for r in reviews if r.verdict == ReviewVerdict.APPROVED.value)
        if approval_count >= min_approvals:
            answer.status = AnswerStatus.APPROVED.value
            answer.confirmed_at = datetime.now(timezone.utc)
            # Set confirmed_by to the last approver
            last_approver = [r for r in reviews if r.verdict == ReviewVerdict.APPROVED.value][-1]
            answer.confirmed_by_id = last_approver.reviewer_id
            resolved = True

    # Auto-supersede remaining pending reviews only when the answer reaches
    # a terminal positive state (approved). For rejected/revision_requested,
    # keep pending reviews open so other reviewers can still submit verdicts
    # that may change the priority outcome (changes_requested > rejected).
    if resolved and answer.status == AnswerStatus.APPROVED.value:
        await db.execute(
            update(Review)
            .where(
                Review.target_type == ReviewTargetType.ANSWER.value,
                Review.target_id == answer_id,
                Review.answer_version == answer.current_version,
                Review.verdict == ReviewVerdict.PENDING.value,
            )
            .values(verdict=ReviewVerdict.SUPERSEDED.value)
        )


async def auto_assign_reviewers(answer: Answer, question: Question, db: AsyncSession) -> list[Review]:
    """Auto-assign reviewers based on question's review policy."""
    review_policy = question.review_policy or {}
    if not review_policy.get("auto_assign", False):
        return []

    auto_assign_count = review_policy.get("auto_assign_count", 1)
    allow_self_review = review_policy.get("allow_self_review", False)

    # Find users with reviewer role
    from app.models.user import Role, User, user_roles
    from sqlalchemy import and_

    reviewer_role_result = await db.execute(
        select(Role).where(Role.name == RoleName.REVIEWER.value)
    )
    reviewer_role = reviewer_role_result.scalar_one_or_none()
    if not reviewer_role:
        return []

    # Get all reviewer users
    reviewers_result = await db.execute(
        select(User).join(user_roles).where(
            user_roles.c.role_id == reviewer_role.id,
            User.is_active == True,  # noqa: E712
        )
    )
    reviewers = reviewers_result.scalars().all()

    # Filter out the answer author unless self-review allowed (or dev/test mode)
    if not allow_self_review and not settings.DEV_LOGIN_ENABLED:
        reviewers = [r for r in reviewers if r.id != answer.author_id]

    # Take first N reviewers (simple round-robin for v1)
    selected = reviewers[:auto_assign_count]

    created_reviews = []
    for reviewer in selected:
        review = Review(
            target_type=ReviewTargetType.ANSWER.value,
            target_id=answer.id,
            reviewer_id=reviewer.id,
            answer_version=answer.current_version,
        )
        db.add(review)
        created_reviews.append(review)

    return created_reviews
