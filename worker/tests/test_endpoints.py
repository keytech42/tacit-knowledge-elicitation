"""Contract tests for all worker FastAPI endpoints via real HTTP transport.

Mocks only litellm (call_llm) and platform_client (platform) at the boundary.
"""

import asyncio
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from worker.schemas import (
    GeneratedQuestion,
    GeneratedQuestionSet,
    ScaffoldedOption,
    ScaffoldedOptionSet,
    ReviewAssessment,
    ExtractedQuestion,
    ExtractedQuestionSet,
    RecommendationResult,
    RecommendedRespondent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

QUESTION_ID = str(uuid.uuid4())
ANSWER_ID = str(uuid.uuid4())
REVIEW_ID = str(uuid.uuid4())


def _fake_question(qid: str = QUESTION_ID) -> dict:
    return {
        "id": qid,
        "title": "Test question",
        "body": "What is testing?",
        "category": "engineering",
        "status": "published",
    }


def _fake_answer(aid: str = ANSWER_ID, qid: str = QUESTION_ID) -> dict:
    return {
        "id": aid,
        "question_id": qid,
        "body": "Testing is important.",
        "status": "submitted",
    }


def _fake_review(rid: str = REVIEW_ID) -> dict:
    return {"id": rid, "verdict": "pending"}


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /tasks/generate-questions
# ---------------------------------------------------------------------------


class TestGenerateQuestions:
    @pytest.mark.asyncio
    async def test_trigger_returns_202_with_task_id(self, client):
        mock_llm = AsyncMock(return_value=GeneratedQuestionSet(questions=[
            GeneratedQuestion(title="Q1", body="Body", category="cat"),
        ]))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=["cat"])
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-1"})
        mock_platform.submit_question = AsyncMock(return_value={})

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "testing",
                "domain": "engineering",
                "count": 1,
            })

        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_task_completes_successfully(self, client):
        mock_llm = AsyncMock(return_value=GeneratedQuestionSet(questions=[
            GeneratedQuestion(title="Q1", body="Body", category="cat"),
        ]))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=[])
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-1"})
        mock_platform.submit_question = AsyncMock(return_value={})

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "testing",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "completed"
        assert status_data["result"]["count"] == 1
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_marks_task_failed(self, client):
        mock_llm = AsyncMock(side_effect=RuntimeError("LLM unreachable"))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=[])
        mock_platform.get_questions = AsyncMock(return_value=[])

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "testing",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "failed"
        assert "LLM unreachable" in status_resp.json()["error"]

    @pytest.mark.asyncio
    async def test_platform_failure_marks_task_failed(self, client):
        mock_llm = AsyncMock(return_value=GeneratedQuestionSet(questions=[]))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(side_effect=Exception("Platform down"))
        mock_platform.get_questions = AsyncMock(return_value=[])

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "testing",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "failed"
        assert "Platform down" in status_resp.json()["error"]


# ---------------------------------------------------------------------------
# POST /tasks/scaffold-options
# ---------------------------------------------------------------------------


class TestScaffoldOptions:
    @pytest.mark.asyncio
    async def test_trigger_returns_202(self, client):
        mock_llm = AsyncMock(return_value=ScaffoldedOptionSet(options=[
            ScaffoldedOption(body="Option A", display_order=1),
            ScaffoldedOption(body="Option B", display_order=2),
        ]))
        mock_platform = MagicMock()
        mock_platform.get_question = AsyncMock(return_value=_fake_question())
        mock_platform.delete_answer_options = AsyncMock()
        mock_platform.create_answer_options = AsyncMock(return_value=[{}, {}])
        mock_platform.update_question = AsyncMock(return_value={})

        with patch("worker.tasks.answer_scaffold.call_llm", mock_llm), \
             patch("worker.tasks.answer_scaffold.platform", mock_platform):
            resp = await client.post("/tasks/scaffold-options", json={
                "question_id": QUESTION_ID,
                "num_options": 2,
            })

        assert resp.status_code == 202
        assert "task_id" in resp.json()

    @pytest.mark.asyncio
    async def test_scaffold_completes_and_calls_platform(self, client):
        mock_llm = AsyncMock(return_value=ScaffoldedOptionSet(options=[
            ScaffoldedOption(body="Option A", display_order=1),
        ]))
        mock_platform = MagicMock()
        mock_platform.get_question = AsyncMock(return_value=_fake_question())
        mock_platform.delete_answer_options = AsyncMock()
        mock_platform.create_answer_options = AsyncMock(return_value=[{}])
        mock_platform.update_question = AsyncMock(return_value={})

        with patch("worker.tasks.answer_scaffold.call_llm", mock_llm), \
             patch("worker.tasks.answer_scaffold.platform", mock_platform):
            resp = await client.post("/tasks/scaffold-options", json={
                "question_id": QUESTION_ID,
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "completed"
        mock_platform.get_question.assert_called_once()
        mock_platform.delete_answer_options.assert_called_once()
        mock_platform.create_answer_options.assert_called_once()
        mock_platform.update_question.assert_called_once()


# ---------------------------------------------------------------------------
# POST /tasks/review-assist
# ---------------------------------------------------------------------------


class TestReviewAssist:
    @pytest.mark.asyncio
    async def test_trigger_returns_202(self, client):
        mock_llm = AsyncMock(return_value=ReviewAssessment(
            verdict="approved",
            comment="Good answer",
            strengths=["clear"],
            weaknesses=[],
            suggestions=[],
            confidence=0.8,
        ))
        mock_platform = MagicMock()
        mock_platform.get_answer = AsyncMock(return_value=_fake_answer())
        mock_platform.get_question = AsyncMock(return_value=_fake_question())
        mock_platform.create_review = AsyncMock(return_value=_fake_review())
        mock_platform.submit_review_verdict = AsyncMock(return_value={})

        with patch("worker.tasks.review_assist.call_llm", mock_llm), \
             patch("worker.tasks.review_assist.platform", mock_platform):
            resp = await client.post("/tasks/review-assist", json={
                "answer_id": ANSWER_ID,
            })

        assert resp.status_code == 202
        assert "task_id" in resp.json()

    @pytest.mark.asyncio
    async def test_high_confidence_submits_review(self, client):
        mock_llm = AsyncMock(return_value=ReviewAssessment(
            verdict="approved",
            comment="Good answer",
            strengths=["clear"],
            weaknesses=[],
            suggestions=[],
            confidence=0.85,
        ))
        mock_platform = MagicMock()
        mock_platform.get_answer = AsyncMock(return_value=_fake_answer())
        mock_platform.get_question = AsyncMock(return_value=_fake_question())
        mock_platform.create_review = AsyncMock(return_value=_fake_review())
        mock_platform.submit_review_verdict = AsyncMock(return_value={})

        with patch("worker.tasks.review_assist.call_llm", mock_llm), \
             patch("worker.tasks.review_assist.platform", mock_platform):
            resp = await client.post("/tasks/review-assist", json={
                "answer_id": ANSWER_ID,
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        result = status_resp.json()["result"]
        assert result["submitted"] is True
        assert result["verdict"] == "approved"
        mock_platform.submit_review_verdict.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_confidence_skips_submission(self, client):
        mock_llm = AsyncMock(return_value=ReviewAssessment(
            verdict="changes_requested",
            comment="Not sure",
            strengths=[],
            weaknesses=["unclear"],
            suggestions=["rewrite"],
            confidence=0.4,
        ))
        mock_platform = MagicMock()
        mock_platform.get_answer = AsyncMock(return_value=_fake_answer())
        mock_platform.get_question = AsyncMock(return_value=_fake_question())

        with patch("worker.tasks.review_assist.call_llm", mock_llm), \
             patch("worker.tasks.review_assist.platform", mock_platform):
            resp = await client.post("/tasks/review-assist", json={
                "answer_id": ANSWER_ID,
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        result = status_resp.json()["result"]
        assert result["submitted"] is False
        assert "confidence below threshold" in result["reason"]
        mock_platform.create_review = AsyncMock()
        # create_review should NOT have been called for low confidence
        # (it's only called after the confidence check passes)


# ---------------------------------------------------------------------------
# POST /tasks/extract-questions
# ---------------------------------------------------------------------------


class TestExtractQuestions:
    @pytest.mark.asyncio
    async def test_trigger_returns_202(self, client):
        mock_llm = AsyncMock(return_value=ExtractedQuestionSet(
            questions=[
                ExtractedQuestion(
                    title="EQ1", body="Body", category="cat",
                    source_passage="passage", confidence=0.9,
                ),
            ],
            document_summary="Summary",
        ))
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-1"})
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            resp = await client.post("/tasks/extract-questions", json={
                "source_text": "Some document content.",
                "document_title": "Test Doc",
            })

        assert resp.status_code == 202
        assert "task_id" in resp.json()

    @pytest.mark.asyncio
    async def test_extraction_completes_with_results(self, client):
        mock_llm = AsyncMock(return_value=ExtractedQuestionSet(
            questions=[
                ExtractedQuestion(
                    title="EQ1", body="Body", category="cat",
                    source_passage="passage", confidence=0.9,
                ),
            ],
            document_summary="Summary",
        ))
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(return_value=[])
        mock_platform.create_question = AsyncMock(return_value={"id": "q-1"})
        mock_platform.update_source_document = AsyncMock()

        with patch("worker.tasks.question_extract.call_llm", mock_llm), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            resp = await client.post("/tasks/extract-questions", json={
                "source_text": "Short doc.",
                "source_document_id": "doc-1",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "completed"
        assert status_resp.json()["result"]["count"] == 1


# ---------------------------------------------------------------------------
# POST /tasks/recommend (synchronous)
# ---------------------------------------------------------------------------


class TestRecommend:
    @pytest.mark.asyncio
    async def test_returns_200_with_items(self, client):
        mock_result = RecommendationResult(respondents=[
            RecommendedRespondent(user_id="u-1", score=0.9, reasoning="Expert"),
        ])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result):
            resp = await client.post("/tasks/recommend", json={
                "question": {"title": "Q", "body": "B", "category": "c"},
                "candidates": [
                    {"user_id": "u-1", "display_name": "Alice", "answer_summaries": []},
                ],
                "top_k": 5,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["user_id"] == "u-1"
        assert data["items"][0]["display_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self, client):
        resp = await client.post("/tasks/recommend", json={
            "question": {"title": "Q", "body": "B"},
            "candidates": [],
            "top_k": 5,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_recommend_is_synchronous_no_task_id(self, client):
        """Recommend returns results directly, no task_id in response."""
        mock_result = RecommendationResult(respondents=[])

        with patch("worker.tasks.respondent_recommend.call_llm", new_callable=AsyncMock, return_value=mock_result):
            resp = await client.post("/tasks/recommend", json={
                "question": {"title": "Q", "body": "B"},
                "candidates": [
                    {"user_id": "u-1", "display_name": "A", "answer_summaries": []},
                ],
            })

        assert resp.status_code == 200
        assert "task_id" not in resp.json()


# ---------------------------------------------------------------------------
# GET /tasks/{task_id} — task lifecycle
# ---------------------------------------------------------------------------


class TestTaskLifecycle:
    @pytest.mark.asyncio
    async def test_get_unknown_task_returns_404(self, client):
        resp = await client.get(f"/tasks/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_task_status_transitions(self, client):
        """Task goes from accepted -> running -> completed."""
        mock_llm = AsyncMock(return_value=GeneratedQuestionSet(questions=[]))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=[])
        mock_platform.get_questions = AsyncMock(return_value=[])

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "test",
            })
            task_id = resp.json()["task_id"]

            # Immediately after POST, status should be accepted or running
            status_resp = await client.get(f"/tasks/{task_id}")
            assert status_resp.json()["status"] in ("accepted", "running")

            await asyncio.sleep(0.2)

            # After task finishes
            status_resp = await client.get(f"/tasks/{task_id}")
            assert status_resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# POST /tasks/{task_id}/cancel
# ---------------------------------------------------------------------------


class TestCancelTask:
    @pytest.mark.asyncio
    async def test_cancel_pending_task(self, client):
        """Cancelling a task in accepted/running state returns 200."""
        # Use a slow coroutine so the task stays in running state
        async def _slow_task(*args, **kwargs):
            await asyncio.sleep(10)
            return {}

        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=[])
        mock_platform.get_questions = AsyncMock(return_value=[])

        with patch("worker.tasks.question_gen.call_llm", AsyncMock(side_effect=_slow_task)), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "test",
            })
            task_id = resp.json()["task_id"]
            # Give event loop a tick so the task starts
            await asyncio.sleep(0.05)

            cancel_resp = await client.post(f"/tasks/{task_id}/cancel")

        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_task_returns_409(self, client):
        mock_llm = AsyncMock(return_value=GeneratedQuestionSet(questions=[]))
        mock_platform = MagicMock()
        mock_platform.get_categories = AsyncMock(return_value=[])
        mock_platform.get_questions = AsyncMock(return_value=[])

        with patch("worker.tasks.question_gen.call_llm", mock_llm), \
             patch("worker.tasks.question_gen.platform", mock_platform):
            resp = await client.post("/tasks/generate-questions", json={
                "topic": "test",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            cancel_resp = await client.post(f"/tasks/{task_id}/cancel")

        assert cancel_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_unknown_task_returns_404(self, client):
        resp = await client.post(f"/tasks/{uuid.uuid4()}/cancel")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error paths — failures propagate to task status
# ---------------------------------------------------------------------------


class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_scaffold_platform_error_marks_failed(self, client):
        mock_platform = MagicMock()
        mock_platform.get_question = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("worker.tasks.answer_scaffold.call_llm", AsyncMock()), \
             patch("worker.tasks.answer_scaffold.platform", mock_platform):
            resp = await client.post("/tasks/scaffold-options", json={
                "question_id": QUESTION_ID,
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "failed"
        assert "Connection refused" in status_resp.json()["error"]

    @pytest.mark.asyncio
    async def test_review_assist_llm_error_marks_failed(self, client):
        mock_platform = MagicMock()
        mock_platform.get_answer = AsyncMock(return_value=_fake_answer())
        mock_platform.get_question = AsyncMock(return_value=_fake_question())

        with patch("worker.tasks.review_assist.call_llm", AsyncMock(side_effect=RuntimeError("Model overloaded"))), \
             patch("worker.tasks.review_assist.platform", mock_platform):
            resp = await client.post("/tasks/review-assist", json={
                "answer_id": ANSWER_ID,
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "failed"
        assert "Model overloaded" in status_resp.json()["error"]

    @pytest.mark.asyncio
    async def test_extract_platform_error_marks_failed(self, client):
        mock_platform = MagicMock()
        mock_platform.get_questions = AsyncMock(side_effect=Exception("Timeout"))

        with patch("worker.tasks.question_extract.call_llm", AsyncMock()), \
             patch("worker.tasks.question_extract.platform", mock_platform):
            resp = await client.post("/tasks/extract-questions", json={
                "source_text": "Content",
            })
            task_id = resp.json()["task_id"]
            await asyncio.sleep(0.2)

            status_resp = await client.get(f"/tasks/{task_id}")

        assert status_resp.json()["status"] == "failed"
        assert "Timeout" in status_resp.json()["error"]
