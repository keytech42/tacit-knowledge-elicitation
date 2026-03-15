"""Slack JSON export source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument, SourceType
from pipeline.registry import register

logger = logging.getLogger(__name__)


@register("ingest", "slack")
class SlackAdapter:
    """Ingest a Slack JSON export directory.

    Expected structure: ``<channel_name>/`` dirs containing JSON files,
    each with an array of message objects (``text``, ``user``, ``ts`` fields).
    """

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        root = Path(source.path)
        if not root.is_dir():
            raise FileNotFoundError(f"Slack export directory not found: {root}")

        channel_filter = source.filters.get("channels")
        docs: list[ParsedDocument] = []

        for channel_dir in sorted(root.iterdir()):
            if not channel_dir.is_dir():
                continue
            channel_name = channel_dir.name
            if channel_filter and channel_name not in channel_filter:
                continue

            messages = self._load_channel(channel_dir)
            if not messages:
                continue

            text = "\n\n".join(messages)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            docs.append(
                ParsedDocument(
                    source_path=str(channel_dir),
                    source_type=SourceType.slack,
                    title=f"#{channel_name}",
                    raw_text=text,
                    content_hash=content_hash,
                    metadata={"channel": channel_name},
                )
            )

        return docs

    def _load_channel(self, channel_dir: Path) -> list[str]:
        """Load and concatenate messages from all JSON files in a channel dir."""
        messages: list[str] = []
        for json_file in sorted(channel_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning(f"Skipping invalid JSON file: {json_file}")
                continue
            if not isinstance(data, list):
                continue
            for msg in data:
                text = msg.get("text", "").strip()
                if text:
                    user = msg.get("user", "unknown")
                    messages.append(f"{user}: {text}")
        return messages
