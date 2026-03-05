import logging
import uuid

from worker.llm import call_llm
from worker.platform_client import platform
from worker.prompts.answer_scaffold import SYSTEM_PROMPT, build_user_prompt
from worker.schemas import ScaffoldedOptionSet

logger = logging.getLogger(__name__)


async def run_answer_scaffolding(
    question_id: uuid.UUID,
    num_options: int = 4,
) -> dict:
    """Generate answer option scaffolding for a question via LLM."""
    question = await platform.get_question(question_id)
    existing_options = await platform.get_answer_options(question_id)

    user_prompt = build_user_prompt(
        question=question,
        num_options=num_options,
        existing_options=existing_options,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await call_llm(messages, ScaffoldedOptionSet)
    logger.info(f"LLM generated {len(result.options)} answer options")

    options = [
        {"body": opt.body, "display_order": opt.display_order}
        for opt in result.options
    ]
    created = await platform.create_answer_options(question_id, options)
    logger.info(f"Created {len(created)} answer options for question {question_id}")

    return {"question_id": str(question_id), "options_created": len(created)}
