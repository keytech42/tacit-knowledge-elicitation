"""PDF parser protocol and registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PdfParser(Protocol):
    """Protocol for PDF parsing strategies."""

    def parse(self, content: bytes, filename: str) -> str:
        """Parse PDF bytes into plain text."""
        ...
