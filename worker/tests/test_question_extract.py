"""Unit tests for the question extraction task — chunking logic and task orchestration."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from worker.tasks.question_extract import _chunk_text, run_question_extraction
from worker.schemas import ExtractedQuestion, ExtractedQuestionSet


class TestChunkText:
    """Tests for paragraph-boundary text chunking."""

    def test_short_text_single_chunk(self):
        text = "This is a short paragraph."
        chunks = _chunk_text(text, max_chars=4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_returns_original(self):
        chunks = _chunk_text("", max_chars=4000)
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_splits_on_paragraph_boundaries(self):
        para1 = "A" * 2000
        para2 = "B" * 2000
        para3 = "C" * 2000
        text = f"{para1}\n\n{para2}\n\n{para3}"
        chunks = _chunk_text(text, max_chars=4100)
        assert len(chunks) == 2
        assert para1 in chunks[0]
        assert para2 in chunks[0]
        assert para3 in chunks[1]

    def test_single_long_paragraph_stays_together(self):
        # A single paragraph longer than max_chars can't be split
        text = "A" * 5000
        chunks = _chunk_text(text, max_chars=4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_many_short_paragraphs_grouped(self):
        paragraphs = [f"Paragraph {i}" for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = _chunk_text(text, max_chars=100)
        assert len(chunks) > 1
        # All content should be preserved
        rejoined = "\n\n".join(chunks)
        for p in paragraphs:
            assert p in rejoined

    def test_preserves_paragraph_content(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = _chunk_text(text, max_chars=10000)
        assert len(chunks) == 1
        assert "First paragraph." in chunks[0]
        assert "Second paragraph." in chunks[0]
        assert "Third paragraph." in chunks[0]


class TestRunQuestionExtraction:
    """Tests for the extraction task with mocked LLM and platform client."""

    @pytest.mark.asyncio
    async def test_single_chunk_skips_consolidation(self):
        """Short documents should only make one LLM call (no consolidation pass)."""
        mock_questions = [
            ExtractedQuestion(
                title="Q1", body="Body 1", category="cat",
                source_passage="passage 1", confidence=0.9,
            ),
        ]
        mock_result = ExtractedQuestionSet(
            questions=mock_questions, document_summary="A summary",
        )
        mock_llm = AsyncMock(return_value=mock_result)
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-123"})
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            result = await run_question_extraction(
                source_text="Short document.",
                document_title="Test",
                max_questions=10,
                source_document_id="doc-1",
            )

        assert result["count"] == 1
        assert result["document_summary"] == "A summary"
        # Only one LLM call (extraction), no consolidation
        assert mock_llm.call_count == 1
        # Question created with extracted source_type
        mock_platform.create_question.assert_called_once()
        call_kwargs = mock_platform.create_question.call_args
        assert call_kwargs.kwargs.get("source_type") or call_kwargs[1].get("source_type") == "extracted"

    @pytest.mark.asyncio
    async def test_multi_chunk_triggers_consolidation(self):
        """Long documents should trigger a consolidation pass."""
        mock_questions = [
            ExtractedQuestion(
                title=f"Q{i}", body=f"Body {i}", category="cat",
                source_passage=f"passage {i}", confidence=0.8,
            )
            for i in range(3)
        ]
        mock_extract_result = ExtractedQuestionSet(
            questions=mock_questions, document_summary="Chunk summary",
        )
        mock_consolidate_result = ExtractedQuestionSet(
            questions=mock_questions[:2], document_summary="Final summary",
        )
        mock_llm = AsyncMock(side_effect=[mock_extract_result, mock_extract_result, mock_consolidate_result])
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-123"})
        mock_platform.update_source_document = AsyncMock()

        # Create text that will be split into 2 chunks
        long_text = ("A" * 3000) + "\n\n" + ("B" * 3000)

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            result = await run_question_extraction(
                source_text=long_text,
                max_questions=5,
                source_document_id="doc-2",
            )

        # 2 extraction calls + 1 consolidation call
        assert mock_llm.call_count == 3
        assert result["count"] == 2
        assert result["document_summary"] == "Final summary"

    @pytest.mark.asyncio
    async def test_updates_source_document_after_extraction(self):
        """Source document should be updated with summary and count."""
        mock_result = ExtractedQuestionSet(
            questions=[
                ExtractedQuestion(
                    title="Q1", body="B", category="c",
                    source_passage="p", confidence=0.9,
                ),
            ],
            document_summary="Doc summary",
        )
        mock_llm = AsyncMock(return_value=mock_result)
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-1"})
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            await run_question_extraction(
                source_text="Content.",
                source_document_id="doc-99",
            )

        mock_platform.update_source_document.assert_called_once_with(
            "doc-99", summary="Doc summary", question_count=1,
        )

    @pytest.mark.asyncio
    async def test_no_source_document_update_when_id_missing(self):
        """When source_document_id is None, skip the update call."""
        mock_result = ExtractedQuestionSet(
            questions=[], document_summary="Empty",
        )
        mock_llm = AsyncMock(return_value=mock_result)
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            result = await run_question_extraction(source_text="Content.")

        mock_platform.update_source_document.assert_not_called()
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_failed_question_creation_continues(self):
        """If one question fails to create, the rest should still be created."""
        mock_questions = [
            ExtractedQuestion(
                title=f"Q{i}", body=f"B{i}", category="c",
                source_passage=f"p{i}", confidence=0.8,
            )
            for i in range(3)
        ]
        mock_result = ExtractedQuestionSet(
            questions=mock_questions, document_summary="Summary",
        )
        mock_llm = AsyncMock(return_value=mock_result)
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        # Second call raises, others succeed
        mock_platform.create_question = AsyncMock(
            side_effect=[{"id": "q-1"}, Exception("API error"), {"id": "q-3"}]
        )
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            result = await run_question_extraction(
                source_text="Content.",
                source_document_id="doc-1",
            )

        # 2 out of 3 created
        assert result["count"] == 2
        assert len(result["created_question_ids"]) == 2
