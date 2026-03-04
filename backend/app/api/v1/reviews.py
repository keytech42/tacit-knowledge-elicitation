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
from app.services.review import auto_assign_reviewers, resolve_answer_reviews

router = APIRouter(prefix="/reviews", tags=["reviews"])


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

    review = Review(
        target_type=request.target_type,
        target_id=request.target_id,
        reviewer_id=current_user.id,
        answer_version=target.current_version if request.target_type == "answer" else None,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
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
    return result.scalars().all()


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
    return result.scalars().all()


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
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
    if review.target_type == ReviewTargetType.ANSWER.value:
        await db.flush()
        await resolve_answer_reviews(review.target_id, db)

    await db.refresh(review)
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
