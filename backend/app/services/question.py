from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.question import Confirmation, Question, QuestionStatus
from app.models.user import RoleName, User

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


def apply_close(question: Question, user: User) -> None:
    validate_transition(question, QuestionStatus.CLOSED, user)
    question.status = QuestionStatus.CLOSED.value
    question.closed_at = datetime.now(timezone.utc)


def apply_archive(question: Question, user: User) -> None:
    validate_transition(question, QuestionStatus.ARCHIVED, user)
    question.status = QuestionStatus.ARCHIVED.value
