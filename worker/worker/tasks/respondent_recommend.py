"""LLM-based respondent recommendation — matches questions to suitable respondents."""

import logging

from worker.config import settings
from worker.llm import call_llm
from worker.prompts.respondent_recommend import SYSTEM_PROMPT, build_user_prompt
from worker.schemas import RecommendationResult

logger = logging.getLogger(__name__)


async def run_respondent_recommendation(
    question: dict,
    candidates: list[dict],
    top_k: int = 5,
) -> dict:
    """Recommend respondents for a question using LLM reasoning.

    The backend gathers candidate context from the DB and passes it here.
    This task only handles the LLM reasoning step.
    """
    if not candidates:
        return {"items": [], "reason": "No candidates provided."}

    user_prompt = build_user_prompt(
        question=question,
        candidates=candidates,
        top_k=top_k,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    model = settings.RECOMMENDATION_MODEL or settings.LLM_MODEL
    result = await call_llm(messages, RecommendationResult, model=model, temperature=0.3)

    # Map LLM results back to full candidate info
    candidate_lookup = {c["user_id"]: c for c in candidates}
    items = []
    for rec in result.respondents[:top_k]:
        candidate = candidate_lookup.get(rec.user_id)
        if candidate:
            items.append({
                "user_id": rec.user_id,
                "display_name": candidate["display_name"],
                "score": round(rec.score, 3),
                "reasoning": rec.reasoning,
            })

    return {"items": items, "reason": None}
