"""PDF source adapter — delegates parsing to registered pdf_parser strategies."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument, SourceType
from pipeline.registry import get_strategy
from pipeline.registry import register

logger = logging.getLogger(__name__)

DEFAULT_PARSER = "pymupdf"


@register("ingest", "pdf")
class PdfAdapter:
    """Ingest PDF files from a file or directory."""

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        # Import parsers to trigger registration
        import pipeline.parsers.pymupdf_strategy  # noqa: F401

        parser_name = source.filters.get("parser", DEFAULT_PARSER)
        parser = get_strategy("pdf_parser", parser_name)

        path = Path(source.path)
        if path.is_file() and path.suffix.lower() == ".pdf":
            return [self._read_pdf(path, parser)]
        if path.is_dir():
            docs = []
            for pdf_file in sorted(path.rglob("*.pdf")):
                if pdf_file.is_file():
                    docs.append(self._read_pdf(pdf_file, parser))
            return docs
        raise FileNotFoundError(f"PDF source not found: {path}")

    def _read_pdf(self, path: Path, parser) -> ParsedDocument:
        content = path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        text = parser.parse(content, path.name)
        return ParsedDocument(
            source_path=str(path),
            source_type=SourceType.pdf,
            title=path.stem,
            raw_text=text,
            content_hash=content_hash,
        )
