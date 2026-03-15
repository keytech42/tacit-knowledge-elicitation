"""Plain text and markdown source adapter."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument, SourceType
from pipeline.registry import register

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md"}


@register("ingest", "text")
class TextAdapter:
    """Ingest plain text and markdown files from a file or directory."""

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        path = Path(source.path)
        if path.is_file():
            return [self._read_file(path)]
        if path.is_dir():
            docs = []
            for file_path in sorted(path.rglob("*")):
                if file_path.suffix.lower() in SUPPORTED_EXTENSIONS and file_path.is_file():
                    docs.append(self._read_file(file_path))
            return docs
        raise FileNotFoundError(f"Text source not found: {path}")

    def _read_file(self, path: Path) -> ParsedDocument:
        content = path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return ParsedDocument(
            source_path=str(path),
            source_type=SourceType.text,
            title=path.stem,
            raw_text=content,
            content_hash=content_hash,
        )
