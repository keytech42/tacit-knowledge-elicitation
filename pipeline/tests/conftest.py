"""Shared test fixtures for the pipeline test suite."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from pipeline.config import ExperimentConfig, load_experiment_config
from pipeline.models import (
    Contradiction,
    GeneratedQuestion,
    NormStatement,
    NormType,
    ParsedChunk,
    ParsedDocument,
    Severity,
    SourceType,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIGS_DIR = REPO_ROOT / "configs"


@pytest.fixture
def default_config() -> ExperimentConfig:
    """Load the default experiment config."""
    return load_experiment_config(CONFIGS_DIR / "experiments" / "default.yaml")


@pytest.fixture
def sample_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="/test/doc.md",
        source_type=SourceType.text,
        title="Test Document",
        raw_text="Paragraph one about flat hierarchy.\n\nParagraph two about CEO decisions.\n\nParagraph three about team autonomy.",
        chunks=[
            ParsedChunk(text="Paragraph one about flat hierarchy.", chunk_index=0, total_chunks=3),
            ParsedChunk(text="Paragraph two about CEO decisions.", chunk_index=1, total_chunks=3),
            ParsedChunk(text="Paragraph three about team autonomy.", chunk_index=2, total_chunks=3),
        ],
        content_hash="abc123",
    )


@pytest.fixture
def sample_norms() -> list[NormStatement]:
    return [
        NormStatement(
            id="norm-1",
            text="The organization operates with a flat hierarchy where no single person has authority over others.",
            norm_type=NormType.stated,
            source_document="Lean HR Policy",
            source_passage="We believe in a flat organizational structure.",
            confidence=0.9,
        ),
        NormStatement(
            id="norm-2",
            text="The CEO makes final decisions on all major hiring and budget matters.",
            norm_type=NormType.practiced,
            source_document="Slack #general",
            source_passage="@ceo approved the new hire budget for Q2",
            confidence=0.85,
        ),
    ]


@pytest.fixture
def sample_contradictions(sample_norms: list[NormStatement]) -> list[Contradiction]:
    return [
        Contradiction(
            id="contra-1",
            norm_a_id="norm-1",
            norm_b_id="norm-2",
            tension_description="Documentation states flat hierarchy with no authority figures, but in practice the CEO makes unilateral decisions on hiring and budget.",
            severity=Severity.high,
            confidence=0.9,
        ),
    ]


@pytest.fixture
def sample_questions() -> list[GeneratedQuestion]:
    return [
        GeneratedQuestion(
            title="How are major hiring decisions actually made?",
            body="Our HR policy states a flat hierarchy, but Slack messages show the CEO approving all major hires. How does hiring actually work in practice?",
            category="Authority",
            evidence=["Lean HR Policy: flat structure", "Slack: CEO approved Q2 budget"],
            source_passages=["We believe in a flat organizational structure.", "@ceo approved the new hire budget for Q2"],
            suggested_options=["CEO decides", "Team consensus", "Department lead recommends, CEO approves"],
            confidence=0.85,
        ),
    ]


@pytest.fixture
def mock_call_llm():
    """Return a mock for pipeline.llm.call_llm that can be configured per test."""
    return AsyncMock()
