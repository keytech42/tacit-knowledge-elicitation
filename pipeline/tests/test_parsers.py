"""Tests for PDF parser strategies."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from pipeline.registry import list_strategies


def _ensure_pymupdf_mock():
    """Ensure a mock pymupdf module exists so the parser can import it."""
    if "pymupdf" not in sys.modules:
        mock_mod = types.ModuleType("pymupdf")
        mock_mod.open = MagicMock()
        sys.modules["pymupdf"] = mock_mod


class TestPyMuPdfParser:
    def test_registration(self):
        import pipeline.parsers.pymupdf_strategy  # noqa: F401

        assert "pymupdf" in list_strategies("pdf_parser")

    def test_parse_with_mock(self):
        """Test the parser delegates to pymupdf correctly."""
        _ensure_pymupdf_mock()
        from pipeline.parsers.pymupdf_strategy import PyMuPdfParser

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content"

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_doc.close = MagicMock()

        with patch.object(sys.modules["pymupdf"], "open", return_value=mock_doc) as mock_open:
            parser = PyMuPdfParser()
            result = parser.parse(b"fake pdf bytes", "test.pdf")

            mock_open.assert_called_once_with(stream=b"fake pdf bytes", filetype="pdf")
            mock_doc.close.assert_called_once()
            assert result == "Page 1 content"

    def test_parse_multipage_with_mock(self):
        """Test multi-page PDF concatenation."""
        _ensure_pymupdf_mock()
        from pipeline.parsers.pymupdf_strategy import PyMuPdfParser

        page1 = MagicMock()
        page1.get_text.return_value = "First page"
        page2 = MagicMock()
        page2.get_text.return_value = "Second page"

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([page1, page2])

        with patch.object(sys.modules["pymupdf"], "open", return_value=mock_doc):
            parser = PyMuPdfParser()
            result = parser.parse(b"fake pdf bytes", "test.pdf")
            assert result == "First page\n\nSecond page"


class TestDoclingParser:
    def test_registration(self):
        import pipeline.parsers.docling_strategy  # noqa: F401

        assert "docling" in list_strategies("pdf_parser")

    def test_import_error_message(self):
        """Docling parser raises helpful error when docling is not installed."""
        from pipeline.parsers.docling_strategy import DoclingParser

        with patch.dict("sys.modules", {"docling": None, "docling.document_converter": None}):
            parser = DoclingParser()
            with pytest.raises(ImportError, match="docling"):
                parser.parse(b"fake pdf", "test.pdf")
