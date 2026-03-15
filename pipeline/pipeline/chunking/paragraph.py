"""Paragraph-boundary chunking strategy — ported from worker."""

from __future__ import annotations

from pipeline.models import ParsedChunk
from pipeline.registry import register


@register("chunking", "paragraph")
class ParagraphChunker:
    """Split text on paragraph boundaries (``\\n\\n``), accumulating up to max_chars."""

    def __init__(self, max_chars: int = 4000, **kwargs):
        self.max_chars = max_chars

    def chunk(self, text: str) -> list[ParsedChunk]:
        if not text.strip():
            return []

        paragraphs = text.split("\n\n")
        raw_chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > self.max_chars:
                raw_chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            raw_chunks.append(current.strip())

        if not raw_chunks:
            raw_chunks = [text]

        total = len(raw_chunks)
        chunks: list[ParsedChunk] = []
        offset = 0
        for i, chunk_text in enumerate(raw_chunks):
            chunks.append(
                ParsedChunk(
                    text=chunk_text,
                    chunk_index=i,
                    total_chunks=total,
                    char_offset=offset,
                )
            )
            # Advance offset by chunk text length + the separator (\n\n = 2 chars)
            offset += len(chunk_text) + 2

        return chunks
