"""Dedup runner — applies configured dedup strategy to questions."""

from __future__ import annotations

import logging

from pipeline.config import ExperimentConfig
from pipeline.models import GeneratedQuestion
from pipeline.registry import get_strategy

logger = logging.getLogger(__name__)


async def run_dedup(questions: list[GeneratedQuestion], config: ExperimentConfig) -> list[GeneratedQuestion]:
    """Apply the configured dedup strategy to generated questions."""
    # Import strategies to trigger registration
    import pipeline.dedup.exact  # noqa: F401
    import pipeline.dedup.llm_dedup  # noqa: F401

    dedup = get_strategy("dedup", config.dedup.strategy, threshold=config.dedup.threshold)
    before = len(questions)
    questions = await dedup.dedup(questions)
    removed = before - len(questions)
    if removed:
        logger.info(f"Dedup removed {removed} duplicate questions ({before} → {len(questions)})")
    return questions
