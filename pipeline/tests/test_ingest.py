"""Tests for source ingestion adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.config import SourceConfig
from pipeline.models import SourceType

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Text adapter ---


class TestTextAdapter:
    def test_ingest_single_file(self):
        from pipeline.ingest.text import TextAdapter

        adapter = TextAdapter()
        source = SourceConfig(type="text", path=str(FIXTURES_DIR / "text_files" / "sample.md"))
        docs = adapter.ingest(source)

        assert len(docs) == 1
        assert docs[0].source_type == SourceType.text
        assert docs[0].title == "sample"
        assert "code review" in docs[0].raw_text
        assert docs[0].content_hash  # non-empty

    def test_ingest_directory(self):
        from pipeline.ingest.text import TextAdapter

        adapter = TextAdapter()
        source = SourceConfig(type="text", path=str(FIXTURES_DIR / "text_files"))
        docs = adapter.ingest(source)

        assert len(docs) >= 1
        assert all(d.source_type == SourceType.text for d in docs)

    def test_ingest_missing_path(self):
        from pipeline.ingest.text import TextAdapter

        adapter = TextAdapter()
        source = SourceConfig(type="text", path="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            adapter.ingest(source)

    def test_content_hash_is_deterministic(self):
        from pipeline.ingest.text import TextAdapter

        adapter = TextAdapter()
        source = SourceConfig(type="text", path=str(FIXTURES_DIR / "text_files" / "sample.md"))
        docs1 = adapter.ingest(source)
        docs2 = adapter.ingest(source)
        assert docs1[0].content_hash == docs2[0].content_hash


# --- Slack adapter ---


class TestSlackAdapter:
    def test_ingest_slack_export(self):
        from pipeline.ingest.slack import SlackAdapter

        adapter = SlackAdapter()
        source = SourceConfig(type="slack", path=str(FIXTURES_DIR / "slack_export"))
        docs = adapter.ingest(source)

        assert len(docs) == 1
        doc = docs[0]
        assert doc.source_type == SourceType.slack
        assert doc.title == "#general"
        assert doc.metadata["channel"] == "general"
        assert "deployment process" in doc.raw_text
        assert doc.content_hash

    def test_ingest_with_channel_filter(self):
        from pipeline.ingest.slack import SlackAdapter

        adapter = SlackAdapter()
        source = SourceConfig(
            type="slack",
            path=str(FIXTURES_DIR / "slack_export"),
            filters={"channels": ["nonexistent"]},
        )
        docs = adapter.ingest(source)
        assert len(docs) == 0

    def test_messages_include_user(self):
        from pipeline.ingest.slack import SlackAdapter

        adapter = SlackAdapter()
        source = SourceConfig(type="slack", path=str(FIXTURES_DIR / "slack_export"))
        docs = adapter.ingest(source)
        # Messages should be formatted as "user: text"
        assert "U001:" in docs[0].raw_text

    def test_ingest_missing_directory(self):
        from pipeline.ingest.slack import SlackAdapter

        adapter = SlackAdapter()
        source = SourceConfig(type="slack", path="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            adapter.ingest(source)


# --- Notion adapter ---


class TestNotionAdapter:
    def test_ingest_notion_export(self):
        from pipeline.ingest.notion import NotionAdapter

        adapter = NotionAdapter()
        source = SourceConfig(type="notion", path=str(FIXTURES_DIR / "notion_export"))
        docs = adapter.ingest(source)

        assert len(docs) == 2
        assert all(d.source_type == SourceType.notion for d in docs)
        titles = {d.title for d in docs}
        assert "Process" in titles
        assert "Values" in titles

    def test_metadata_has_relative_path(self):
        from pipeline.ingest.notion import NotionAdapter

        adapter = NotionAdapter()
        source = SourceConfig(type="notion", path=str(FIXTURES_DIR / "notion_export"))
        docs = adapter.ingest(source)

        for doc in docs:
            assert "relative_path" in doc.metadata
            assert doc.metadata["relative_path"].startswith("team-wiki/")

    def test_ingest_missing_directory(self):
        from pipeline.ingest.notion import NotionAdapter

        adapter = NotionAdapter()
        source = SourceConfig(type="notion", path="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            adapter.ingest(source)


# --- PDF adapter ---


class TestPdfAdapter:
    def test_ingest_pdf_with_mock_parser(self, monkeypatch):
        """Test PDF adapter with a mocked pymupdf parser."""
        import pipeline.parsers.pymupdf_strategy  # noqa: F401
        from pipeline.ingest.pdf import PdfAdapter
        from pipeline.registry import _REGISTRIES

        class FakeParser:
            def parse(self, content: bytes, filename: str) -> str:
                return "Parsed PDF content"

        _REGISTRIES.setdefault("pdf_parser", {})["pymupdf"] = FakeParser

        # Create a temporary PDF file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake pdf content")
            pdf_path = f.name

        try:
            adapter = PdfAdapter()
            source = SourceConfig(type="pdf", path=pdf_path)
            docs = adapter.ingest(source)

            assert len(docs) == 1
            assert docs[0].source_type == SourceType.pdf
            assert docs[0].raw_text == "Parsed PDF content"
            assert docs[0].content_hash
        finally:
            Path(pdf_path).unlink()

    def test_ingest_missing_path(self):
        from pipeline.ingest.pdf import PdfAdapter

        adapter = PdfAdapter()
        source = SourceConfig(type="pdf", path="/nonexistent/file.pdf")
        with pytest.raises(FileNotFoundError):
            adapter.ingest(source)


# --- Registry integration ---


class TestRegistryIntegration:
    def test_all_adapters_registered(self):
        # Import all adapters to trigger registration
        import pipeline.ingest.text  # noqa: F401
        import pipeline.ingest.slack  # noqa: F401
        import pipeline.ingest.notion  # noqa: F401
        import pipeline.ingest.pdf  # noqa: F401
        import pipeline.ingest.notion_mcp  # noqa: F401
        import pipeline.ingest.slack_mcp  # noqa: F401

        from pipeline.registry import list_strategies

        strategies = list_strategies("ingest")
        assert "text" in strategies
        assert "slack" in strategies
        assert "notion" in strategies
        assert "pdf" in strategies
        assert "notion_mcp" in strategies
        assert "slack_mcp" in strategies


class TestNotionMCPAdapter:
    def test_raises_not_implemented(self):
        from pipeline.ingest.notion_mcp import NotionMCPAdapter

        adapter = NotionMCPAdapter()
        source = SourceConfig(type="notion_mcp", path="")
        with pytest.raises(NotImplementedError, match="MCP client SDK"):
            adapter.ingest(source)

    def test_to_document(self):
        from pipeline.ingest.notion_mcp import NotionMCPAdapter

        adapter = NotionMCPAdapter()
        doc = adapter._to_document(
            page_id="abc123",
            title="Test Page",
            content="Some content",
            metadata={"workspace": "test"},
        )
        assert doc.source_type == SourceType.notion_mcp
        assert doc.title == "Test Page"
        assert doc.source_path == "notion://abc123"
        assert doc.content_hash  # non-empty


class TestSlackMCPAdapter:
    def test_raises_not_implemented(self):
        from pipeline.ingest.slack_mcp import SlackMCPAdapter

        adapter = SlackMCPAdapter()
        source = SourceConfig(type="slack_mcp", path="")
        with pytest.raises(NotImplementedError, match="official MCP server"):
            adapter.ingest(source)

    def test_to_document(self):
        from pipeline.ingest.slack_mcp import SlackMCPAdapter

        adapter = SlackMCPAdapter()
        doc = adapter._to_document(
            channel_name="general",
            messages=["user1: hello", "user2: world"],
            metadata={"channel": "general", "message_count": 2},
        )
        assert doc.source_type == SourceType.slack_mcp
        assert doc.title == "#general"
        assert doc.source_path == "slack://general"
        assert "hello" in doc.raw_text
        assert doc.content_hash  # non-empty
