"""Tests for the in-memory SSE event bus."""

import asyncio

import pytest

from app.services.event_bus import _channels, publish, subscribe


@pytest.fixture(autouse=True)
def clean_channels():
    """Ensure channels are clean between tests."""
    _channels.clear()
    yield
    _channels.clear()


@pytest.mark.asyncio
async def test_publish_subscribe():
    event = {"type": "answer_status_changed", "answer_id": "abc", "status": "approved"}

    async with subscribe("q1") as queue:
        publish("q1", event)
        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received == event


@pytest.mark.asyncio
async def test_multiple_subscribers():
    async with subscribe("q1") as q1, subscribe("q1") as q2:
        publish("q1", {"type": "test"})
        r1 = await asyncio.wait_for(q1.get(), timeout=1)
        r2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert r1 == r2 == {"type": "test"}


@pytest.mark.asyncio
async def test_publish_no_subscribers():
    """Publishing to a channel with no subscribers should not error."""
    publish("nonexistent", {"type": "test"})


@pytest.mark.asyncio
async def test_cleanup_on_unsubscribe():
    async with subscribe("q1"):
        assert "q1" in _channels
    assert "q1" not in _channels


@pytest.mark.asyncio
async def test_different_channels_isolated():
    async with subscribe("q1") as q1, subscribe("q2") as q2:
        publish("q1", {"type": "for_q1"})
        received = await asyncio.wait_for(q1.get(), timeout=1)
        assert received == {"type": "for_q1"}
        assert q2.empty()
