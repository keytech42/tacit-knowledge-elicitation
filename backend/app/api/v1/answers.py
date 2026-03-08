import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.database import get_db
from app.models.answer import (
    Answer,
    AnswerCollaborator,
    AnswerRevision,
    AnswerStatus,
)
from app.models.question import Question, QuestionStatus
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import RoleName, User
from app.schemas.answer import (
    AnswerCreate,
    AnswerDiffResponse,
    AnswerListResponse,
    AnswerResponse,
    AnswerRevisionResponse,
    AnswerUpdate,
    CollaboratorAdd,
    CollaboratorResponse,
    StagingDiffResponse,
)
from app.services.answer import (
    can_edit_answer,
    can_manage_collaborators,
    generate_diff,
    generate_staging_diff,
    resubmit_answer,
    revise_approved_answer,
    submit_answer,
)
from app.services import slack, worker_client
from app.services.embeddings import update_answer_embedding

router = APIRouter(tags=["answers"])


# Nested under questions
questions_answers_router = APIRouter(prefix="/questions/{question_id}/answers", tags=["answers"])


@questions_answers_router.post("", response_model=AnswerResponse, status_code=201)
async def create_answer(
    question_id: uuid.UUID,
    request: AnswerCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a draft answer for a published question."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.status != QuestionStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can only answer published questions",
        )

    answer = Answer(
        question_id=question_id,
        author_id=current_user.id,
        body=request.body,
        selected_option_id=request.selected_option_id,
    )
    db.add(answer)
    await db.flush()
    await db.refresh(answer)
    return answer


@questions_answers_router.get("", response_model=AnswerListResponse)
async def list_answers_for_question(
    question_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    status_filter: str | None = Query(None, alias="status"),
):
    """List answers for a question."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    query = select(Answer).where(Answer.question_id == question_id)
    count_query = select(func.count(Answer.id)).where(Answer.question_id == question_id)

    if status_filter:
        query = query.where(Answer.status == status_filter)
        count_query = count_query.where(Answer.status == status_filter)

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(Answer.created_at.desc())
    )
    answers = result.scalars().all()
    total = (await db.execute(count_query)).scalar() or 0

    return AnswerListResponse(answers=answers, total=total)


# Direct answer routes
answers_router = APIRouter(prefix="/answers", tags=["answers"])


@answers_router.get("/{answer_id}", response_model=AnswerResponse)
async def get_answer(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single answer by ID."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    return answer


@answers_router.patch("/{answer_id}", response_model=AnswerResponse)
async def update_answer(
    answer_id: uuid.UUID,
    request: AnswerUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update a draft or revision_requested answer."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    if not can_edit_answer(answer, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit this answer in its current state",
        )

    if request.body is not None:
        answer.body = request.body
    if request.selected_option_id is not None:
        answer.selected_option_id = request.selected_option_id

    return answer


@answers_router.post("/{answer_id}/submit", response_model=AnswerResponse)
async def submit_answer_endpoint(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer for review (draft → submitted). Creates revision v1."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    if answer.status == AnswerStatus.REVISION_REQUESTED.value:
        resubmit_answer(answer, current_user)
        await db.flush()

        # Reset reviews that requested changes: same reviewer re-reviews the same version
        prev_reviews_result = await db.execute(
            select(Review).where(
                Review.target_type == ReviewTargetType.ANSWER.value,
                Review.target_id == answer.id,
                Review.answer_version == answer.current_version,
                Review.verdict == ReviewVerdict.CHANGES_REQUESTED.value,
            )
        )
        prev_reviews = prev_reviews_result.scalars().all()
        for review in prev_reviews:
            review.verdict = ReviewVerdict.PENDING.value
        # If reviewers were reset, move directly to under_review
        if prev_reviews:
            answer.status = AnswerStatus.UNDER_REVIEW.value
        await update_answer_embedding(db, answer)
        await db.flush()
        await db.refresh(answer)
    else:
        revision = submit_answer(answer, current_user)
        db.add(revision)
        await update_answer_embedding(db, answer)
        await db.flush()
        await db.refresh(answer)

    # Fire-and-forget: trigger AI review assist
    await worker_client.trigger_review_assist(answer.id)

    # Notify Slack
    question_result = await db.execute(select(Question).where(Question.id == answer.question_id))
    question = question_result.scalar_one_or_none()
    logger = logging.getLogger(__name__)
    logger.info(
        "Answer submit Slack notify: question=%s, slack_channel=%s, slack_thread_ts=%s",
        answer.question_id,
        question.slack_channel if question else None,
        question.slack_thread_ts if question else None,
    )
    await slack.notify_answer_submitted(
        question_title=question.title if question else "Unknown",
        question_id=str(answer.question_id),
        answer_id=str(answer.id),
        author_name=current_user.display_name,
        slack_channel=question.slack_channel if question else None,
        slack_thread_ts=question.slack_thread_ts if question else None,
    )

    return answer


@answers_router.post("/{answer_id}/revise", response_model=AnswerResponse)
async def revise_answer_endpoint(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    request: AnswerUpdate | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Post-approval revision. Accepts optional new content, creates new revision and resets to submitted."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    revision = await revise_approved_answer(
        answer, current_user, db,
        new_body=request.body if request else None,
        new_selected_option_id=request.selected_option_id if request else None,
    )
    db.add(revision)
    return answer


# Version history and diff

@answers_router.get("/{answer_id}/versions", response_model=list[AnswerRevisionResponse])
async def list_versions(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List all revisions for an answer."""
    result = await db.execute(
        select(AnswerRevision)
        .where(AnswerRevision.answer_id == answer_id)
        .order_by(AnswerRevision.version)
    )
    return result.scalars().all()


@answers_router.get("/{answer_id}/versions/{version}", response_model=AnswerRevisionResponse)
async def get_version(
    answer_id: uuid.UUID,
    version: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific revision."""
    result = await db.execute(
        select(AnswerRevision).where(
            AnswerRevision.answer_id == answer_id,
            AnswerRevision.version == version,
        )
    )
    revision = result.scalar_one_or_none()
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    return revision


@answers_router.get("/{answer_id}/diff", response_model=AnswerDiffResponse)
async def get_diff(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
):
    """Get a diff between two revisions."""
    rev_from_result = await db.execute(
        select(AnswerRevision).where(
            AnswerRevision.answer_id == answer_id,
            AnswerRevision.version == from_version,
        )
    )
    rev_from = rev_from_result.scalar_one_or_none()

    rev_to_result = await db.execute(
        select(AnswerRevision).where(
            AnswerRevision.answer_id == answer_id,
            AnswerRevision.version == to_version,
        )
    )
    rev_to = rev_to_result.scalar_one_or_none()

    if not rev_from or not rev_to:
        raise HTTPException(status_code=404, detail="One or both revisions not found")

    diff_text = generate_diff(rev_from, rev_to)

    return AnswerDiffResponse(
        from_version=from_version,
        to_version=to_version,
        diff=diff_text,
        from_created_at=rev_from.created_at,
        to_created_at=rev_to.created_at,
    )


@answers_router.get("/{answer_id}/staging-diff", response_model=StagingDiffResponse)
async def get_staging_diff(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Compare the current working copy against the latest committed revision."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    diff_text = generate_staging_diff(answer)
    latest_version = answer.revisions[-1].version if answer.revisions else None

    return StagingDiffResponse(
        has_changes=diff_text is not None,
        latest_version=latest_version,
        diff=diff_text,
    )


# Collaborators

@answers_router.post(
    "/{answer_id}/collaborators",
    response_model=CollaboratorResponse,
    status_code=201,
)
async def add_collaborator(
    answer_id: uuid.UUID,
    request: CollaboratorAdd,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Add a collaborator to an answer (author/admin only)."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    if not await can_manage_collaborators(answer, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or admin can manage collaborators",
        )

    # Check user exists
    target_result = await db.execute(select(User).where(User.id == request.user_id))
    target_user = target_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check not already collaborator
    existing = await db.execute(
        select(AnswerCollaborator).where(
            AnswerCollaborator.answer_id == answer_id,
            AnswerCollaborator.user_id == request.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a collaborator")

    collab = AnswerCollaborator(
        answer_id=answer_id,
        user_id=request.user_id,
        granted_by_id=current_user.id,
    )
    db.add(collab)
    await db.flush()
    await db.refresh(collab)
    return collab


@answers_router.get("/{answer_id}/collaborators", response_model=list[CollaboratorResponse])
async def list_collaborators(
    answer_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List collaborators for an answer."""
    result = await db.execute(
        select(AnswerCollaborator).where(AnswerCollaborator.answer_id == answer_id)
    )
    return result.scalars().all()


@answers_router.delete("/{answer_id}/collaborators/{user_id}", status_code=204)
async def remove_collaborator(
    answer_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Remove a collaborator (author/admin only)."""
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    if not await can_manage_collaborators(answer, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or admin can manage collaborators",
        )

    collab_result = await db.execute(
        select(AnswerCollaborator).where(
            AnswerCollaborator.answer_id == answer_id,
            AnswerCollaborator.user_id == user_id,
        )
    )
    collab = collab_result.scalar_one_or_none()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    await db.delete(collab)
