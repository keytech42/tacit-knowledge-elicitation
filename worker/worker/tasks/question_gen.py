import logging
import uuid

from worker.llm import call_llm
from worker.platform_client import platform
from worker.prompts.question_gen import SYSTEM_PROMPT, build_user_prompt
from worker.schemas import GeneratedQuestionSet

logger = logging.getLogger(__name__)


async def run_question_generation(
    topic: str,
    domain: str = "",
    count: int = 3,
    context: str | None = None,
) -> dict:
    """Generate elicitation questions via LLM and create them on the platform."""
    # Gather context from the platform
    existing_categories = await platform.get_categories()
    existing_questions = await platform.get_questions()

    user_prompt = build_user_prompt(
        topic=topic,
        domain=domain,
        count=count,
        existing_categories=existing_categories,
        existing_questions=existing_questions,
        context=context,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await call_llm(messages, GeneratedQuestionSet)
    logger.info(f"LLM generated {len(result.questions)} questions")

    created_ids: list[str] = []
    for gq in result.questions:
        try:
            question = await platform.create_question(
                title=gq.title,
                body=gq.body,
                category=gq.category,
            )
            question_id = question["id"]
            created_ids.append(question_id)

            # Submit the question (draft -> proposed)
            await platform.submit_question(uuid.UUID(question_id))

            # Create suggested answer options if any
            if gq.suggested_options:
                options = [
                    {"body": opt, "display_order": i}
                    for i, opt in enumerate(gq.suggested_options)
                ]
                await platform.create_answer_options(uuid.UUID(question_id), options)

            logger.info(f"Created and submitted question: {gq.title}")
        except Exception:
            logger.exception(f"Failed to create question: {gq.title}")

    return {"created_question_ids": created_ids, "count": len(created_ids)}
