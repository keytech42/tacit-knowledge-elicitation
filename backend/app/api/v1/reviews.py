import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.database import get_db
from app.models.answer import Answer, AnswerStatus
from app.models.question import Question
from app.models.review import Review, ReviewComment, ReviewTargetType, ReviewVerdict
from app.models.user import RoleName, User
from app.schemas.review import ReviewCommentCreate, ReviewCommentResponse, ReviewCreate, ReviewResponse, ReviewUpdate
from app.services import slack
from app.services.review import auto_assign_reviewers, resolve_answer_reviews

router = APIRouter(prefix="/reviews", tags=["reviews"])


async def _enrich_question_titles(reviews: list[Review], db: AsyncSession) -> None:
    """Set question_title on each review object for API serialization."""
    if not reviews:
        return

    answer_reviews = [r for r in reviews if r.target_type == ReviewTargetType.ANSWER.value]
    question_reviews = [r for r in reviews if r.target_type == ReviewTargetType.QUESTION.value]

    # Resolve question titles for answer reviews (answer → question)
    answer_ids = {r.target_id for r in answer_reviews}
    if answer_ids:
        result = await db.execute(select(Answer).where(Answer.id.in_(answer_ids)))
        answers = {a.id: a for a in result.scalars().all()}
        question_ids = {a.question_id for a in answers.values()}
        result = await db.execute(select(Question).where(Question.id.in_(question_ids)))
        questions = {q.id: q for q in result.scalars().all()}
        for r in answer_reviews:
            answer = answers.get(r.target_id)
            if answer:
                q = questions.get(answer.question_id)
                if q:
                    r.question_title = q.title  # type: ignore[attr-defined]

    # Resolve question titles for question reviews (direct)
    q_ids = {r.target_id for r in question_reviews}
    if q_ids:
        result = await db.execute(select(Question).where(Question.id.in_(q_ids)))
        questions = {q.id: q for q in result.scalars().all()}
        for r in question_reviews:
            q = questions.get(r.target_id)
            if q:
                r.question_title = q.title  # type: ignore[attr-defined]


@router.post("", response_model=ReviewResponse, status_code=201)
async def create_review(
    request: ReviewCreate,
    current_user: User = require_role(RoleName.REVIEWER, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Create a new review for a question or answer."""
    # Validate target exists
    if request.target_type == "answer":
        result = await db.execute(select(Answer).where(Answer.id == request.target_id))
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Answer not found")
        if target.status not in (AnswerStatus.SUBMITTED.value, AnswerStatus.UNDER_REVIEW.value):
            raise HTTPException(status_code=409, detail="Answer is not in a reviewable state")
        # Move to under_review if submitted
        if target.status == AnswerStatus.SUBMITTED.value:
            target.status = AnswerStatus.UNDER_REVIEW.value
    elif request.target_type == "question":
        result = await db.execute(select(Question).where(Question.id == request.target_id))
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Question not found")
    else:
        raise HTTPException(status_code=400, detail="target_type must be 'question' or 'answer'")

    # Prevent duplicate: reject if this reviewer already has a pending review for the same target and version
    existing_query = select(Review).where(
        Review.target_type == request.target_type,
        Review.target_id == request.target_id,
        Review.reviewer_id == current_user.id,
        Review.verdict == ReviewVerdict.PENDING.value,
    )
    if request.target_type == "answer":
        existing_query = existing_query.where(Review.answer_version == target.current_version)
    existing_result = await db.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending review for this target",
        )

    review = Review(
        target_type=request.target_type,
        target_id=request.target_id,
        reviewer_id=current_user.id,
        answer_version=target.current_version if request.target_type == "answer" else None,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    await _enrich_question_titles([review], db)
    return review


@router.get("", response_model=list[ReviewResponse])
async def list_reviews(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
):
    """List reviews with optional filters."""
    query = select(Review)
    if target_type:
        query = query.where(Review.target_type == target_type)
    if target_id:
        query = query.where(Review.target_id == target_id)
    if reviewer_id:
        query = query.where(Review.reviewer_id == reviewer_id)

    result = await db.execute(query.order_by(Review.created_at.desc()))
    reviews = list(result.scalars().all())
    await _enrich_question_titles(reviews, db)
    return reviews


@router.get("/my-queue", response_model=list[ReviewResponse])
async def my_review_queue(
    current_user: User = require_role(RoleName.REVIEWER, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's pending reviews."""
    result = await db.execute(
        select(Review).where(
            Review.reviewer_id == current_user.id,
            Review.verdict == ReviewVerdict.PENDING.value,
        ).order_by(Review.created_at.asc())
    )
    reviews = list(result.scalars().all())
    await _enrich_question_titles(reviews, db)
    return reviews


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    await _enrich_question_titles([review], db)
    return review


@router.patch("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: uuid.UUID,
    request: ReviewUpdate,
    current_user: User = require_role(RoleName.REVIEWER, RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Submit a verdict on a review."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.reviewer_id != current_user.id:
        user_roles = {r.name for r in current_user.roles}
        if RoleName.ADMIN.value not in user_roles:
            raise HTTPException(status_code=403, detail="Not your review")

    # Validate verdict
    try:
        verdict = ReviewVerdict(request.verdict)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid verdict: {request.verdict}")

    review.verdict = verdict.value
    review.comment = request.comment

    # Resolve answer status if this is an answer review
    answer_status_before = None
    if review.target_type == ReviewTargetType.ANSWER.value:
        answer_result = await db.execute(select(Answer).where(Answer.id == review.target_id))
        answer = answer_result.scalar_one_or_none()
        answer_status_before = answer.status if answer else None
        await db.flush()
        await resolve_answer_reviews(review.target_id, db)

    await db.refresh(review)
    await _enrich_question_titles([review], db)

    # Slack notifications for review verdicts on answers
    if review.target_type == ReviewTargetType.ANSWER.value and answer:
        await db.refresh(answer)
        question_result = await db.execute(select(Question).where(Question.id == answer.question_id))
        question = question_result.scalar_one_or_none()
        q_title = question.title if question else "Unknown"

        # Notify about the individual review verdict
        await slack.notify_review_verdict(
            question_title=q_title,
            answer_id=str(answer.id),
            verdict=verdict.value,
            reviewer_name=current_user.display_name,
            author_email=answer.author.email if answer.author else None,
            author_name=answer.author.display_name if answer.author else "Unknown",
            comment=request.comment,
            slack_channel=question.slack_channel if question else None,
            slack_thread_ts=question.slack_thread_ts if question else None,
        )

        # Notify about answer status changes from review resolution
        if answer.status != answer_status_before:
            if answer.status == AnswerStatus.APPROVED.value:
                await slack.notify_answer_approved(
                    question_title=q_title,
                    answer_id=str(answer.id),
                    author_email=answer.author.email if answer.author else None,
                    author_name=answer.author.display_name if answer.author else "Unknown",
                    slack_channel=question.slack_channel if question else None,
                    slack_thread_ts=question.slack_thread_ts if question else None,
                )
            elif answer.status == AnswerStatus.REVISION_REQUESTED.value:
                await slack.notify_revision_requested(
                    question_title=q_title,
                    answer_id=str(answer.id),
                    author_email=answer.author.email if answer.author else None,
                    author_name=answer.author.display_name if answer.author else "Unknown",
                    slack_channel=question.slack_channel if question else None,
                    slack_thread_ts=question.slack_thread_ts if question else None,
                )
                await slack.notify_changes_requested_dm(
                    question_title=q_title,
                    question_id=str(answer.question_id),
                    answer_id=str(answer.id),
                    author_email=answer.author.email if answer.author else None,
                    author_name=answer.author.display_name if answer.author else "Unknown",
                    reviewer_name=current_user.display_name,
                    comment=request.comment,
                )

    return review


@router.post("/{review_id}/comments", response_model=ReviewCommentResponse, status_code=201)
async def add_review_comment(
    review_id: uuid.UUID,
    request: ReviewCommentCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a review (threaded)."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if request.parent_id:
        parent_result = await db.execute(
            select(ReviewComment).where(ReviewComment.id == request.parent_id, ReviewComment.review_id == review_id)
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent comment not found")

    comment = ReviewComment(
        review_id=review_id, author_id=current_user.id,
        body=request.body, parent_id=request.parent_id,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment
