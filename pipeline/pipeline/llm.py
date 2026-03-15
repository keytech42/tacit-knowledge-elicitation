"""LLM wrapper adapted from worker/worker/llm.py — accepts explicit params instead of settings singleton."""

import asyncio
import json
import logging
import re
from typing import TypeVar

import litellm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling code fences and control chars."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)
    # Try parsing as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fix common issues: unescaped control characters in string values
    # Replace literal tabs/newlines inside JSON strings
    cleaned = re.sub(r'[\x00-\x1f]', lambda m: f'\\u{ord(m.group()):04x}', text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Last resort: find the outermost { } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        subset = text[start:end + 1]
        cleaned = re.sub(r'[\x00-\x1f]', lambda m: f'\\u{ord(m.group()):04x}', subset)
        return json.loads(cleaned)
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


async def call_llm(
    messages: list[dict],
    response_model: type[T],
    *,
    model: str = "anthropic/claude-sonnet-4-6",
    temperature: float = 0.3,
    max_retries: int = 3,
    max_tokens: int = 4096,
) -> T:
    """Call LLM with structured output via litellm.

    Uses JSON schema instruction appended to system message.
    Retries with exponential backoff on transient failures.
    """
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
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            parsed = _extract_json(content)
            return response_model.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2**attempt
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM call failed after {max_retries} attempts: {e}")

    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")
