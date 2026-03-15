"""Exact-match deduplication — normalize titles and remove duplicates."""

from __future__ import annotations

import re

from pipeline.models import GeneratedQuestion
from pipeline.registry import register


def _normalize(title: str) -> str:
    """Lowercase, strip whitespace and common punctuation for comparison."""
    text = title.lower().strip()
    text = re.sub(r"[?!.,;:\-\"'()]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@register("dedup", "exact")
class ExactDedup:
    def __init__(self, threshold: float = 0.85, **kwargs):
        pass  # threshold unused for exact match

    async def dedup(self, questions: list[GeneratedQuestion]) -> list[GeneratedQuestion]:
        seen: set[str] = set()
        result: list[GeneratedQuestion] = []
        for q in questions:
            key = _normalize(q.title)
            if key not in seen:
                seen.add(key)
                result.append(q)
        return result
