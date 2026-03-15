"""Stage 3: Detect contradictions and tensions between norm statements."""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from pipeline.config import ExperimentConfig
from pipeline.models import Contradiction, NormStatement
from pipeline.stages.base import run_llm_stage

logger = logging.getLogger(__name__)


class ContradictionDetectionResult(BaseModel):
    contradictions: list[Contradiction]


async def _detect_batch(
    batch: list[NormStatement],
    batch_context: str,
    stage_config,
    semaphore: asyncio.Semaphore,
) -> list[Contradiction]:
    """Detect contradictions in a single batch, with concurrency limiting."""
    template_vars = {
        "norms": batch,
        "batch_context": batch_context,
    }

    async with semaphore:
        try:
            result = await run_llm_stage(
                stage_config,
                ContradictionDetectionResult,
                template_vars,
            )
        except Exception:
            logger.warning(f"Failed contradiction detection batch, skipping")
            return []

    return result.contradictions


async def detect_contradictions(
    norms: list[NormStatement], config: ExperimentConfig
) -> list[Contradiction]:
    """Detect contradictions between norms by processing in batches (concurrent)."""
    stage_config = config.contradiction_detection
    batch_size = stage_config.batch_size
    semaphore = asyncio.Semaphore(stage_config.concurrency)

    # Build all batch tasks
    tasks = []
    for i in range(0, len(norms), batch_size):
        batch = norms[i : i + batch_size]
        batch_context = (
            f"Batch {i // batch_size + 1}: norms {i + 1}-{i + len(batch)} of {len(norms)} total."
            if len(norms) > batch_size
            else ""
        )
        tasks.append(_detect_batch(batch, batch_context, stage_config, semaphore))

    # Run concurrently
    results = await asyncio.gather(*tasks)

    all_contradictions: list[Contradiction] = []
    for contradictions in results:
        all_contradictions.extend(contradictions)

    logger.info(f"Detected {len(all_contradictions)} contradictions from {len(norms)} norms")
    return all_contradictions
