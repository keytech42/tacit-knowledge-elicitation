"""Ingest runner — dispatches to source adapters based on config."""

from __future__ import annotations

import logging

from pipeline.config import ExperimentConfig, SourceConfig
from pipeline.models import ParsedDocument
from pipeline.registry import get_strategy

logger = logging.getLogger(__name__)


def run_ingest(config: ExperimentConfig) -> list[ParsedDocument]:
    """Ingest all configured sources and return parsed, chunked documents."""
    # Import adapters to trigger registration
    import pipeline.ingest.slack  # noqa: F401
    import pipeline.ingest.notion  # noqa: F401
    import pipeline.ingest.pdf  # noqa: F401
    import pipeline.ingest.text  # noqa: F401

    from pipeline.chunking.runner import apply_chunking

    documents: list[ParsedDocument] = []
    for source in config.sources:
        logger.info(f"Ingesting source: {source.type} from {source.path}")
        adapter = get_strategy("ingest", source.type)
        docs = adapter.ingest(source)
        documents.extend(docs)

    logger.info(f"Ingested {len(documents)} documents, applying chunking...")
    documents = apply_chunking(documents, config.chunking)
    logger.info(f"Chunked into {sum(len(d.chunks) for d in documents)} total chunks")
    return documents
