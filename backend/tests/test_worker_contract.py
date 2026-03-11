"""Contract tests for worker_client.py — verifies HTTP payloads and error handling.

These tests mock httpx.AsyncClient to verify that the worker client sends the
correct HTTP requests with the right payloads, URLs, and timeouts, and handles
all error conditions gracefully (returning None).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import worker_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_WORKER_URL = "http://fake-worker:8001"


def _make_mock_response(status_code: int = 200, json_data: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class _MockAsyncClient:
    """Mock httpx.AsyncClient that supports async context manager protocol."""

    def __init__(self, response=None, side_effect=None, **kwargs):
        self.init_kwargs = kwargs
        self.post = AsyncMock(return_value=response, side_effect=side_effect)
        self.get = AsyncMock(return_value=response, side_effect=side_effect)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture(autouse=True)
def _enable_worker():
    """Enable WORKER_URL for all tests in this module."""
    with patch.object(worker_client.settings, "WORKER_URL", FAKE_WORKER_URL):
        yield


# ---------------------------------------------------------------------------
# WORKER_URL disabled (empty string)
# ---------------------------------------------------------------------------


class TestWorkerDisabled:
    """When WORKER_URL is empty, all functions should return None immediately."""

    @pytest.fixture(autouse=True)
    def _disable_worker(self):
        with patch.object(worker_client.settings, "WORKER_URL", ""):
            yield

    @pytest.mark.asyncio
    async def test_trigger_generate_questions_disabled(self):
        result = await worker_client.trigger_generate_questions("topic")
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_scaffold_options_disabled(self):
        result = await worker_client.trigger_scaffold_options(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_review_assist_disabled(self):
        result = await worker_client.trigger_review_assist(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_extract_questions_disabled(self):
        result = await worker_client.trigger_extract_questions("text")
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_recommend_disabled(self):
        result = await worker_client.trigger_recommend({}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_status_disabled(self):
        result = await worker_client.get_task_status("task-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_task_disabled(self):
        result = await worker_client.cancel_task("task-1")
        assert result is None


# ---------------------------------------------------------------------------
# trigger_generate_questions
# ---------------------------------------------------------------------------


class TestTriggerGenerateQuestions:

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        resp = _make_mock_response(200, {"task_id": "t1", "status": "accepted"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.trigger_generate_questions(
                "AI safety", domain="ml", count=5,
            )

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/generate-questions",
            json={"topic": "AI safety", "domain": "ml", "count": 5},
        )
        assert result == {"task_id": "t1", "status": "accepted"}

    @pytest.mark.asyncio
    async def test_includes_context_when_provided(self):
        resp = _make_mock_response(200, {"task_id": "t2"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_generate_questions(
                "topic", context="extra context",
            )

        payload = mock_client.post.call_args[1]["json"]
        assert payload["context"] == "extra context"

    @pytest.mark.asyncio
    async def test_omits_context_when_none(self):
        resp = _make_mock_response(200, {"task_id": "t3"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_generate_questions("topic", context=None)

        payload = mock_client.post.call_args[1]["json"]
        assert "context" not in payload

    @pytest.mark.asyncio
    async def test_omits_context_when_empty_string(self):
        resp = _make_mock_response(200, {"task_id": "t4"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_generate_questions("topic", context="")

        payload = mock_client.post.call_args[1]["json"]
        assert "context" not in payload

    @pytest.mark.asyncio
    async def test_default_params(self):
        resp = _make_mock_response(200, {"task_id": "t5"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_generate_questions("topic")

        payload = mock_client.post.call_args[1]["json"]
        assert payload == {"topic": "topic", "domain": "", "count": 3}

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_generate_questions("topic")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_generate_questions("topic")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(500, {"error": "internal"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_generate_questions("topic")

        assert result is None


# ---------------------------------------------------------------------------
# trigger_scaffold_options
# ---------------------------------------------------------------------------


class TestTriggerScaffoldOptions:

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        qid = uuid.uuid4()
        resp = _make_mock_response(200, {"task_id": "s1"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.trigger_scaffold_options(qid, num_options=3)

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/scaffold-options",
            json={"question_id": str(qid), "num_options": 3},
        )
        assert result == {"task_id": "s1"}

    @pytest.mark.asyncio
    async def test_default_num_options(self):
        qid = uuid.uuid4()
        resp = _make_mock_response(200, {"task_id": "s2"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_scaffold_options(qid)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["num_options"] == 4

    @pytest.mark.asyncio
    async def test_uuid_serialized_as_string(self):
        qid = uuid.uuid4()
        resp = _make_mock_response(200, {"task_id": "s3"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_scaffold_options(qid)

        payload = mock_client.post.call_args[1]["json"]
        assert isinstance(payload["question_id"], str)
        assert payload["question_id"] == str(qid)

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_scaffold_options(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_scaffold_options(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(422, {"detail": "bad input"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_scaffold_options(uuid.uuid4())

        assert result is None


# ---------------------------------------------------------------------------
# trigger_review_assist
# ---------------------------------------------------------------------------


class TestTriggerReviewAssist:

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        aid = uuid.uuid4()
        resp = _make_mock_response(200, {"task_id": "r1"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.trigger_review_assist(aid)

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/review-assist",
            json={"answer_id": str(aid)},
        )
        assert result == {"task_id": "r1"}

    @pytest.mark.asyncio
    async def test_uuid_serialized_as_string(self):
        aid = uuid.uuid4()
        resp = _make_mock_response(200, {"task_id": "r2"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_review_assist(aid)

        payload = mock_client.post.call_args[1]["json"]
        assert isinstance(payload["answer_id"], str)

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_review_assist(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_review_assist(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(503, {"error": "unavailable"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_review_assist(uuid.uuid4())

        assert result is None


# ---------------------------------------------------------------------------
# trigger_extract_questions
# ---------------------------------------------------------------------------


class TestTriggerExtractQuestions:

    @pytest.mark.asyncio
    async def test_sends_correct_payload_all_params(self):
        resp = _make_mock_response(200, {"task_id": "e1"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.trigger_extract_questions(
                source_text="doc content",
                document_title="My Doc",
                domain="engineering",
                max_questions=5,
                source_document_id="doc-uuid-123",
            )

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/extract-questions",
            json={
                "source_text": "doc content",
                "document_title": "My Doc",
                "domain": "engineering",
                "max_questions": 5,
                "source_document_id": "doc-uuid-123",
            },
        )
        assert result == {"task_id": "e1"}

    @pytest.mark.asyncio
    async def test_omits_source_document_id_when_none(self):
        resp = _make_mock_response(200, {"task_id": "e2"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_extract_questions("text")

        payload = mock_client.post.call_args[1]["json"]
        assert "source_document_id" not in payload

    @pytest.mark.asyncio
    async def test_omits_source_document_id_when_empty_string(self):
        resp = _make_mock_response(200, {"task_id": "e3"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_extract_questions("text", source_document_id="")

        payload = mock_client.post.call_args[1]["json"]
        assert "source_document_id" not in payload

    @pytest.mark.asyncio
    async def test_default_params(self):
        resp = _make_mock_response(200, {"task_id": "e4"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_extract_questions("text")

        payload = mock_client.post.call_args[1]["json"]
        assert payload == {
            "source_text": "text",
            "document_title": "",
            "domain": "",
            "max_questions": 10,
        }

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_extract_questions("text")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_extract_questions("text")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(500)
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_extract_questions("text")

        assert result is None


# ---------------------------------------------------------------------------
# trigger_recommend (60s timeout, not 10s)
# ---------------------------------------------------------------------------


class TestTriggerRecommend:

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        question = {"id": "q1", "title": "Q", "body": "body"}
        candidates = [{"id": "c1", "answers": []}]
        resp = _make_mock_response(200, {"items": [{"id": "c1", "score": 0.9}]})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.trigger_recommend(
                question, candidates, top_k=3,
            )

        mock_cls.assert_called_once_with(timeout=60.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/recommend",
            json={
                "question": question,
                "candidates": candidates,
                "top_k": 3,
            },
        )
        assert result == {"items": [{"id": "c1", "score": 0.9}]}

    @pytest.mark.asyncio
    async def test_timeout_is_60_seconds(self):
        """Recommend uses a longer timeout (60s) than other calls (10s)."""
        resp = _make_mock_response(200, {})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await worker_client.trigger_recommend({}, [])

        mock_cls.assert_called_once_with(timeout=60.0)

    @pytest.mark.asyncio
    async def test_default_top_k(self):
        resp = _make_mock_response(200, {"items": []})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await worker_client.trigger_recommend({}, [])

        payload = mock_client.post.call_args[1]["json"]
        assert payload["top_k"] == 5

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_recommend({}, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_recommend({}, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(500)
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.trigger_recommend({}, [])

        assert result is None


# ---------------------------------------------------------------------------
# get_task_status
# ---------------------------------------------------------------------------


class TestGetTaskStatus:

    @pytest.mark.asyncio
    async def test_sends_correct_get_request(self):
        resp = _make_mock_response(200, {
            "task_id": "task-abc",
            "status": "completed",
            "result": {"questions": ["q1"]},
            "error": None,
        })
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.get_task_status("task-abc")

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.get.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/task-abc",
        )
        assert result == {
            "task_id": "task-abc",
            "status": "completed",
            "result": {"questions": ["q1"]},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.get_task_status("task-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.get_task_status("task-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(404)
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.get_task_status("nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# cancel_task
# ---------------------------------------------------------------------------


class TestCancelTask:

    @pytest.mark.asyncio
    async def test_sends_correct_post_request(self):
        resp = _make_mock_response(200, {"task_id": "task-x", "status": "cancelled"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cls:
            result = await worker_client.cancel_task("task-x")

        mock_cls.assert_called_once_with(timeout=10.0)
        mock_client.post.assert_called_once_with(
            f"{FAKE_WORKER_URL}/tasks/task-x/cancel",
            json={},
        )
        assert result == {"task_id": "task-x", "status": "cancelled"}

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_client = _MockAsyncClient(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.cancel_task("task-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        mock_client = _MockAsyncClient(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.cancel_task("task-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_non_2xx(self):
        resp = _make_mock_response(409, {"error": "already cancelled"})
        mock_client = _MockAsyncClient(response=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker_client.cancel_task("task-1")

        assert result is None


# ---------------------------------------------------------------------------
# URL construction — trailing slash normalization
# ---------------------------------------------------------------------------


class TestURLConstruction:

    @pytest.mark.asyncio
    async def test_strips_trailing_slash_from_worker_url(self):
        resp = _make_mock_response(200, {"task_id": "u1"})
        mock_client = _MockAsyncClient(response=resp)

        with patch.object(worker_client.settings, "WORKER_URL", "http://worker:8001/"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await worker_client.trigger_generate_questions("topic")

        url = mock_client.post.call_args[0][0]
        assert url == "http://worker:8001/tasks/generate-questions"
        assert "//" not in url.split("://")[1]

    @pytest.mark.asyncio
    async def test_no_trailing_slash_works(self):
        resp = _make_mock_response(200, {"task_id": "u2"})
        mock_client = _MockAsyncClient(response=resp)

        with patch.object(worker_client.settings, "WORKER_URL", "http://worker:8001"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await worker_client.trigger_generate_questions("topic")

        url = mock_client.post.call_args[0][0]
        assert url == "http://worker:8001/tasks/generate-questions"


# ---------------------------------------------------------------------------
# _is_enabled guard
# ---------------------------------------------------------------------------


class TestIsEnabled:

    @pytest.mark.asyncio
    async def test_empty_string_means_disabled(self):
        with patch.object(worker_client.settings, "WORKER_URL", ""):
            result = await worker_client.trigger_generate_questions("topic")
        assert result is None

    @pytest.mark.asyncio
    async def test_non_empty_string_means_enabled(self):
        resp = _make_mock_response(200, {"task_id": "en1"})
        mock_client = _MockAsyncClient(response=resp)

        with patch.object(worker_client.settings, "WORKER_URL", "http://w:8001"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await worker_client.trigger_generate_questions("topic")

        assert result is not None
