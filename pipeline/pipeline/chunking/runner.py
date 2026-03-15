"""Chunking runner — applies configured chunking strategy to documents."""

from __future__ import annotations

import logging

from pipeline.config import ChunkingConfig
from pipeline.models import ParsedDocument
from pipeline.registry import get_strategy

logger = logging.getLogger(__name__)


def apply_chunking(documents: list[ParsedDocument], config: ChunkingConfig) -> list[ParsedDocument]:
    """Apply the configured chunking strategy to all documents."""
    # Import strategies to trigger registration
    import pipeline.chunking.paragraph  # noqa: F401
    import pipeline.chunking.sliding_window  # noqa: F401

    chunker = get_strategy("chunking", config.strategy, max_chars=config.max_chars, overlap=config.overlap)
    for doc in documents:
        if not doc.chunks:
            doc.chunks = chunker.chunk(doc.raw_text)
    return documents
