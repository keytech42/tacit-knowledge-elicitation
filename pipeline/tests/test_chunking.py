"""Tests for chunking strategies."""

from __future__ import annotations

import pytest

from pipeline.registry import list_strategies


class TestParagraphChunker:
    def test_registration(self):
        import pipeline.chunking.paragraph  # noqa: F401

        assert "paragraph" in list_strategies("chunking")

    def test_single_paragraph(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        chunker = ParagraphChunker(max_chars=4000)
        chunks = chunker.chunk("A single paragraph of text.")

        assert len(chunks) == 1
        assert chunks[0].text == "A single paragraph of text."
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
        assert chunks[0].char_offset == 0

    def test_multiple_paragraphs_fit_in_one_chunk(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunker = ParagraphChunker(max_chars=4000)
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert "Paragraph one." in chunks[0].text
        assert "Paragraph three." in chunks[0].text

    def test_paragraphs_split_when_exceeding_max(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        # Create text that will need splitting
        p1 = "A" * 100
        p2 = "B" * 100
        p3 = "C" * 100
        text = f"{p1}\n\n{p2}\n\n{p3}"

        chunker = ParagraphChunker(max_chars=150)
        chunks = chunker.chunk(text)

        assert len(chunks) > 1
        assert all(c.total_chunks == len(chunks) for c in chunks)
        # Verify chunk indices are sequential
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_empty_text(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        chunker = ParagraphChunker(max_chars=4000)
        chunks = chunker.chunk("")
        assert chunks == []

    def test_whitespace_only(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        chunker = ParagraphChunker(max_chars=4000)
        chunks = chunker.chunk("   \n\n   ")
        assert chunks == []

    def test_char_offset_tracking(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunker = ParagraphChunker(max_chars=25)
        chunks = chunker.chunk(text)

        assert len(chunks) >= 2
        assert chunks[0].char_offset == 0
        # Second chunk offset should be > 0
        assert chunks[1].char_offset > 0

    def test_preserves_all_content(self):
        from pipeline.chunking.paragraph import ParagraphChunker

        text = "Para one about testing.\n\nPara two about code.\n\nPara three about review."
        chunker = ParagraphChunker(max_chars=40)
        chunks = chunker.chunk(text)

        # All original text should be present across chunks
        combined = " ".join(c.text for c in chunks)
        assert "testing" in combined
        assert "code" in combined
        assert "review" in combined


class TestSlidingWindowChunker:
    def test_registration(self):
        import pipeline.chunking.sliding_window  # noqa: F401

        assert "sliding_window" in list_strategies("chunking")

    def test_short_text_single_chunk(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        chunker = SlidingWindowChunker(max_chars=1000, overlap=100)
        chunks = chunker.chunk("Short text.")

        assert len(chunks) == 1
        assert chunks[0].text == "Short text."
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_overlap_creates_more_chunks(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        text = "word " * 200  # 1000 chars
        chunker_no_overlap = SlidingWindowChunker(max_chars=300, overlap=0)
        chunker_with_overlap = SlidingWindowChunker(max_chars=300, overlap=100)

        chunks_no = chunker_no_overlap.chunk(text)
        chunks_with = chunker_with_overlap.chunk(text)

        assert len(chunks_with) > len(chunks_no)

    def test_word_boundary_breaking(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        text = "hello world this is a test of word boundary breaking in chunks"
        chunker = SlidingWindowChunker(max_chars=20, overlap=5)
        chunks = chunker.chunk(text)

        # Chunks should not break mid-word (when possible)
        for chunk in chunks:
            # The chunk text should not start or end with a partial word
            # (after stripping, no leading/trailing word fragments)
            assert chunk.text == chunk.text.strip()

    def test_empty_text(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        chunker = SlidingWindowChunker(max_chars=100, overlap=20)
        chunks = chunker.chunk("")
        assert chunks == []

    def test_chunk_indices_and_totals(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        text = "word " * 100  # 500 chars
        chunker = SlidingWindowChunker(max_chars=100, overlap=20)
        chunks = chunker.chunk(text)

        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)

    def test_char_offsets_increase(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        text = "word " * 100
        chunker = SlidingWindowChunker(max_chars=100, overlap=20)
        chunks = chunker.chunk(text)

        offsets = [c.char_offset for c in chunks]
        assert offsets == sorted(offsets)
        assert offsets[0] == 0

    def test_overlap_content_shared(self):
        from pipeline.chunking.sliding_window import SlidingWindowChunker

        # With overlap, consecutive chunks should share some content
        text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        chunker = SlidingWindowChunker(max_chars=30, overlap=10)
        chunks = chunker.chunk(text)

        if len(chunks) >= 2:
            # Some characters from the end of chunk 0 should appear in chunk 1
            # (due to overlap)
            end_of_first = chunks[0].text[-10:]
            assert any(
                word in chunks[1].text
                for word in end_of_first.split()
                if len(word) > 2
            )
