"""Respondent recommendation — embedding similarity or LLM-based."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.answer import Answer, AnswerStatus
from app.models.question import Question
from app.models.user import User

logger = logging.getLogger(__name__)

# Max recent answers per candidate to include in LLM context
_MAX_ANSWERS_PER_CANDIDATE = 10


def _resolve_strategy() -> str:
    """Resolve 'auto' to a concrete strategy based on available infrastructure."""
    strategy = settings.RECOMMENDATION_STRATEGY
    if strategy != "auto":
        return strategy
    # Auto: prefer embedding if model is configured, otherwise LLM
    if settings.EMBEDDING_MODEL:
        return "embedding"
    return "llm"


async def recommend_respondents(
    db: AsyncSession,
    question_id: uuid.UUID,
    top_k: int = 5,
) -> dict:
    """Dispatch to the configured recommendation strategy.

    Returns a dict: {items: [{user_id, display_name, score, reasoning}], reason: str | None}
    """
    strategy = _resolve_strategy()

    if strategy == "embedding":
        return await _recommend_via_embedding(db, question_id, top_k)
    elif strategy == "llm":
        return await _recommend_via_llm(db, question_id, top_k)
    else:
        logger.error(f"Unknown RECOMMENDATION_STRATEGY: {strategy}")
        return {"items": [], "reason": f"Unknown strategy: {strategy}"}


async def _build_candidate_context(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> tuple[dict | None, list[dict]]:
    """Gather question and candidate data from DB for LLM recommendation.

    Returns (question_dict, candidates_list).
    """
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        return None, []

    question_dict = {
        "title": question.title,
        "body": question.body,
        "category": question.category,
    }

    # Get all answers with their questions and authors
    answer_result = await db.execute(
        select(Answer)
        .join(Question, Answer.question_id == Question.id)
        .where(Answer.author_id.isnot(None))
        .order_by(Answer.created_at.desc())
    )
    answers = answer_result.scalars().all()

    # Build candidate profiles
    candidates_map: dict[uuid.UUID, dict] = {}
    for ans in answers:
        author_id = ans.author_id
        if author_id not in candidates_map:
            author = ans.author
            candidates_map[author_id] = {
                "user_id": str(author_id),
                "display_name": author.display_name if author else "Unknown",
                "answer_summaries": [],
            }
        if len(candidates_map[author_id]["answer_summaries"]) < _MAX_ANSWERS_PER_CANDIDATE:
            q = ans.question
            candidates_map[author_id]["answer_summaries"].append({
                "question_title": q.title if q else "?",
                "category": q.category if q else "none",
                "status": ans.status,
            })

    return question_dict, list(candidates_map.values())


async def _recommend_via_llm(
    db: AsyncSession,
    question_id: uuid.UUID,
    top_k: int = 5,
) -> dict:
    """Delegate recommendation to the worker's LLM-based recommender."""
    from app.services import worker_client

    if not settings.WORKER_URL:
        return {
            "items": [],
            "reason": (
                "LLM recommendation requires WORKER_URL to be configured. "
                "Either set WORKER_URL or switch RECOMMENDATION_STRATEGY to 'embedding'."
            ),
        }

    question_dict, candidates = await _build_candidate_context(db, question_id)
    if question_dict is None:
        return {"items": [], "reason": "Question not found."}
    if not candidates:
        return {"items": [], "reason": "No respondents with answer history found."}

    result = await worker_client.trigger_recommend(
        question=question_dict,
        candidates=candidates,
        top_k=top_k,
    )
    if result is None:
        return {
            "items": [],
            "reason": "Worker service did not respond. Check worker logs.",
        }
    return result


async def _recommend_via_embedding(
    db: AsyncSession,
    question_id: uuid.UUID,
    top_k: int = 5,
) -> dict:
    """Recommend respondents based on embedding similarity and structured scoring.

    Scoring formula:
    0.4 * semantic_similarity + 0.3 * approval_rate + 0.2 * category_match + 0.1 * recency
    """
    def _empty(reason: str) -> dict:
        return {"items": [], "reason": reason}

    # Get the question
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        return _empty("Question not found.")

    if question.embedding is None:
        logger.warning(f"Question {question_id} has no embedding, cannot recommend")
        return _empty(
            "This question has no embedding. "
            "Set EMBEDDING_MODEL and the corresponding API key (e.g. OPENAI_API_KEY) "
            "in your environment, then re-publish the question to generate embeddings."
        )

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
        return _empty(
            "No answers with embeddings found. "
            "Recommendations require submitted answers that have been embedded."
        )

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
    return {"items": scored[:top_k], "reason": None}
