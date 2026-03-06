import logging
import uuid

from worker.llm import call_llm
from worker.platform_client import platform
from worker.prompts.answer_scaffold import SYSTEM_PROMPT, build_user_prompt
from worker.schemas import ScaffoldedOptionSet

logger = logging.getLogger(__name__)


MAX_OPTIONS = 4


async def run_answer_scaffolding(
    question_id: uuid.UUID,
    num_options: int = 4,
) -> dict:
    """Generate answer option scaffolding for a question via LLM.

    Replaces any existing options with a fresh set (max 4).
    """
    num_options = min(num_options, MAX_OPTIONS)
    question = await platform.get_question(question_id)

    user_prompt = build_user_prompt(
        question=question,
        num_options=num_options,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await call_llm(messages, ScaffoldedOptionSet)
    # Enforce cap even if LLM returns more
    capped = result.options[:MAX_OPTIONS]
    logger.info(f"LLM generated {len(result.options)} options, using {len(capped)}")

    options = [
        {"body": opt.body, "display_order": i + 1}
        for i, opt in enumerate(capped)
    ]

    # Replace existing options with fresh set
    await platform.delete_answer_options(question_id)
    created = await platform.create_answer_options(question_id, options)
    logger.info(f"Created {len(created)} answer options for question {question_id}")

    # Enable show_suggestions so options are visible to respondents
    await platform.update_question(question_id, {"show_suggestions": True})

    return {"question_id": str(question_id), "options_created": len(created)}
