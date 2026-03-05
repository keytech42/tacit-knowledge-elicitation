import asyncio
import json
import logging
from typing import TypeVar

import litellm
from pydantic import BaseModel

from worker.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def call_llm(
    messages: list[dict],
    response_model: type[T],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_retries: int | None = None,
) -> T:
    """Call LLM with structured output via litellm.

    Uses response_format with a JSON schema derived from the Pydantic model.
    Retries with exponential backoff on transient failures.
    """
    model = model or settings.LLM_MODEL
    temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
    max_retries = max_retries if max_retries is not None else settings.MAX_RETRIES

    schema = response_model.model_json_schema()

    # Append instruction to return JSON matching the schema
    system_suffix = (
        f"\n\nYou MUST respond with valid JSON matching this schema:\n"
        f"```json\n{json.dumps(schema, indent=2)}\n```\n"
        f"Return ONLY the JSON object, no other text."
    )
    enriched_messages = []
    for msg in messages:
        if msg["role"] == "system":
            enriched_messages.append({**msg, "content": msg["content"] + system_suffix})
            system_suffix = ""  # Only add once
        else:
            enriched_messages.append(msg)

    # If no system message was present, add one
    if system_suffix:
        enriched_messages.insert(0, {"role": "system", "content": system_suffix.strip()})

    last_error = None
    for attempt in range(max_retries):
        try:
            response = await litellm.acompletion(
                model=model,
                messages=enriched_messages,
                temperature=temperature,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            # Parse JSON from response, handling potential markdown code blocks
            text = content.strip()
            if text.startswith("```"):
                # Remove markdown code fences
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines)
            parsed = json.loads(text)
            return response_model.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM call failed after {max_retries} attempts: {e}")

    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")
