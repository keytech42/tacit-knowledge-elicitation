"""Tests for LLM pipeline stages with mocked LLM calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

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
from pipeline.stages.contradiction_detection import (
    ContradictionDetectionResult,
    detect_contradictions,
)
from pipeline.stages.norm_extraction import NormExtractionResult, extract_norms
from pipeline.stages.question_generation import (
    QuestionGenerationResult,
    generate_questions,
)


# ---------------------------------------------------------------------------
# Stage 2: Norm Extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_norms_calls_per_chunk(default_config, sample_document):
    """Should call run_llm_stage once per chunk."""
    mock_result = NormExtractionResult(
        norms=[
            NormStatement(
                text="Test norm",
                norm_type=NormType.stated,
                confidence=0.9,
                source_passage="some passage",
            )
        ]
    )
    with patch(
        "pipeline.stages.norm_extraction.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        norms = await extract_norms([sample_document], default_config)

        assert mock_stage.call_count == len(sample_document.chunks)
        assert len(norms) == len(sample_document.chunks)  # 1 norm per chunk


@pytest.mark.asyncio
async def test_extract_norms_sets_source_document(default_config, sample_document):
    """Extracted norms should have source_document set to the document title."""
    mock_result = NormExtractionResult(
        norms=[
            NormStatement(text="A norm", norm_type=NormType.practiced, confidence=0.8)
        ]
    )
    with patch(
        "pipeline.stages.norm_extraction.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        norms = await extract_norms([sample_document], default_config)

        for norm in norms:
            assert norm.source_document == sample_document.title


@pytest.mark.asyncio
async def test_extract_norms_template_vars(default_config, sample_document):
    """Should pass correct template variables to run_llm_stage."""
    mock_result = NormExtractionResult(norms=[])
    with patch(
        "pipeline.stages.norm_extraction.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await extract_norms([sample_document], default_config)

        first_call = mock_stage.call_args_list[0]
        template_vars = first_call[0][2]  # 3rd positional arg
        assert template_vars["source_title"] == sample_document.title
        assert template_vars["source_type"] == sample_document.source_type.value
        assert template_vars["chunk_index"] == 0
        assert template_vars["total_chunks"] == 3
        assert template_vars["chunk_text"] == sample_document.chunks[0].text


@pytest.mark.asyncio
async def test_extract_norms_max_items(default_config, sample_document):
    """Should respect max_items limit."""
    default_config.norm_extraction.max_items = 2

    mock_result = NormExtractionResult(
        norms=[
            NormStatement(text="Norm A", norm_type=NormType.stated, confidence=0.9),
            NormStatement(text="Norm B", norm_type=NormType.stated, confidence=0.8),
        ]
    )
    with patch(
        "pipeline.stages.norm_extraction.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        norms = await extract_norms([sample_document], default_config)

        assert len(norms) == 2


@pytest.mark.asyncio
async def test_extract_norms_empty_documents(default_config):
    """Should handle empty document list gracefully."""
    norms = await extract_norms([], default_config)
    assert norms == []


@pytest.mark.asyncio
async def test_extract_norms_no_chunks(default_config):
    """Should handle document with no chunks."""
    doc = ParsedDocument(
        source_path="/test/empty.md",
        source_type=SourceType.text,
        title="Empty",
        raw_text="",
        chunks=[],
    )
    norms = await extract_norms([doc], default_config)
    assert norms == []


# ---------------------------------------------------------------------------
# Stage 3: Contradiction Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_contradictions_single_batch(default_config, sample_norms):
    """Norms fitting in one batch should produce a single LLM call."""
    mock_result = ContradictionDetectionResult(
        contradictions=[
            Contradiction(
                norm_a_id="norm-1",
                norm_b_id="norm-2",
                tension_description="Flat hierarchy vs CEO authority",
                severity=Severity.high,
                confidence=0.9,
            )
        ]
    )
    with patch(
        "pipeline.stages.contradiction_detection.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        result = await detect_contradictions(sample_norms, default_config)

        assert mock_stage.call_count == 1
        assert len(result) == 1
        assert result[0].norm_a_id == "norm-1"


@pytest.mark.asyncio
async def test_detect_contradictions_batching(default_config, sample_norms):
    """Should split norms into batches of batch_size."""
    default_config.contradiction_detection.batch_size = 1

    mock_result = ContradictionDetectionResult(contradictions=[])
    with patch(
        "pipeline.stages.contradiction_detection.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await detect_contradictions(sample_norms, default_config)

        assert mock_stage.call_count == len(sample_norms)


@pytest.mark.asyncio
async def test_detect_contradictions_template_vars(default_config, sample_norms):
    """Should pass norms batch and batch_context as template vars."""
    mock_result = ContradictionDetectionResult(contradictions=[])
    with patch(
        "pipeline.stages.contradiction_detection.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await detect_contradictions(sample_norms, default_config)

        template_vars = mock_stage.call_args_list[0][0][2]
        assert template_vars["norms"] == sample_norms
        # Small batch — no batch_context needed
        assert template_vars["batch_context"] == ""


@pytest.mark.asyncio
async def test_detect_contradictions_batch_context_when_multiple_batches(
    default_config, sample_norms
):
    """batch_context should be non-empty when there are multiple batches."""
    default_config.contradiction_detection.batch_size = 1

    mock_result = ContradictionDetectionResult(contradictions=[])
    with patch(
        "pipeline.stages.contradiction_detection.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await detect_contradictions(sample_norms, default_config)

        for call in mock_stage.call_args_list:
            template_vars = call[0][2]
            assert template_vars["batch_context"] != ""


@pytest.mark.asyncio
async def test_detect_contradictions_empty_norms(default_config):
    """Should handle empty norms list gracefully."""
    result = await detect_contradictions([], default_config)
    assert result == []


# ---------------------------------------------------------------------------
# Stage 4: Question Generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_questions(
    default_config, sample_contradictions, sample_norms
):
    """Should generate questions from contradictions and norms."""
    mock_result = QuestionGenerationResult(
        questions=[
            GeneratedQuestion(
                title="How are hiring decisions made?",
                body="Evidence shows tension between flat hierarchy and CEO authority.",
                category="Authority",
                confidence=0.85,
            )
        ]
    )
    with patch(
        "pipeline.stages.question_generation.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        questions = await generate_questions(
            sample_contradictions, sample_norms, default_config
        )

        assert mock_stage.call_count == 1
        assert len(questions) == 1
        assert questions[0].title == "How are hiring decisions made?"


@pytest.mark.asyncio
async def test_generate_questions_norm_lookup(
    default_config, sample_contradictions, sample_norms
):
    """Should build norm_lookup dict and pass to template."""
    mock_result = QuestionGenerationResult(questions=[])
    with patch(
        "pipeline.stages.question_generation.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await generate_questions(
            sample_contradictions, sample_norms, default_config
        )

        template_vars = mock_stage.call_args_list[0][0][2]
        norm_lookup = template_vars["norm_lookup"]
        assert "norm-1" in norm_lookup
        assert "norm-2" in norm_lookup
        assert norm_lookup["norm-1"].text == sample_norms[0].text


@pytest.mark.asyncio
async def test_generate_questions_quality_weights(
    default_config, sample_contradictions, sample_norms
):
    """Should include quality_weights in template vars."""
    mock_result = QuestionGenerationResult(questions=[])
    with patch(
        "pipeline.stages.question_generation.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_stage:
        await generate_questions(
            sample_contradictions, sample_norms, default_config
        )

        template_vars = mock_stage.call_args_list[0][0][2]
        assert "quality_weights" in template_vars
        # quality_criteria.yaml should be loaded
        assert "recency" in template_vars["quality_weights"]


@pytest.mark.asyncio
async def test_generate_questions_max_items(
    default_config, sample_contradictions, sample_norms
):
    """Should respect max_items limit."""
    default_config.question_generation.max_items = 1

    mock_result = QuestionGenerationResult(
        questions=[
            GeneratedQuestion(
                title="Q1", body="body1", category="A", confidence=0.9
            ),
            GeneratedQuestion(
                title="Q2", body="body2", category="B", confidence=0.8
            ),
        ]
    )
    with patch(
        "pipeline.stages.question_generation.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        questions = await generate_questions(
            sample_contradictions, sample_norms, default_config
        )

        assert len(questions) == 1


@pytest.mark.asyncio
async def test_generate_questions_empty_contradictions(default_config, sample_norms):
    """Should handle empty contradictions list."""
    mock_result = QuestionGenerationResult(questions=[])
    with patch(
        "pipeline.stages.question_generation.run_llm_stage",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        questions = await generate_questions([], sample_norms, default_config)
        assert questions == []
