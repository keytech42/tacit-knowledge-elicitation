"""Dedup strategy protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline.models import GeneratedQuestion


@runtime_checkable
class DedupStrategy(Protocol):
    """Protocol for question deduplication strategies."""

    async def dedup(self, questions: list[GeneratedQuestion]) -> list[GeneratedQuestion]:
        """Remove duplicate questions, returning the deduplicated list."""
        ...
