import difflib
import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerCollaborator, AnswerRevision, AnswerStatus, RevisionTrigger
from app.models.user import RoleName, User


def normalize_body(text: str) -> str:
    """Normalize answer body for content comparison: strip trailing whitespace per line, strip trailing blank lines."""
    lines = [line.rstrip() for line in text.splitlines()]
    # Strip trailing blank lines
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def compute_content_hash(text: str) -> str:
    """SHA-256 hex digest of the normalized body text."""
    return hashlib.sha256(normalize_body(text).encode("utf-8")).hexdigest()


def can_edit_answer(answer: Answer, user: User) -> bool:
    if answer.status not in (AnswerStatus.DRAFT.value, AnswerStatus.REVISION_REQUESTED.value):
        return False
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    if answer.author_id == user.id:
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


def create_revision(answer: Answer, user: User, trigger: RevisionTrigger, *, check_duplicate: bool = False) -> AnswerRevision:
    new_hash = compute_content_hash(answer.body)

    # For resubmits/revisions, reject if content is identical to the latest revision
    if check_duplicate and answer.revisions:
        latest = answer.revisions[-1]  # ordered by version (selectin)
        latest_hash = latest.content_hash or compute_content_hash(latest.body)
        if new_hash == latest_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No changes detected — the content is identical to the previous version",
            )

    version = answer.current_version + 1
    revision = AnswerRevision(
        answer_id=answer.id, version=version, body=answer.body,
        selected_option_id=answer.selected_option_id, created_by_id=user.id,
        trigger=trigger.value, previous_status=answer.status,
        content_hash=new_hash,
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
    """Resubmit after changes requested — creates a new immutable version."""
    if answer.status != AnswerStatus.REVISION_REQUESTED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot resubmit answer in {answer.status} status")
    user_roles = {r.name for r in user.roles}
    if answer.author_id != user.id and RoleName.ADMIN.value not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or admin can resubmit")

    revision = create_revision(answer, user, RevisionTrigger.REVISION_AFTER_REVIEW, check_duplicate=True)
    answer.status = AnswerStatus.SUBMITTED.value
    return revision


async def revise_approved_answer(
    answer: Answer, user: User, db: AsyncSession,
    *, new_body: str | None = None, new_selected_option_id=None,
) -> AnswerRevision:
    if answer.status != AnswerStatus.APPROVED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Can only revise approved answers")
    if not await can_revise_answer(answer, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to revise this answer")
    # Apply new content before snapshotting the revision
    if new_body is not None:
        answer.body = new_body
    if new_selected_option_id is not None:
        answer.selected_option_id = new_selected_option_id
    revision = create_revision(answer, user, RevisionTrigger.POST_APPROVAL_UPDATE, check_duplicate=True)
    answer.status = AnswerStatus.SUBMITTED.value
    answer.confirmed_by_id = None
    answer.confirmed_at = None
    return revision


def generate_diff(rev_from: AnswerRevision, rev_to: AnswerRevision) -> str:
    # Ensure each line ends with \n so unified_diff produces proper line breaks
    from_lines = [line + "\n" for line in rev_from.body.splitlines()]
    to_lines = [line + "\n" for line in rev_to.body.splitlines()]
    diff = difflib.unified_diff(from_lines, to_lines, fromfile=f"version {rev_from.version}", tofile=f"version {rev_to.version}")
    return "".join(diff)


def generate_staging_diff(answer: Answer) -> str | None:
    """Diff between the latest committed revision and the current working copy.

    Returns None when there are no committed revisions yet or the content
    is identical (nothing staged).
    """
    if not answer.revisions:
        return None
    latest = answer.revisions[-1]
    if normalize_body(answer.body) == normalize_body(latest.body):
        return None
    from_lines = [line + "\n" for line in latest.body.splitlines()]
    to_lines = [line + "\n" for line in answer.body.splitlines()]
    diff = difflib.unified_diff(from_lines, to_lines, fromfile=f"version {latest.version}", tofile="working copy")
    return "".join(diff)


async def can_manage_collaborators(answer: Answer, user: User) -> bool:
    user_roles = {r.name for r in user.roles}
    if RoleName.ADMIN.value in user_roles:
        return True
    return answer.author_id == user.id
