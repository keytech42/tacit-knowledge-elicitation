"""Shared fixtures for worker tests."""

import pytest
import httpx

from worker.main import app, _tasks, _async_tasks


@pytest.fixture
def client():
    """Async HTTP client wired to the worker FastAPI app."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def clear_tasks():
    """Clear in-memory task tracking between tests."""
    _tasks.clear()
    _async_tasks.clear()
    yield
    _tasks.clear()
    _async_tasks.clear()
