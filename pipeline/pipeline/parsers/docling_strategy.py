"""Docling CV/ML-based PDF parser strategy for scanned/complex PDFs."""

from __future__ import annotations

import logging

from pipeline.registry import register

logger = logging.getLogger(__name__)


@register("pdf_parser", "docling")
class DoclingParser:
    """Parse scanned and complex PDFs using the docling library (optional dependency)."""

    def parse(self, content: bytes, filename: str) -> str:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            raise ImportError(
                "The 'docling' library is required for the docling PDF parser. "
                "Install it with: pip install 'tacit-knowledge-pipeline[docling]'"
            )

        converter = DocumentConverter()
        result = converter.convert_from_binary(content, filename=filename)
        return result.document.export_to_text()
