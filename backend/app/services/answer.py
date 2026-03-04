import difflib
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerCollaborator, AnswerRevision, AnswerStatus, RevisionTrigger
from app.models.user import RoleName, User


def can_edit_answer(answer: Answer, user: User) -> bool:
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    if answer.author_id == user.id and answer.status in (AnswerStatus.DRAFT.value, AnswerStatus.REVISION_REQUESTED.value):
        return True
    return False


async def can_revise_answer(answer: Answer, user: User, db: AsyncSession) -> bool:
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    if answer.author_id == user.id:
        return True
    result = await db.execute(
        select(AnswerCollaborator).where(AnswerCollaborator.answer_id == answer.id, AnswerCollaborator.user_id == user.id)
    )
    return result.scalar_one_or_none() is not None


def create_revision(answer: Answer, user: User, trigger: RevisionTrigger) -> AnswerRevision:
    version = answer.current_version + 1
    revision = AnswerRevision(
        answer_id=answer.id, version=version, body=answer.body,
        selected_option_id=answer.selected_option_id, created_by_id=user.id,
        trigger=trigger.value, previous_status=answer.status,
    )
    answer.current_version = version
    return revision


def submit_answer(answer: Answer, user: User) -> AnswerRevision:
    if answer.status != AnswerStatus.DRAFT.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot submit answer in {answer.status} status")
    user_roles = {r.name for r in user.roles}
    if answer.author_id != user.id and RoleName.ADMIN.value not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or admin can submit")
    revision = create_revision(answer, user, RevisionTrigger.INITIAL_SUBMIT)
    answer.status = AnswerStatus.SUBMITTED.value
    answer.submitted_at = datetime.now(timezone.utc)
    return revision


def resubmit_answer(answer: Answer, user: User) -> AnswerRevision:
    if answer.status != AnswerStatus.REVISION_REQUESTED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot resubmit answer in {answer.status} status")
    user_roles = {r.name for r in user.roles}
    if answer.author_id != user.id and RoleName.ADMIN.value not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or admin can resubmit")
    revision = create_revision(answer, user, RevisionTrigger.REVISION_AFTER_REVIEW)
    answer.status = AnswerStatus.SUBMITTED.value
    return revision


async def revise_approved_answer(answer: Answer, user: User, db: AsyncSession) -> AnswerRevision:
    if answer.status != AnswerStatus.APPROVED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Can only revise approved answers")
    if not await can_revise_answer(answer, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to revise this answer")
    revision = create_revision(answer, user, RevisionTrigger.POST_APPROVAL_UPDATE)
    answer.status = AnswerStatus.SUBMITTED.value
    answer.confirmed_by_id = None
    answer.confirmed_at = None
    return revision


def generate_diff(rev_from: AnswerRevision, rev_to: AnswerRevision) -> str:
    from_lines = rev_from.body.splitlines(keepends=True)
    to_lines = rev_to.body.splitlines(keepends=True)
    diff = difflib.unified_diff(from_lines, to_lines, fromfile=f"version {rev_from.version}", tofile=f"version {rev_to.version}")
    return "".join(diff)


async def can_manage_collaborators(answer: Answer, user: User) -> bool:
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    return answer.author_id == user.id
