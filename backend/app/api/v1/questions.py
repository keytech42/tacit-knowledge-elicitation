import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.database import get_db
from app.models.answer import Answer, AnswerCollaborator, AnswerRevision
from app.models.question import AnswerOption, Question, QuestionQualityFeedback, QuestionStatus
from app.models.review import Review, ReviewComment, ReviewTargetType
from app.models.user import RoleName, User
from app.schemas.question import (
    AdminQueueItem, AdminQueueResponse, AnswerOptionBatchCreate, AnswerOptionResponse,
    AssignRespondentRequest, QualityFeedbackCreate, QualityFeedbackResponse,
    QuestionCreate, QuestionListResponse, QuestionRejectRequest, QuestionResponse, QuestionUpdate,
)
from app.services.question import (
    apply_archive, apply_close, apply_publish, apply_reject,
    apply_start_review, apply_submit, can_edit_question,
)
from app.services import slack, worker_client
from app.services.embeddings import update_question_embedding

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", response_model=QuestionResponse, status_code=201)
async def create_question(
    request: QuestionCreate,
    current_user: User = require_role(RoleName.AUTHOR, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    question = Question(
        title=request.title, body=request.body, category=request.category,
        review_policy=request.review_policy, show_suggestions=request.show_suggestions,
        created_by_id=current_user.id,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)
    return question


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    current_user: CurrentUser, db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None, skip: int = 0, limit: int = 50,
):
    query = select(Question)
    count_query = select(func.count(Question.id))
    user_roles = {r.name for r in current_user.roles}

    if RoleName.ADMIN.value not in user_roles:
        visible_statuses = [QuestionStatus.PUBLISHED.value, QuestionStatus.CLOSED.value, QuestionStatus.ARCHIVED.value]
        query = query.where((Question.status.in_(visible_statuses)) | (Question.created_by_id == current_user.id))
        count_query = count_query.where((Question.status.in_(visible_statuses)) | (Question.created_by_id == current_user.id))

    if status_filter:
        query = query.where(Question.status == status_filter)
        count_query = count_query.where(Question.status == status_filter)
    if category:
        query = query.where(Question.category == category)
        count_query = count_query.where(Question.category == category)

    result = await db.execute(query.offset(skip).limit(limit).order_by(Question.created_at.desc()))
    questions = result.scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return QuestionListResponse(questions=questions, total=total)


@router.get("/admin-queue", response_model=AdminQueueResponse)
async def admin_queue(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    actionable = [
        QuestionStatus.PROPOSED.value,
        QuestionStatus.IN_REVIEW.value,
        QuestionStatus.PUBLISHED.value,
        QuestionStatus.CLOSED.value,
    ]
    # Fetch questions with answer counts in one query
    stmt = (
        select(Question, func.count(Answer.id).label("answer_count"))
        .outerjoin(Answer, Answer.question_id == Question.id)
        .where(Question.status.in_(actionable))
        .group_by(Question.id)
        .order_by(Question.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    buckets: dict[str, list[AdminQueueItem]] = {s: [] for s in actionable}
    for question, count in rows:
        item = AdminQueueItem.model_validate(question)
        item.answer_count = count
        buckets.setdefault(question.status, []).append(item)

    return AdminQueueResponse(
        proposed=buckets.get(QuestionStatus.PROPOSED.value, []),
        in_review=buckets.get(QuestionStatus.IN_REVIEW.value, []),
        published=buckets.get(QuestionStatus.PUBLISHED.value, []),
        closed=buckets.get(QuestionStatus.CLOSED.value, []),
    )


@router.get("/categories", response_model=list[str])
async def list_categories(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(distinct(Question.category)).where(Question.category.isnot(None)))
    return [row[0] for row in result.all()]


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    user_roles = {r.name for r in current_user.roles}
    if RoleName.ADMIN.value not in user_roles:
        visible_statuses = {QuestionStatus.PUBLISHED.value, QuestionStatus.CLOSED.value, QuestionStatus.ARCHIVED.value}
        if question.status not in visible_statuses and question.created_by_id != current_user.id:
            raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.patch("/{question_id}", response_model=QuestionResponse)
async def update_question(question_id: uuid.UUID, request: QuestionUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if not can_edit_question(question, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit this question")
    if request.title is not None: question.title = request.title
    if request.body is not None: question.body = request.body
    if request.category is not None: question.category = request.category
    if request.review_policy is not None: question.review_policy = request.review_policy
    if request.show_suggestions is not None: question.show_suggestions = request.show_suggestions
    return question


@router.delete("/{question_id}", status_code=204)
async def delete_question(question_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    user_roles = {r.name for r in current_user.roles}
    if RoleName.ADMIN.value not in user_roles:
        if question.created_by_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your question")
        if question.status != QuestionStatus.DRAFT.value:
            raise HTTPException(status_code=409, detail="Can only delete draft questions")
    # Cascade-delete child records in FK-safe order
    answer_ids = select(Answer.id).where(Answer.question_id == question_id)

    # Clean up reviews and their comments targeting this question's answers
    answer_review_ids = select(Review.id).where(
        Review.target_type == ReviewTargetType.ANSWER.value,
        Review.target_id.in_(answer_ids),
    )
    await db.execute(delete(ReviewComment).where(ReviewComment.review_id.in_(answer_review_ids)))
    await db.execute(delete(Review).where(Review.id.in_(answer_review_ids)))

    # Clean up reviews targeting the question itself
    question_review_ids = select(Review.id).where(
        Review.target_type == ReviewTargetType.QUESTION.value,
        Review.target_id == question_id,
    )
    await db.execute(delete(ReviewComment).where(ReviewComment.review_id.in_(question_review_ids)))
    await db.execute(delete(Review).where(Review.id.in_(question_review_ids)))

    # Delete answer child records, then answers
    await db.execute(delete(AnswerRevision).where(AnswerRevision.answer_id.in_(answer_ids)))
    await db.execute(delete(AnswerCollaborator).where(AnswerCollaborator.answer_id.in_(answer_ids)))
    await db.execute(delete(Answer).where(Answer.question_id == question_id))
    await db.execute(delete(AnswerOption).where(AnswerOption.question_id == question_id))
    await db.execute(delete(QuestionQualityFeedback).where(QuestionQualityFeedback.question_id == question_id))
    await db.delete(question)
    await db.flush()


@router.post("/{question_id}/submit", response_model=QuestionResponse)
async def submit_question(question_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    apply_submit(question, current_user)
    return question


@router.post("/{question_id}/start-review", response_model=QuestionResponse)
async def start_review(question_id: uuid.UUID, current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    apply_start_review(question, current_user)
    return question


@router.post("/{question_id}/publish", response_model=QuestionResponse)
async def publish_question(question_id: uuid.UUID, current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    apply_publish(question, current_user)
    await update_question_embedding(db, question)
    await db.flush()
    await db.refresh(question)
    # Fire-and-forget: scaffold answer options + recommendation
    await worker_client.trigger_scaffold_options(question_id)
    thread_ts, slack_ch = await slack.notify_question_published(
        question_title=question.title,
        question_id=str(question.id),
        question_body=question.body,
        publisher_name=current_user.display_name,
    )
    if thread_ts and slack_ch:
        question.slack_thread_ts = thread_ts
        question.slack_channel = slack_ch
    return question


@router.post("/{question_id}/reject", response_model=QuestionResponse)
async def reject_question(
    question_id: uuid.UUID, request: QuestionRejectRequest | None = None,
    current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    comment = request.comment if request else None
    apply_reject(question, current_user, comment)
    await slack.notify_question_rejected(
        question_title=question.title,
        question_id=str(question.id),
        author_email=question.created_by.email if question.created_by else None,
        author_name=question.created_by.display_name if question.created_by else "Unknown",
        comment=comment,
    )
    return question


@router.post("/{question_id}/close", response_model=QuestionResponse)
async def close_question(question_id: uuid.UUID, current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    apply_close(question, current_user)
    if question.slack_thread_ts and question.slack_channel:
        await slack.notify_question_closed(
            slack_channel=question.slack_channel,
            slack_thread_ts=question.slack_thread_ts,
            question_title=question.title,
            question_id=str(question.id),
        )
    return question


@router.post("/{question_id}/archive", response_model=QuestionResponse)
async def archive_question(question_id: uuid.UUID, current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    apply_archive(question, current_user)
    return question


@router.post("/{question_id}/assign-respondent", response_model=QuestionResponse)
async def assign_respondent(
    question_id: uuid.UUID,
    request: AssignRespondentRequest,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if question.status != QuestionStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Can only assign respondents to published questions")
    user_result = await db.execute(select(User).where(User.id == request.user_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    question.assigned_respondent_id = request.user_id
    await db.flush()
    await db.refresh(question)
    return question


# Answer Options
@router.post("/{question_id}/options", response_model=list[AnswerOptionResponse], status_code=201)
async def create_answer_options(
    question_id: uuid.UUID, request: AnswerOptionBatchCreate,
    current_user: User = require_role(RoleName.AUTHOR, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    options = []
    for opt in request.options:
        option = AnswerOption(question_id=question_id, body=opt.body, display_order=opt.display_order, created_by_id=current_user.id)
        db.add(option)
        options.append(option)
    await db.flush()
    for opt in options:
        await db.refresh(opt)
    return options


@router.delete("/{question_id}/options", status_code=204)
async def delete_answer_options(
    question_id: uuid.UUID,
    current_user: User = require_role(RoleName.AUTHOR, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.execute(delete(AnswerOption).where(AnswerOption.question_id == question_id))


@router.get("/{question_id}/options", response_model=list[AnswerOptionResponse])
async def list_answer_options(question_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    user_roles = {r.name for r in current_user.roles}
    if RoleName.ADMIN.value not in user_roles and RoleName.AUTHOR.value not in user_roles:
        if not question.show_suggestions:
            return []
    result = await db.execute(select(AnswerOption).where(AnswerOption.question_id == question_id).order_by(AnswerOption.display_order))
    return result.scalars().all()


# Quality Feedback
@router.post("/{question_id}/feedback", response_model=QualityFeedbackResponse, status_code=201)
async def submit_quality_feedback(question_id: uuid.UUID, request: QualityFeedbackCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    existing = await db.execute(
        select(QuestionQualityFeedback).where(QuestionQualityFeedback.question_id == question_id, QuestionQualityFeedback.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already submitted feedback")
    feedback = QuestionQualityFeedback(question_id=question_id, user_id=current_user.id, rating=request.rating, comment=request.comment)
    db.add(feedback)
    await db.flush()
    avg_result = await db.execute(select(func.avg(QuestionQualityFeedback.rating)).where(QuestionQualityFeedback.question_id == question_id))
    question.quality_score = avg_result.scalar()
    await db.refresh(feedback)
    return feedback


@router.get("/{question_id}/feedback", response_model=list[QualityFeedbackResponse])
async def list_quality_feedback(question_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(QuestionQualityFeedback).where(QuestionQualityFeedback.question_id == question_id).order_by(QuestionQualityFeedback.created_at.desc())
    )
    return result.scalars().all()
