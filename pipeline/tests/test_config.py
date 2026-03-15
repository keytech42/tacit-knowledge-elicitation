"""Tests for config loading and validation."""

from pathlib import Path

import pytest

from pipeline.config import ExperimentConfig, load_experiment_config

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"


def test_load_default_config():
    config = load_experiment_config(CONFIGS_DIR / "experiments" / "default.yaml")
    assert config.experiment_name == "default"
    assert len(config.sources) > 0
    assert config.chunking.strategy == "paragraph"
    assert config.norm_extraction.prompt_dir == "norm_extraction"
    assert config.contradiction_detection.prompt_dir == "contradiction_detection"
    assert config.question_generation.prompt_dir == "question_generation"


def test_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_experiment_config("/nonexistent/config.yaml")


def test_config_validation_minimal():
    config = ExperimentConfig(
        experiment_name="test",
        sources=[{"type": "text", "path": "./data"}],
    )
    assert config.experiment_name == "test"
    assert config.chunking.max_chars == 4000
    assert config.dedup.strategy == "exact"


def test_config_validation_full():
    config = ExperimentConfig(
        experiment_name="full-test",
        sources=[
            {"type": "slack", "path": "./slack-export", "filters": {"channels": ["general"]}},
            {"type": "pdf", "path": "./docs/policy.pdf"},
        ],
        chunking={"strategy": "sliding_window", "max_chars": 2000, "overlap": 500},
        norm_extraction={"model": "openai/gpt-4o", "temperature": 0.5, "prompt_dir": "norm_extraction"},
        dedup={"strategy": "llm", "threshold": 0.9},
    )
    assert len(config.sources) == 2
    assert config.chunking.strategy == "sliding_window"
    assert config.norm_extraction.model == "openai/gpt-4o"
    assert config.dedup.strategy == "llm"
