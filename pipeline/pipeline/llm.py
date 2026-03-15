"""LLM wrapper adapted from worker/worker/llm.py — accepts explicit params instead of settings singleton."""

import asyncio
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import TypeVar

import litellm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class UsageStats:
    """Thread-safe accumulator for LLM token usage across a pipeline run."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    failed_calls: int = 0
    cost_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cost_usd += cost
            self.calls += 1

    def record_failure(self) -> None:
        with self._lock:
            self.failed_calls += 1

    def reset(self) -> None:
        """Reset all counters to zero."""
        with self._lock:
            self.input_tokens = 0
            self.output_tokens = 0
            self.calls = 0
            self.failed_calls = 0
            self.cost_usd = 0.0

    def summary(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "cost_usd": round(self.cost_usd, 6),
        }


# Global usage tracker — reset per pipeline run
usage = UsageStats()


def _clean_json_text(text: str) -> str:
    """Apply common fixes to LLM JSON output."""
    # Replace smart/curly quotes with escaped straight quotes
    text = text.replace("\u201c", '\\"').replace("\u201d", '\\"')  # " "
    text = text.replace("\u2018", "\\'").replace("\u2019", "\\'")  # ' '
    # Replace control characters
    text = re.sub(r'[\x00-\x1f]', lambda m: f'\\u{ord(m.group()):04x}', text)
    return text


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling code fences, smart quotes, and preamble."""
    text = text.strip()
    # Strip markdown code fences
    if "```" in text:
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # Try parsing as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try with common fixes
    try:
        return json.loads(_clean_json_text(text))
    except json.JSONDecodeError:
        pass
    # Extract outermost { } block (handles preamble text, BOM, etc.)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        subset = text[start:end + 1]
        try:
            return json.loads(subset)
        except json.JSONDecodeError:
            pass
        return json.loads(_clean_json_text(subset))
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
    content = ""
    for attempt in range(max_retries):
        try:
            response = await litellm.acompletion(
                model=model,
                messages=enriched_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content

            # Record token usage and cost from litellm
            resp_usage = getattr(response, "usage", None)
            try:
                call_cost = litellm.completion_cost(completion_response=response)
            except Exception:
                call_cost = 0.0
            if resp_usage:
                usage.record(
                    input_tokens=getattr(resp_usage, "prompt_tokens", 0),
                    output_tokens=getattr(resp_usage, "completion_tokens", 0),
                    cost=call_cost,
                )

            parsed = _extract_json(content)
            return response_model.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2**attempt
                raw_preview = content[:200] if content else "(no content)"
                logger.warning(
                    f"LLM call attempt {attempt + 1} failed: {e}. "
                    f"Response preview: {raw_preview!r}. Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
            else:
                raw_preview = content[:500] if content else "(no content)"
                logger.error(
                    f"LLM call failed after {max_retries} attempts: {e}. "
                    f"Last response preview: {raw_preview!r}"
                )

    usage.record_failure()
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")
