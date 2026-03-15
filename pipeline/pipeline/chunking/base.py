"""Chunker protocol and registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline.models import ParsedChunk


@runtime_checkable
class Chunker(Protocol):
    """Protocol for text chunking strategies."""

    def chunk(self, text: str) -> list[ParsedChunk]:
        """Split text into chunks."""
        ...
