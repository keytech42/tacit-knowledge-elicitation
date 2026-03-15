"""Stage 2: Extract organizational norm statements from parsed document chunks."""

from __future__ import annotations

import asyncio
import json
import logging

from pydantic import BaseModel

from pipeline.config import ExperimentConfig
from pipeline.models import NormStatement, ParsedDocument
from pipeline.stages.base import run_llm_stage

logger = logging.getLogger(__name__)


class NormExtractionResult(BaseModel):
    norms: list[NormStatement]


async def _extract_from_chunk(
    doc: ParsedDocument,
    chunk_index: int,
    stage_config,
    semaphore: asyncio.Semaphore,
) -> list[NormStatement]:
    """Extract norms from a single chunk, with concurrency limiting."""
    chunk = doc.chunks[chunk_index]
    template_vars = {
        "source_title": doc.title,
        "source_type": doc.source_type.value,
        "source_metadata": json.dumps(doc.metadata) if doc.metadata else "",
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
        "chunk_text": chunk.text,
    }

    async with semaphore:
        try:
            result = await run_llm_stage(
                stage_config,
                NormExtractionResult,
                template_vars,
            )
        except Exception:
            logger.warning(
                f"Failed to extract norms from {doc.title} chunk {chunk.chunk_index}/{chunk.total_chunks}, skipping"
            )
            return []

    norms = result.norms
    for norm in norms:
        norm.source_document = doc.title
    return norms


async def extract_norms(
    documents: list[ParsedDocument], config: ExperimentConfig
) -> list[NormStatement]:
    """Extract norms from all document chunks via LLM (concurrent)."""
    stage_config = config.norm_extraction
    semaphore = asyncio.Semaphore(stage_config.concurrency)

    # Build all tasks
    tasks = []
    for doc in documents:
        for i in range(len(doc.chunks)):
            tasks.append(_extract_from_chunk(doc, i, stage_config, semaphore))

    # Run concurrently
    results = await asyncio.gather(*tasks)

    # Flatten
    all_norms: list[NormStatement] = []
    for norms in results:
        all_norms.extend(norms)

    failed = sum(1 for r in results if not r)
    if failed:
        logger.warning(f"Skipped {failed} chunks due to LLM failures")

    if stage_config.max_items:
        all_norms = all_norms[: stage_config.max_items]

    logger.info(f"Extracted {len(all_norms)} norms from {len(documents)} documents")
    return all_norms
