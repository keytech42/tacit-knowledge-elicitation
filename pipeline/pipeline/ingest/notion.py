"""Notion markdown export source adapter."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument, SourceType
from pipeline.registry import register

logger = logging.getLogger(__name__)


@register("ingest", "notion")
class NotionAdapter:
    """Ingest a Notion markdown export directory.

    Walks recursively; each ``.md`` file becomes a ParsedDocument.
    """

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        root = Path(source.path)
        if not root.is_dir():
            raise FileNotFoundError(f"Notion export directory not found: {root}")

        docs: list[ParsedDocument] = []
        for md_file in sorted(root.rglob("*.md")):
            if not md_file.is_file():
                continue
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            relative_path = str(md_file.relative_to(root))
            docs.append(
                ParsedDocument(
                    source_path=str(md_file),
                    source_type=SourceType.notion,
                    title=md_file.stem,
                    raw_text=content,
                    content_hash=content_hash,
                    metadata={"relative_path": relative_path},
                )
            )

        return docs
