import logging
import uuid

from worker.config import settings
from worker.llm import call_llm
from worker.platform_client import platform
from worker.prompts.review_assist import SYSTEM_PROMPT, build_user_prompt
from worker.schemas import ReviewAssessment

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6


async def run_review_assist(answer_id: uuid.UUID) -> dict:
    """Generate an AI-assisted review for a submitted answer."""
    answer = await platform.get_answer(answer_id)
    question = await platform.get_question(uuid.UUID(answer["question_id"]))

    user_prompt = build_user_prompt(question=question, answer=answer)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    assessment = await call_llm(
        messages,
        ReviewAssessment,
        temperature=settings.LLM_REVIEW_TEMPERATURE,
    )

    logger.info(
        f"Review assessment for answer {answer_id}: "
        f"verdict={assessment.verdict}, confidence={assessment.confidence}"
    )

    result = {
        "answer_id": str(answer_id),
        "verdict": assessment.verdict,
        "confidence": assessment.confidence,
        "submitted": False,
    }

    if assessment.confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            f"Confidence {assessment.confidence} below threshold {CONFIDENCE_THRESHOLD}, "
            f"skipping review submission"
        )
        result["reason"] = "confidence below threshold"
        return result

    # Build the review comment from the assessment
    comment_parts = [assessment.comment]
    if assessment.strengths:
        comment_parts.append("\n**Strengths:**")
        comment_parts.extend(f"- {s}" for s in assessment.strengths)
    if assessment.weaknesses:
        comment_parts.append("\n**Areas for improvement:**")
        comment_parts.extend(f"- {w}" for w in assessment.weaknesses)
    if assessment.suggestions:
        comment_parts.append("\n**Suggestions:**")
        comment_parts.extend(f"- {s}" for s in assessment.suggestions)
    comment_parts.append(f"\n*AI confidence: {assessment.confidence:.0%}*")
    full_comment = "\n".join(comment_parts)

    # Create and submit the review
    review = await platform.create_review("answer", answer_id)
    review_id = uuid.UUID(review["id"])
    await platform.submit_review_verdict(review_id, assessment.verdict, full_comment)

    result["submitted"] = True
    result["review_id"] = str(review_id)
    logger.info(f"Submitted AI review {review_id} for answer {answer_id}")

    return result
