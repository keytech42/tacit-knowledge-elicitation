import io
import json
import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class FileParser(ABC):
    """Base class for file format parsers."""

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> str:
        """Parse file bytes into plain text."""
        ...


class TextParser(FileParser):
    """Parse plain text and markdown files."""

    def parse(self, content: bytes, filename: str) -> str:
        return content.decode("utf-8")


class PdfParser(FileParser):
    """Parse PDF files using pymupdf."""

    def parse(self, content: bytes, filename: str) -> str:
        import pymupdf

        doc = pymupdf.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)


class DocxParser(FileParser):
    """Parse DOCX files using python-docx."""

    def parse(self, content: bytes, filename: str) -> str:
        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)


class JsonParser(FileParser):
    """Parse JSON files by extracting text from all string values."""

    def parse(self, content: bytes, filename: str) -> str:
        data = json.loads(content.decode("utf-8"))
        return _extract_text_from_json(data)


def _extract_text_from_json(data, depth: int = 0, max_depth: int = 10) -> str:
    """Recursively extract string values from JSON structures."""
    if depth > max_depth:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = [_extract_text_from_json(item, depth + 1) for item in data]
        return "\n\n".join(p for p in parts if p)
    if isinstance(data, dict):
        parts = [_extract_text_from_json(v, depth + 1) for v in data.values()]
        return "\n\n".join(p for p in parts if p)
    return ""


# Registry mapping MIME types and extensions to parsers
_PARSERS: dict[str, FileParser] = {
    "text/plain": TextParser(),
    "text/markdown": TextParser(),
    "application/pdf": PdfParser(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxParser(),
    "application/json": JsonParser(),
}

_EXT_MAP: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
}

SUPPORTED_EXTENSIONS = list(_EXT_MAP.keys())
SUPPORTED_CONTENT_TYPES = list(_PARSERS.keys())
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def get_parser(content_type: str | None, filename: str) -> FileParser:
    """Get the appropriate parser for a file, trying content_type first, then extension."""
    if content_type and content_type in _PARSERS:
        return _PARSERS[content_type]
    # Fallback to extension
    ext = os.path.splitext(filename)[1].lower()
    mime = _EXT_MAP.get(ext)
    if mime and mime in _PARSERS:
        return _PARSERS[mime]
    raise ValueError(f"Unsupported file format: {content_type or ext}")


def parse_file(content: bytes, filename: str, content_type: str | None = None) -> str:
    """Parse a file into plain text. Raises ValueError for unsupported formats."""
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE})")
    parser = get_parser(content_type, filename)
    return parser.parse(content, filename)
