"""Sliding-window chunking strategy with configurable overlap."""

from __future__ import annotations

from pipeline.models import ParsedChunk
from pipeline.registry import register


@register("chunking", "sliding_window")
class SlidingWindowChunker:
    """Fixed-size character windows with overlap, breaking at word boundaries."""

    def __init__(self, max_chars: int = 4000, overlap: int = 200, **kwargs):
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> list[ParsedChunk]:
        if not text.strip():
            return []

        # Pre-compute all chunks, then set total_chunks
        raw_chunks: list[tuple[str, int]] = []  # (text, char_offset)
        pos = 0
        while pos < len(text):
            end = min(pos + self.max_chars, len(text))
            # Break at word boundary if we're not at the end of text
            if end < len(text):
                # Search backward for a space to break at a word boundary
                boundary = text.rfind(" ", pos, end)
                if boundary > pos:
                    end = boundary + 1  # include the space in this chunk

            chunk_text = text[pos:end].strip()
            if chunk_text:
                raw_chunks.append((chunk_text, pos))

            # Advance by (end - overlap), but never go backward
            next_pos = end - self.overlap
            if next_pos <= pos:
                next_pos = end
            pos = next_pos

        total = len(raw_chunks)
        return [
            ParsedChunk(
                text=chunk_text,
                chunk_index=i,
                total_chunks=total,
                char_offset=char_offset,
            )
            for i, (chunk_text, char_offset) in enumerate(raw_chunks)
        ]
