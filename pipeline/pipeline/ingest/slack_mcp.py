"""Slack MCP source adapter — live data retrieval via Slack MCP server.

# TODO: Implement live Slack ingestion via MCP client SDK
#
# Architecture:
#   Pipeline (MCP Client) → Slack MCP Server → Slack API → Channels/Messages
#
# MCP Server availability (as of 2026-03):
#   - Slack does NOT yet provide an official MCP server for custom MCP clients
#   - Claude Code has built-in Slack MCP access (mcp__claude_ai_Slack__* tools),
#     but this is not exposed for standalone MCP client connections
#   - Open-source alternatives exist that wrap the Slack API as an MCP server:
#     * https://github.com/modelcontextprotocol/servers (check for community Slack server)
#     * Custom MCP server wrapping Slack's Web API (conversations.list, conversations.history)
#   - Until an official server is available, the recommended approach is:
#     a. Use the file-based SlackAdapter (type: "slack") with JSON exports, OR
#     b. Build/use an open-source Slack MCP server wrapper
#
# Available Slack MCP tools (from Claude Code's built-in integration):
#   - slack_search_channels: Find channels by name/topic
#   - slack_read_channel: Read recent messages from a channel
#   - slack_read_thread: Read a specific thread
#   - slack_search_public: Search messages across public channels
#   - slack_search_public_and_private: Search all accessible messages
#   - slack_read_user_profile: Get user profile info
#
# Implementation steps (when MCP server becomes available):
#   1. Add `mcp` SDK dependency to pyproject.toml (shared with notion_mcp)
#   2. Implement MCP client connection to Slack MCP server
#   3. Use slack_search_channels to discover channels (filtered by config)
#   4. Use slack_read_channel to retrieve message history per channel
#   5. Convert messages to ParsedDocument (same format as SlackAdapter output)
#   6. Handle pagination for channels with long history
#   7. Add incremental mode: track oldest_ts per channel, only pull new messages
#   8. Resolve user IDs to display names via slack_read_user_profile
#
# Config example:
#   sources:
#     - type: slack_mcp
#       path: ""                              # unused for MCP
#       filters:
#         channels:                           # specific channels to ingest
#           - general
#           - bharvest-dev-culture
#         search_query: "decision process"    # or search across all channels
#         after: "2025-01-01"                 # incremental: messages after date
#         server_url: "http://localhost:3001"  # MCP server address
"""

from __future__ import annotations

import hashlib
import logging

from pipeline.config import SourceConfig
from pipeline.models import ParsedDocument, SourceType
from pipeline.registry import register

logger = logging.getLogger(__name__)


@register("ingest", "slack_mcp")
class SlackMCPAdapter:
    """Ingest Slack messages via MCP client connection to a Slack MCP server.

    TODO: Implement MCP client connection. Currently raises NotImplementedError.

    Status: Slack does not yet provide an official MCP server for custom clients.
    Options:
        1. Use file-based SlackAdapter (type: "slack") with JSON exports (recommended)
        2. Use an open-source Slack MCP server wrapper
        3. Wait for Slack's official MCP server release

    Requires:
        - MCP client SDK (pip install mcp)
        - A Slack MCP server running and accessible (official or open-source)
        - SLACK_MCP_SERVER_URL in environment or config
    """

    def ingest(self, source: SourceConfig) -> list[ParsedDocument]:
        """Retrieve Slack messages via MCP and return as ParsedDocuments.

        TODO: Implementation outline:
            1. Connect to Slack MCP server via MCP client SDK
            2. If source.filters has "channels":
               - For each channel, call slack_read_channel to get message history
            3. If source.filters has "search_query":
               - Call slack_search_public_and_private with the query
            4. For each channel's messages:
               - Format as "{user}: {text}" (same as file-based SlackAdapter)
               - Resolve user IDs to names via slack_read_user_profile (cache results)
               - Build ParsedDocument with source_type=SourceType.slack_mcp
               - Set metadata: channel name, message count, date range
            5. If source.filters.get("after"), skip messages before cutoff timestamp
            6. Return list of ParsedDocuments
        """
        # TODO: Replace with actual MCP client implementation
        raise NotImplementedError(
            "SlackMCPAdapter requires an MCP client SDK and a running Slack MCP server. "
            "Slack does not yet provide an official MCP server for custom clients. "
            "For file-based Slack ingestion, use type: 'slack' with a local JSON export directory."
        )

    def _connect(self, source: SourceConfig):
        """Establish MCP client connection to Slack MCP server.

        TODO:
            - Read server URL from source.filters.get("server_url") or SLACK_MCP_SERVER_URL env var
            - Initialize MCP client session
            - Verify connection by listing available tools
        """
        ...

    def _read_channel(self, channel_name: str, after: str | None = None) -> list[dict]:
        """Read messages from a channel via MCP slack_read_channel tool.

        TODO:
            - Call slack_read_channel with channel name
            - Handle pagination (Slack limits to ~100 messages per call)
            - Filter by timestamp if `after` is specified
            - Return list of message dicts with text, user, ts fields
        """
        ...

    def _search_messages(self, query: str) -> list[dict]:
        """Search messages across channels via MCP slack_search_public_and_private tool.

        TODO:
            - Call slack_search_public_and_private with query
            - Group results by channel
            - Return list of message dicts
        """
        ...

    def _resolve_user(self, user_id: str) -> str:
        """Resolve a Slack user ID to display name via MCP slack_read_user_profile.

        TODO:
            - Cache resolved names to avoid repeated MCP calls
            - Call slack_read_user_profile for cache misses
            - Return display name or fall back to user_id
        """
        ...

    def _to_document(self, channel_name: str, messages: list[str], metadata: dict) -> ParsedDocument:
        """Convert channel messages to a ParsedDocument."""
        text = "\n\n".join(messages)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ParsedDocument(
            source_path=f"slack://{channel_name}",
            source_type=SourceType.slack_mcp,
            title=f"#{channel_name}",
            raw_text=text,
            content_hash=content_hash,
            metadata=metadata,
        )
