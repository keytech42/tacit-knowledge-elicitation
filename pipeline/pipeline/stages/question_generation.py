"""Stage 4: Generate knowledge elicitation questions from contradictions."""

from __future__ import annotations

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


async def generate_questions(
    contradictions: list[Contradiction],
    norms: list[NormStatement],
    config: ExperimentConfig,
) -> list[GeneratedQuestion]:
    """Generate elicitation questions grounded in contradictions."""
    stage_config = config.question_generation

    norm_lookup = {norm.id: norm for norm in norms}
    quality_weights = _load_quality_criteria()

    template_vars = {
        "contradictions": contradictions,
        "norm_lookup": norm_lookup,
        "quality_weights": quality_weights,
    }

    result = await run_llm_stage(
        stage_config,
        QuestionGenerationResult,
        template_vars,
    )

    questions = result.questions
    if stage_config.max_items:
        questions = questions[: stage_config.max_items]

    logger.info(f"Generated {len(questions)} questions from {len(contradictions)} contradictions")
    return questions
