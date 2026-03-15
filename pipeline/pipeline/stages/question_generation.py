"""Stage 4: Generate knowledge elicitation questions from contradictions."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

from pipeline.config import ExperimentConfig
from pipeline.models import Contradiction, GeneratedQuestion, NormStatement
from pipeline.stages.base import run_llm_stage

logger = logging.getLogger(__name__)

# quality_criteria.yaml lives at configs/ root (sibling to prompts/)
_CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs"


class QuestionGenerationResult(BaseModel):
    questions: list[GeneratedQuestion]


def _load_quality_criteria(configs_dir: Path | None = None) -> str:
    """Load quality_criteria.yaml and format as readable string."""
    base = configs_dir or _CONFIGS_DIR
    path = base / "quality_criteria.yaml"
    if not path.exists():
        return ""
    with open(path) as f:
        data = yaml.safe_load(f)
    lines: list[str] = []
    if "weights" in data:
        lines.append("Scoring weights:")
        for k, v in data["weights"].items():
            lines.append(f"  - {k}: {v}")
    if "thresholds" in data:
        lines.append("Thresholds:")
        for k, v in data["thresholds"].items():
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


async def _generate_batch(
    batch: list[Contradiction],
    norm_lookup: dict[str, NormStatement],
    quality_weights: str,
    stage_config,
    semaphore: asyncio.Semaphore,
) -> list[GeneratedQuestion]:
    """Generate questions from a single batch of contradictions."""
    # Build minimal norm_lookup for this batch
    batch_norm_ids = set()
    for c in batch:
        batch_norm_ids.add(c.norm_a_id)
        batch_norm_ids.add(c.norm_b_id)
    batch_norm_lookup = {nid: norm_lookup[nid] for nid in batch_norm_ids if nid in norm_lookup}

    template_vars = {
        "contradictions": batch,
        "norm_lookup": batch_norm_lookup,
        "quality_weights": quality_weights,
    }

    async with semaphore:
        try:
            result = await run_llm_stage(
                stage_config,
                QuestionGenerationResult,
                template_vars,
            )
        except Exception:
            logger.warning("Failed to generate questions from contradiction batch, skipping")
            return []

    return result.questions


async def generate_questions(
    contradictions: list[Contradiction],
    norms: list[NormStatement],
    config: ExperimentConfig,
) -> list[GeneratedQuestion]:
    """Generate elicitation questions grounded in contradictions (concurrent).

    Batches contradictions to avoid exceeding context limits.
    Prioritizes high-severity contradictions first.
    """
    stage_config = config.question_generation
    semaphore = asyncio.Semaphore(stage_config.concurrency)

    norm_lookup = {norm.id: norm for norm in norms}
    quality_weights = _load_quality_criteria()

    # Sort by severity (high first)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_contradictions = sorted(
        contradictions,
        key=lambda c: (severity_order.get(c.severity.value, 9), -c.confidence),
    )

    # Build batch tasks
    batch_size = stage_config.batch_size
    tasks = []
    for i in range(0, len(sorted_contradictions), batch_size):
        batch = sorted_contradictions[i : i + batch_size]
        tasks.append(_generate_batch(batch, norm_lookup, quality_weights, stage_config, semaphore))

    # Run concurrently
    results = await asyncio.gather(*tasks)

    all_questions: list[GeneratedQuestion] = []
    for questions in results:
        all_questions.extend(questions)

    if stage_config.max_items:
        all_questions = all_questions[: stage_config.max_items]

    logger.info(f"Generated {len(all_questions)} questions from {len(contradictions)} contradictions")
    return all_questions
