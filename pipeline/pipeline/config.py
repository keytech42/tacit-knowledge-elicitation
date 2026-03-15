"""Experiment configuration — single YAML per experiment, Pydantic-validated."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class SourceConfig(BaseModel):
    type: str  # slack, notion, pdf, text
    path: str  # directory or file path
    filters: dict = Field(default_factory=dict)  # e.g. channels, date_range


class ChunkingConfig(BaseModel):
    strategy: str = "paragraph"
    max_chars: int = 4000
    overlap: int = 200  # for sliding_window


class LLMStageConfig(BaseModel):
    model: str = "anthropic/claude-sonnet-4-6"
    temperature: float = 0.3
    max_retries: int = 3
    prompt_dir: str = ""  # relative to configs/prompts/
    batch_size: int = 20  # for contradiction detection pairwise batching
    max_items: int = 0  # 0 = unlimited


class DedupConfig(BaseModel):
    strategy: str = "exact"
    threshold: float = 0.85


class OutputConfig(BaseModel):
    base_dir: str = "runs"
    export_formats: list[str] = Field(default_factory=lambda: ["platform_json", "summary_report"])


class ExperimentConfig(BaseModel):
    experiment_name: str
    sources: list[SourceConfig]
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    norm_extraction: LLMStageConfig = Field(
        default_factory=lambda: LLMStageConfig(prompt_dir="norm_extraction")
    )
    contradiction_detection: LLMStageConfig = Field(
        default_factory=lambda: LLMStageConfig(
            prompt_dir="contradiction_detection", temperature=0.2
        )
    )
    question_generation: LLMStageConfig = Field(
        default_factory=lambda: LLMStageConfig(prompt_dir="question_generation")
    )
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class PipelineSettings(BaseSettings):
    """API keys and runtime settings from environment."""

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


def load_experiment_config(config_path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment config from YAML."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ExperimentConfig.model_validate(raw)
