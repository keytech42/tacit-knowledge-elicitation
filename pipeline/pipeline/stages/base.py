"""Shared run_llm_stage() function and Jinja2 template loader for all LLM stages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeVar

import jinja2
from pydantic import BaseModel

from pipeline.config import LLMStageConfig
from pipeline.llm import call_llm

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Default configs/ directory is sibling to pipeline/ package at repo root
_DEFAULT_CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs"


def load_prompt(prompt_dir: str, template_name: str, configs_dir: Path | None = None, **kwargs: object) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        prompt_dir: Subdirectory under configs/prompts/ (e.g. "norm_extraction").
        template_name: Template filename (e.g. "user.md.jinja").
        configs_dir: Override configs/ root (for testing).
        **kwargs: Template variables.
    """
    base = configs_dir or _DEFAULT_CONFIGS_DIR
    prompts_path = base / "prompts" / prompt_dir
    if not prompts_path.exists():
        raise FileNotFoundError(f"Prompt directory not found: {prompts_path}")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(prompts_path)),
        undefined=jinja2.StrictUndefined,
    )
    template = env.get_template(template_name)
    return template.render(**kwargs)


def load_system_prompt(prompt_dir: str, configs_dir: Path | None = None) -> str:
    """Load a plain markdown system prompt (not a Jinja2 template)."""
    base = configs_dir or _DEFAULT_CONFIGS_DIR
    system_path = base / "prompts" / prompt_dir / "system.md"
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    return system_path.read_text()


async def run_llm_stage(
    stage_config: LLMStageConfig,
    response_model: type[T],
    template_vars: dict,
    configs_dir: Path | None = None,
) -> T:
    """Generic LLM stage runner.

    Loads system.md + renders user.md.jinja from the stage's prompt_dir,
    then calls the LLM with structured output.
    """
    system_prompt = load_system_prompt(stage_config.prompt_dir, configs_dir=configs_dir)
    user_prompt = load_prompt(
        stage_config.prompt_dir,
        "user.md.jinja",
        configs_dir=configs_dir,
        **template_vars,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    return await call_llm(
        messages,
        response_model,
        model=stage_config.model,
        temperature=stage_config.temperature,
        max_retries=stage_config.max_retries,
    )
