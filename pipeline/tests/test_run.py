"""Integration tests for the full pipeline runner."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.config import ExperimentConfig
from pipeline.models import (
    Contradiction,
    GeneratedQuestion,
    NormStatement,
    NormType,
    Severity,
)
from pipeline.run import create_run_dir, run_pipeline, save_jsonl
from pipeline.stages.contradiction_detection import ContradictionDetectionResult
from pipeline.stages.norm_extraction import NormExtractionResult
from pipeline.stages.question_generation import QuestionGenerationResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def integration_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="integration-test",
        sources=[
            {"type": "text", "path": str(FIXTURES_DIR / "text_files")},
            {"type": "slack", "path": str(FIXTURES_DIR / "slack_export")},
            {"type": "notion", "path": str(FIXTURES_DIR / "notion_export")},
        ],
        chunking={"strategy": "paragraph", "max_chars": 500},
        output={"base_dir": str(tmp_path)},
    )


@pytest.fixture
def mock_llm_responses():
    norm_result = NormExtractionResult(norms=[
        NormStatement(id="n1", text="Flat hierarchy", norm_type=NormType.stated, confidence=0.9),
        NormStatement(id="n2", text="CEO decides", norm_type=NormType.practiced, confidence=0.8),
    ])
    contra_result = ContradictionDetectionResult(contradictions=[
        Contradiction(
            id="c1", norm_a_id="n1", norm_b_id="n2",
            tension_description="Stated flat vs practiced hierarchy",
            severity=Severity.high, confidence=0.85,
        ),
    ])
    question_result = QuestionGenerationResult(questions=[
        GeneratedQuestion(
            title="How are decisions made?", body="Context here", category="Authority",
            confidence=0.9, evidence=["Doc A"], source_passages=["passage"],
            suggested_options=["Option 1", "Option 2"],
        ),
    ])

    async def mock_stage(stage_config, response_model, template_vars, **kwargs):
        name = response_model.__name__
        if "Norm" in name:
            return norm_result
        if "Contradiction" in name:
            return contra_result
        if "Question" in name:
            return question_result
        raise ValueError(f"Unexpected model: {name}")

    return mock_stage


def test_create_run_dir(tmp_path: Path, default_config: ExperimentConfig):
    run_dir = create_run_dir(default_config, base_dir=tmp_path)
    assert run_dir.exists()
    assert (run_dir / "config_snapshot.yaml").exists()
    assert (run_dir / "export").is_dir()
    assert "default" in run_dir.name


def test_save_jsonl(tmp_path: Path, sample_norms):
    path = tmp_path / "norms.jsonl"
    save_jsonl(sample_norms, path)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == len(sample_norms)
    for line in lines:
        parsed = json.loads(line)
        assert "text" in parsed


@pytest.mark.asyncio
async def test_dry_run(tmp_path: Path, default_config: ExperimentConfig):
    default_config.output.base_dir = str(tmp_path)
    run_dir = await run_pipeline(default_config, "test-config.yaml", dry_run=True)
    assert run_dir.exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert all(s["status"] == "skipped" for s in manifest["stages"])


@pytest.mark.asyncio
async def test_full_pipeline_integration(integration_config, mock_llm_responses):
    with patch("pipeline.stages.norm_extraction.run_llm_stage", side_effect=mock_llm_responses), \
         patch("pipeline.stages.contradiction_detection.run_llm_stage", side_effect=mock_llm_responses), \
         patch("pipeline.stages.question_generation.run_llm_stage", side_effect=mock_llm_responses):
        run_dir = await run_pipeline(integration_config, "integration-test")

    # All stage outputs exist
    assert (run_dir / "config_snapshot.yaml").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "stage_1_documents.jsonl").exists()
    assert (run_dir / "stage_2_norms.jsonl").exists()
    assert (run_dir / "stage_3_contradictions.jsonl").exists()
    assert (run_dir / "stage_4_questions.jsonl").exists()
    assert (run_dir / "export" / "platform_import.json").exists()
    assert (run_dir / "export" / "report.md").exists()

    # Manifest is well-formed
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["experiment_name"] == "integration-test"
    assert all(s["status"] == "completed" for s in manifest["stages"])
    assert manifest["totals"]["documents"] > 0
    assert manifest["totals"]["norms"] > 0
    assert manifest["totals"]["contradictions"] > 0
    assert manifest["totals"]["questions"] > 0

    # Platform export is valid JSON array
    export = json.loads((run_dir / "export" / "platform_import.json").read_text())
    assert isinstance(export, list)
    assert len(export) > 0
    assert "title" in export[0]

    # Report is non-empty markdown
    report = (run_dir / "export" / "report.md").read_text()
    assert "# Pipeline Run Report" in report or "Run Summary" in report

    # Usage tracking is present in manifest
    assert "usage" in manifest["totals"]
    usage = manifest["totals"]["usage"]
    assert "calls" in usage
    assert "input_tokens" in usage
    assert "output_tokens" in usage
    assert "cost_usd" in usage


@pytest.mark.asyncio
async def test_config_snapshot_matches_input(integration_config, mock_llm_responses):
    with patch("pipeline.stages.norm_extraction.run_llm_stage", side_effect=mock_llm_responses), \
         patch("pipeline.stages.contradiction_detection.run_llm_stage", side_effect=mock_llm_responses), \
         patch("pipeline.stages.question_generation.run_llm_stage", side_effect=mock_llm_responses):
        run_dir = await run_pipeline(integration_config, "integration-test")

    import yaml
    snapshot = yaml.safe_load((run_dir / "config_snapshot.yaml").read_text())
    assert snapshot["experiment_name"] == "integration-test"
    assert snapshot["chunking"]["strategy"] == "paragraph"
    assert snapshot["chunking"]["max_chars"] == 500
