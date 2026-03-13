import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerRevision
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.services.answer import generate_diff


async def get_answer_activity(
    answer_id: uuid.UUID, db: AsyncSession, *, include_diffs: bool = False
) -> dict:
    """Build a chronological activity timeline for an answer.

    Returns a dict with keys: events, current_version, answer_status.
    """
    # Fetch answer
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if answer is None:
        return {"events": [], "current_version": 0, "answer_status": "unknown"}

    # Fetch revisions
    rev_result = await db.execute(
        select(AnswerRevision)
        .where(AnswerRevision.answer_id == answer_id)
        .order_by(AnswerRevision.version)
    )
    revisions = rev_result.scalars().all()

    # Fetch reviews
    review_result = await db.execute(
        select(Review).where(
            Review.target_type == ReviewTargetType.ANSWER.value,
            Review.target_id == answer_id,
        )
    )
    reviews = review_result.scalars().all()

    events: list[dict] = []

    # Build revision-by-version lookup for diff computation
    rev_by_version = {r.version: r for r in revisions}

    # Version submitted events
    for rev in revisions:
        diff = None
        if include_diffs and rev.version > 1:
            prev_rev = rev_by_version.get(rev.version - 1)
            if prev_rev:
                diff = generate_diff(prev_rev, rev)

        events.append({
            "type": "version_submitted",
            "timestamp": rev.created_at,
            "actor": rev.created_by,
            "version": rev.version,
            "trigger": rev.trigger,
            "diff": diff,
            "review_id": None,
            "reviewer": None,
            "assigned_by": None,
            "verdict": None,
            "comment": None,
            "answer_version": None,
            "is_stale": None,
            "self_assigned": None,
        })

    # Reviewer assigned events (from all reviews at created_at)
    for review in reviews:
        events.append({
            "type": "reviewer_assigned",
            "timestamp": review.created_at,
            "actor": None,
            "version": None,
            "trigger": None,
            "diff": None,
            "review_id": review.id,
            "reviewer": review.reviewer,
            "assigned_by": review.assigned_by,
            "verdict": None,
            "comment": None,
            "answer_version": review.answer_version,
            "is_stale": None,
            "self_assigned": review.assigned_by_id is None,
        })

    # Review submitted events (non-pending, non-superseded reviews at updated_at)
    for review in reviews:
        if review.verdict in (ReviewVerdict.PENDING.value, ReviewVerdict.SUPERSEDED.value):
            continue
        events.append({
            "type": "review_submitted",
            "timestamp": review.updated_at,
            "actor": None,
            "version": None,
            "trigger": None,
            "diff": None,
            "review_id": review.id,
            "reviewer": review.reviewer,
            "assigned_by": None,
            "verdict": review.verdict,
            "comment": review.comment,
            "answer_version": review.answer_version,
            "is_stale": (review.answer_version or 0) < answer.current_version,
            "self_assigned": None,
        })

    # Sort by timestamp ascending; tiebreak by logical order:
    # version_submitted < reviewer_assigned < review_submitted
    _type_order = {"version_submitted": 0, "reviewer_assigned": 1, "review_submitted": 2}
    events.sort(key=lambda e: (e["timestamp"], _type_order.get(e["type"], 9), e.get("version") or 0))

    return {
        "events": events,
        "current_version": answer.current_version,
        "answer_status": answer.status,
    }
