"""PyMuPDF-based PDF parser strategy."""

from __future__ import annotations

import logging

from pipeline.registry import register

logger = logging.getLogger(__name__)


@register("pdf_parser", "pymupdf")
class PyMuPdfParser:
    """Parse PDFs using pymupdf (fitz)."""

    def parse(self, content: bytes, filename: str) -> str:
        import pymupdf

        doc = pymupdf.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
