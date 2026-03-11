import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Confirmation, Question, QuestionStatus
from app.models.question_respondent import QuestionRespondent
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import RoleName, User

MAX_RESPONDENTS = 5

QUESTION_TRANSITIONS = {
    QuestionStatus.DRAFT: {QuestionStatus.PROPOSED: {RoleName.AUTHOR, RoleName.ADMIN}},
    QuestionStatus.PROPOSED: {QuestionStatus.IN_REVIEW: {RoleName.ADMIN}},
    QuestionStatus.IN_REVIEW: {
        QuestionStatus.PUBLISHED: {RoleName.ADMIN},
        QuestionStatus.DRAFT: {RoleName.ADMIN},
    },
    QuestionStatus.PUBLISHED: {QuestionStatus.CLOSED: {RoleName.ADMIN}},
    QuestionStatus.CLOSED: {QuestionStatus.ARCHIVED: {RoleName.ADMIN}},
}

DEFAULT_REVIEW_POLICY = {
    "min_approvals": 1,
    "auto_assign": False,
    "allow_self_review": False,
    "require_comment_on_reject": True,
}


def validate_transition(question: Question, target_status: QuestionStatus, user: User) -> None:
    current = QuestionStatus(question.status)
    allowed = QUESTION_TRANSITIONS.get(current, {})
    if target_status not in allowed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot transition from {current.value} to {target_status.value}")
    required_roles = allowed[target_status]
    user_roles = {r.name for r in user.roles}
    required_role_values = {r.value if isinstance(r, RoleName) else r for r in required_roles}
    if not user_roles.intersection(required_role_values):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions for this transition")


def can_edit_question(question: Question, user: User) -> bool:
    if question.status == QuestionStatus.ARCHIVED.value:
        return False
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    if question.created_by_id == user.id and question.status == QuestionStatus.DRAFT.value:
        return True
    return False


def apply_submit(question: Question, user: User) -> None:
    validate_transition(question, QuestionStatus.PROPOSED, user)
    user_roles = {r.name for r in user.roles}
    if question.created_by_id != user.id and RoleName.ADMIN.value not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the creator or admin can submit")
    question.status = QuestionStatus.PROPOSED.value


def apply_start_review(question: Question, user: User) -> None:
    validate_transition(question, QuestionStatus.IN_REVIEW, user)
    question.status = QuestionStatus.IN_REVIEW.value


def apply_publish(question: Question, user: User) -> None:
    validate_transition(question, QuestionStatus.PUBLISHED, user)
    question.status = QuestionStatus.PUBLISHED.value
    question.confirmation = Confirmation.CONFIRMED.value
    question.confirmed_by_id = user.id
    question.confirmed_at = datetime.now(timezone.utc)
    question.published_at = datetime.now(timezone.utc)
    if not question.review_policy:
        question.review_policy = DEFAULT_REVIEW_POLICY


def apply_reject(question: Question, user: User, comment: str | None = None) -> None:
    validate_transition(question, QuestionStatus.DRAFT, user)
    question.status = QuestionStatus.DRAFT.value
    question.confirmation = Confirmation.REJECTED.value



async def update_respondent_pool(
    db: AsyncSession,
    question: Question,
    user_ids: list[uuid.UUID],
    expected_version: int,
    assigned_by: User,
) -> Question:
    if len(user_ids) > MAX_RESPONDENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign more than {MAX_RESPONDENTS} respondents",
        )
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate user IDs in request",
        )
    if question.respondent_pool_version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version mismatch \u2014 pool was modified by another user",
        )
    if user_ids:
        result = await db.execute(select(User.id).where(User.id.in_(user_ids)))
        found_ids = {row[0] for row in result.all()}
        missing = set(user_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Users not found: {[str(uid) for uid in missing]}",
            )
    await db.execute(
        delete(QuestionRespondent).where(QuestionRespondent.question_id == question.id)
    )
    for uid in user_ids:
        db.add(QuestionRespondent(
            question_id=question.id, user_id=uid, assigned_by_id=assigned_by.id,
        ))
    question.respondent_pool_version += 1
    await db.flush()
    await db.refresh(question)
    return question


async def apply_close(question: Question, user: User, db: AsyncSession) -> None:
    validate_transition(question, QuestionStatus.CLOSED, user)
    question.status = QuestionStatus.CLOSED.value
    question.closed_at = datetime.now(timezone.utc)
    question.assigned_respondent_id = None

    # Clear the respondent pool
    await db.execute(
        delete(QuestionRespondent).where(QuestionRespondent.question_id == question.id)
    )

    # Cascade: reject all in-flight and draft answers
    in_flight = [
        AnswerStatus.DRAFT.value,
        AnswerStatus.SUBMITTED.value,
        AnswerStatus.UNDER_REVIEW.value,
        AnswerStatus.REVISION_REQUESTED.value,
    ]
    # Get IDs of answers to reject (needed for review superseding)
    result = await db.execute(
        select(Answer.id).where(
            Answer.question_id == question.id,
            Answer.status.in_(in_flight),
        )
    )
    answer_ids = [row[0] for row in result.all()]

    if answer_ids:
        # Reject the answers
        await db.execute(
            update(Answer)
            .where(Answer.id.in_(answer_ids))
            .values(status=AnswerStatus.REJECTED.value)
        )
        # Supersede pending reviews on those answers
        await db.execute(
            update(Review)
            .where(
                Review.target_type == ReviewTargetType.ANSWER.value,
                Review.target_id.in_(answer_ids),
                Review.verdict == ReviewVerdict.PENDING.value,
            )
            .values(verdict=ReviewVerdict.SUPERSEDED.value)
        )


async def apply_archive(question: Question, user: User, db: AsyncSession) -> None:
    validate_transition(question, QuestionStatus.ARCHIVED, user)
    question.status = QuestionStatus.ARCHIVED.value

    # Cascade: reject any remaining active answers (e.g. approved) to prevent further revisions
    active_statuses = [
        AnswerStatus.APPROVED.value,
        AnswerStatus.DRAFT.value,
        AnswerStatus.SUBMITTED.value,
        AnswerStatus.UNDER_REVIEW.value,
        AnswerStatus.REVISION_REQUESTED.value,
    ]
    await db.execute(
        update(Answer)
        .where(
            Answer.question_id == question.id,
            Answer.status.in_(active_statuses),
        )
        .values(status=AnswerStatus.REJECTED.value)
    )
