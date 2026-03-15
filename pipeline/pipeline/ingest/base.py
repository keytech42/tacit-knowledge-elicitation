"""Source adapter protocol — all ingest adapters implement this."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol for source ingestion adapters."""

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        """Read source files and return parsed documents (without chunks)."""
        ...
