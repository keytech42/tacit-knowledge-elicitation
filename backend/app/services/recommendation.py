"""Respondent recommendation based on embedding similarity + structured scoring."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question
from app.models.user import User

logger = logging.getLogger(__name__)


async def recommend_respondents(
    db: AsyncSession,
    question_id: uuid.UUID,
    top_k: int = 5,
) -> list[dict]:
    """Recommend respondents for a question based on embedding similarity and scoring.

    Scoring formula:
    0.4 * semantic_similarity + 0.3 * approval_rate + 0.2 * category_match + 0.1 * recency

    Returns a list of dicts: [{user_id, display_name, score, reasoning}]
    """
    # Get the question
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        return []

    if question.embedding is None:
        logger.warning(f"Question {question_id} has no embedding, cannot recommend")
        return []

    # Find answers with embeddings, compute cosine similarity
    # pgvector: 1 - (embedding <=> query_embedding) gives cosine similarity
    similarity_expr = (1 - Answer.embedding.cosine_distance(question.embedding)).label("similarity")

    answers_with_similarity = await db.execute(
        select(Answer.author_id, func.max(similarity_expr).label("max_similarity"))
        .where(Answer.embedding.isnot(None))
        .group_by(Answer.author_id)
    )
    author_similarities = {row.author_id: row.max_similarity for row in answers_with_similarity.all()}

    if not author_similarities:
        return []

    # Get approval rates per author
    approval_counts = await db.execute(
        select(
            Answer.author_id,
            func.count(Answer.id).label("total"),
            func.count(Answer.id).filter(Answer.status == AnswerStatus.APPROVED.value).label("approved"),
        )
        .where(Answer.author_id.in_(author_similarities.keys()))
        .group_by(Answer.author_id)
    )
    author_approval = {}
    for row in approval_counts.all():
        rate = row.approved / row.total if row.total > 0 else 0
        author_approval[row.author_id] = rate

    # Category match: does the author have answers in this category?
    category_match_authors = set()
    if question.category:
        cat_result = await db.execute(
            select(Answer.author_id)
            .join(Question, Answer.question_id == Question.id)
            .where(
                Question.category == question.category,
                Answer.author_id.in_(author_similarities.keys()),
            )
            .distinct()
        )
        category_match_authors = {row[0] for row in cat_result.all()}

    # Recency: most recent answer timestamp per author
    recency_result = await db.execute(
        select(Answer.author_id, func.max(Answer.created_at).label("last_answer"))
        .where(Answer.author_id.in_(author_similarities.keys()))
        .group_by(Answer.author_id)
    )
    now = datetime.now(timezone.utc)
    author_recency = {}
    for row in recency_result.all():
        if row.last_answer:
            days_ago = (now - row.last_answer.replace(tzinfo=timezone.utc)).days
            # Normalize: 1.0 for today, decays over 365 days
            author_recency[row.author_id] = max(0.0, 1.0 - days_ago / 365.0)
        else:
            author_recency[row.author_id] = 0.0

    # Get user details
    user_result = await db.execute(
        select(User).where(User.id.in_(author_similarities.keys()))
    )
    users = {u.id: u for u in user_result.scalars().all()}

    # Compute composite scores
    scored = []
    for author_id, similarity in author_similarities.items():
        user = users.get(author_id)
        if not user:
            continue

        sem = float(similarity) if similarity else 0.0
        approval = author_approval.get(author_id, 0.0)
        cat_match = 1.0 if author_id in category_match_authors else 0.0
        recency = author_recency.get(author_id, 0.0)

        score = 0.4 * sem + 0.3 * approval + 0.2 * cat_match + 0.1 * recency

        reasoning_parts = []
        if sem > 0.5:
            reasoning_parts.append(f"strong semantic match ({sem:.0%})")
        if approval > 0.7:
            reasoning_parts.append(f"high approval rate ({approval:.0%})")
        if cat_match:
            reasoning_parts.append("experience in this category")
        if recency > 0.5:
            reasoning_parts.append("recently active")

        scored.append({
            "user_id": str(author_id),
            "display_name": user.display_name,
            "score": round(score, 3),
            "reasoning": "; ".join(reasoning_parts) if reasoning_parts else "general experience",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
