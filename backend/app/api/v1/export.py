from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.database import get_db
from app.models.answer import Answer
from app.models.question import Question
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import RoleName, User
from app.schemas.export import EmbeddingRow, ReviewPairRow, TrainingDataRow

router = APIRouter(prefix="/export", tags=["export"])


def _jsonl_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="application/x-ndjson")


@router.get("/training-data")
async def export_training_data(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    question_status: str | None = Query(None),
    category: str | None = Query(None),
):
    """Stream Q&A pairs as JSONL for training data."""

    async def generate() -> AsyncGenerator[str, None]:
        query = (
            select(Answer)
            .join(Question, Answer.question_id == Question.id)
            .options(
                selectinload(Answer.question).selectinload(Question.answer_options),
                selectinload(Answer.selected_option),
            )
        )

        if date_from:
            query = query.where(Answer.created_at >= date_from)
        if date_to:
            query = query.where(Answer.created_at <= date_to)
        if question_status:
            query = query.where(Question.status == question_status)
        if category:
            query = query.where(Question.category == category)

        query = query.order_by(Answer.created_at)

        # Fetch reviews for answer targets in bulk
        result = await db.execute(query)
        answers = result.scalars().all()

        if not answers:
            return

        answer_ids = [a.id for a in answers]
        review_query = select(Review).where(
            Review.target_type == ReviewTargetType.ANSWER.value,
            Review.target_id.in_(answer_ids),
        )
        review_result = await db.execute(review_query)
        reviews = review_result.scalars().all()

        # Group verdicts by answer id
        verdicts_by_answer: dict = {}
        for r in reviews:
            verdicts_by_answer.setdefault(r.target_id, []).append(r.verdict)

        for answer in answers:
            q = answer.question
            selected_body = answer.selected_option.body if answer.selected_option else None
            row = TrainingDataRow(
                question_id=q.id,
                question_title=q.title,
                question_body=q.body,
                question_category=q.category,
                question_status=q.status,
                quality_score=q.quality_score,
                source_type=q.source_type,
                answer_id=answer.id,
                answer_body=answer.body,
                answer_status=answer.status,
                answer_version=answer.current_version,
                selected_option=selected_body,
                review_verdicts=verdicts_by_answer.get(answer.id, []),
                created_at=answer.created_at,
            )
            yield row.model_dump_json() + "\n"

    return _jsonl_response(generate())


@router.get("/embeddings")
async def export_embeddings(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = Query(None, pattern="^(question|answer|both)$"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """Stream entity embeddings as JSONL."""

    async def generate() -> AsyncGenerator[str, None]:
        include_questions = entity_type in (None, "question", "both")
        include_answers = entity_type in (None, "answer", "both")

        if include_questions:
            q_query = select(Question).where(Question.embedding.isnot(None))
            if date_from:
                q_query = q_query.where(Question.created_at >= date_from)
            if date_to:
                q_query = q_query.where(Question.created_at <= date_to)
            q_query = q_query.order_by(Question.created_at)

            result = await db.execute(q_query)
            for question in result.scalars().all():
                row = EmbeddingRow(
                    entity_type="question",
                    entity_id=question.id,
                    embedding=list(question.embedding),
                )
                yield row.model_dump_json() + "\n"

        if include_answers:
            a_query = select(Answer).where(Answer.embedding.isnot(None))
            if date_from:
                a_query = a_query.where(Answer.created_at >= date_from)
            if date_to:
                a_query = a_query.where(Answer.created_at <= date_to)
            a_query = a_query.order_by(Answer.created_at)

            result = await db.execute(a_query)
            for answer in result.scalars().all():
                row = EmbeddingRow(
                    entity_type="answer",
                    entity_id=answer.id,
                    embedding=list(answer.embedding),
                )
                yield row.model_dump_json() + "\n"

    return _jsonl_response(generate())


@router.get("/review-pairs")
async def export_review_pairs(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    verdict: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """Stream answer-review pairs as JSONL for RLHF."""

    async def generate() -> AsyncGenerator[str, None]:
        query = (
            select(Review)
            .where(
                Review.target_type == ReviewTargetType.ANSWER.value,
                Review.verdict != ReviewVerdict.PENDING.value,
            )
        )

        if verdict:
            query = query.where(Review.verdict == verdict)
        if date_from:
            query = query.where(Review.created_at >= date_from)
        if date_to:
            query = query.where(Review.created_at <= date_to)

        query = query.order_by(Review.created_at)
        result = await db.execute(query)
        reviews = result.scalars().all()

        if not reviews:
            return

        # Fetch answers and questions in bulk
        answer_ids = list({r.target_id for r in reviews})
        answer_result = await db.execute(
            select(Answer)
            .where(Answer.id.in_(answer_ids))
            .options(selectinload(Answer.question))
        )
        answers_by_id = {a.id: a for a in answer_result.scalars().all()}

        for review in reviews:
            answer = answers_by_id.get(review.target_id)
            if not answer:
                continue
            row = ReviewPairRow(
                answer_id=answer.id,
                question_id=answer.question_id,
                question_title=answer.question.title,
                answer_body=answer.body,
                answer_version=answer.current_version,
                review_verdict=review.verdict,
                review_comment=review.comment,
                reviewer_id=review.reviewer_id,
                created_at=review.created_at,
            )
            yield row.model_dump_json() + "\n"

    return _jsonl_response(generate())
