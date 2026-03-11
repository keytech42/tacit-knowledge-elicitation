"""Fire-and-forget HTTP calls to the LLM worker service.

All calls are wrapped in try/except so worker downtime never blocks the main API.
"""
import logging
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return bool(settings.WORKER_URL)


async def _post(path: str, payload: dict) -> dict | None:
    if not _is_enabled():
        return None
    url = f"{settings.WORKER_URL.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception(f"Worker call failed: POST {path}")
        return None


async def _get(path: str) -> dict | None:
    if not _is_enabled():
        return None
    url = f"{settings.WORKER_URL.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception(f"Worker call failed: GET {path}")
        return None


async def trigger_generate_questions(
    topic: str, domain: str = "", count: int = 3, context: str | None = None,
) -> dict | None:
    payload = {"topic": topic, "domain": domain, "count": count}
    if context:
        payload["context"] = context
    return await _post("/tasks/generate-questions", payload)


async def trigger_scaffold_options(question_id: uuid.UUID, num_options: int = 4) -> dict | None:
    return await _post("/tasks/scaffold-options", {
        "question_id": str(question_id),
        "num_options": num_options,
    })


async def trigger_review_assist(answer_id: uuid.UUID) -> dict | None:
    return await _post("/tasks/review-assist", {
        "answer_id": str(answer_id),
    })


async def trigger_extract_questions(
    source_text: str,
    document_title: str = "",
    domain: str = "",
    max_questions: int = 10,
    source_document_id: str | None = None,
) -> dict | None:
    payload = {
        "source_text": source_text,
        "document_title": document_title,
        "domain": domain,
        "max_questions": max_questions,
    }
    if source_document_id:
        payload["source_document_id"] = source_document_id
    return await _post("/tasks/extract-questions", payload)


async def trigger_recommend(
    question: dict, candidates: list[dict], top_k: int = 5,
) -> dict | None:
    """Synchronous call to worker for LLM-based recommendation (longer timeout)."""
    if not _is_enabled():
        return None
    url = f"{settings.WORKER_URL.rstrip('/')}/tasks/recommend"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json={
                "question": question,
                "candidates": candidates,
                "top_k": top_k,
            })
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("Worker call failed: POST /tasks/recommend")
        return None


async def get_task_status(task_id: str) -> dict | None:
    return await _get(f"/tasks/{task_id}")


async def cancel_task(task_id: str) -> dict | None:
    """Cancel a running task on the worker."""
    return await _post(f"/tasks/{task_id}/cancel", {})
