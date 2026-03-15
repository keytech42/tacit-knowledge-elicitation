"""Stage 3: Detect contradictions and tensions between norm statements."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from pipeline.config import ExperimentConfig
from pipeline.models import Contradiction, NormStatement
from pipeline.stages.base import run_llm_stage

logger = logging.getLogger(__name__)


class ContradictionDetectionResult(BaseModel):
    contradictions: list[Contradiction]


async def detect_contradictions(
    norms: list[NormStatement], config: ExperimentConfig
) -> list[Contradiction]:
    """Detect contradictions between norms by processing in batches."""
    all_contradictions: list[Contradiction] = []
    stage_config = config.contradiction_detection
    batch_size = stage_config.batch_size

    for i in range(0, len(norms), batch_size):
        batch = norms[i : i + batch_size]
        batch_context = (
            f"Batch {i // batch_size + 1}: norms {i + 1}-{i + len(batch)} of {len(norms)} total."
            if len(norms) > batch_size
            else ""
        )

        template_vars = {
            "norms": batch,
            "batch_context": batch_context,
        }

        result = await run_llm_stage(
            stage_config,
            ContradictionDetectionResult,
            template_vars,
        )

        all_contradictions.extend(result.contradictions)

    logger.info(f"Detected {len(all_contradictions)} contradictions from {len(norms)} norms")
    return all_contradictions
