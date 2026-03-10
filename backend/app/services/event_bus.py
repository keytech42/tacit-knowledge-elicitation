"""In-memory pub/sub event bus for SSE.

Each channel is keyed by a string (e.g. question UUID).  Subscribers receive
events via asyncio.Queue.  Publishing fans out to all active subscribers.
"""

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

_channels: dict[str, set[asyncio.Queue]] = defaultdict(set)


def publish(channel: str, event: dict[str, Any]) -> None:
    """Push an event to all subscribers on a channel (non-blocking)."""
    for queue in _channels.get(channel, set()):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for channel %s, dropping event", channel)


@asynccontextmanager
async def subscribe(channel: str):
    """Async context manager that yields an asyncio.Queue receiving events."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _channels[channel].add(queue)
    try:
        yield queue
    finally:
        _channels[channel].discard(queue)
        if not _channels[channel]:
            del _channels[channel]
