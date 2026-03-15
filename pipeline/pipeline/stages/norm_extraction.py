"""Stage 2: Extract organizational norm statements from parsed document chunks."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from pipeline.config import ExperimentConfig
from pipeline.models import NormStatement, ParsedDocument
from pipeline.stages.base import run_llm_stage

logger = logging.getLogger(__name__)


class NormExtractionResult(BaseModel):
    norms: list[NormStatement]


async def extract_norms(
    documents: list[ParsedDocument], config: ExperimentConfig
) -> list[NormStatement]:
    """Extract norms from all document chunks via LLM."""
    all_norms: list[NormStatement] = []
    stage_config = config.norm_extraction

    failed_chunks = 0
    for doc in documents:
        for chunk in doc.chunks:
            template_vars = {
                "source_title": doc.title,
                "source_type": doc.source_type.value,
                "source_metadata": json.dumps(doc.metadata) if doc.metadata else "",
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "chunk_text": chunk.text,
            }

            try:
                result = await run_llm_stage(
                    stage_config,
                    NormExtractionResult,
                    template_vars,
                )
            except Exception:
                failed_chunks += 1
                logger.warning(
                    f"Failed to extract norms from {doc.title} chunk {chunk.chunk_index}/{chunk.total_chunks}, skipping"
                )
                continue

            for norm in result.norms:
                norm.source_document = doc.title
                all_norms.append(norm)

            if stage_config.max_items and len(all_norms) >= stage_config.max_items:
                break

        if stage_config.max_items and len(all_norms) >= stage_config.max_items:
            break

    if failed_chunks:
        logger.warning(f"Skipped {failed_chunks} chunks due to LLM failures")

    if stage_config.max_items:
        all_norms = all_norms[: stage_config.max_items]

    logger.info(f"Extracted {len(all_norms)} norms from {len(documents)} documents")
    return all_norms
