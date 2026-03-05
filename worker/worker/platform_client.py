import uuid
import logging

import httpx

from worker.config import settings

logger = logging.getLogger(__name__)


class PlatformClient:
    """Async HTTP client for the platform REST API, authenticating as a service account."""

    def __init__(self):
        self._base_url = settings.PLATFORM_API_URL.rstrip("/")
        self._headers = {"X-API-Key": settings.PLATFORM_API_KEY}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=30.0,
        )

    async def get_question(self, question_id: uuid.UUID) -> dict:
        async with self._client() as client:
            resp = await client.get(f"/api/v1/questions/{question_id}")
            resp.raise_for_status()
            return resp.json()

    async def get_questions(self, status: str | None = None, category: str | None = None) -> list[dict]:
        params = {}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        async with self._client() as client:
            resp = await client.get("/api/v1/questions", params=params)
            resp.raise_for_status()
            return resp.json()["questions"]

    async def create_question(self, title: str, body: str, category: str | None = None) -> dict:
        payload = {"title": title, "body": body}
        if category:
            payload["category"] = category
        async with self._client() as client:
            resp = await client.post("/api/v1/questions", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def submit_question(self, question_id: uuid.UUID) -> dict:
        async with self._client() as client:
            resp = await client.post(f"/api/v1/questions/{question_id}/submit")
            resp.raise_for_status()
            return resp.json()

    async def update_question(self, question_id: uuid.UUID, data: dict) -> dict:
        async with self._client() as client:
            resp = await client.patch(f"/api/v1/questions/{question_id}", json=data)
            resp.raise_for_status()
            return resp.json()

    async def create_answer_options(self, question_id: uuid.UUID, options: list[dict]) -> list[dict]:
        async with self._client() as client:
            resp = await client.post(
                f"/api/v1/questions/{question_id}/options",
                json={"options": options},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_answer(self, answer_id: uuid.UUID) -> dict:
        async with self._client() as client:
            resp = await client.get(f"/api/v1/answers/{answer_id}")
            resp.raise_for_status()
            return resp.json()

    async def create_review(self, target_type: str, target_id: uuid.UUID) -> dict:
        async with self._client() as client:
            resp = await client.post(
                "/api/v1/reviews",
                json={"target_type": target_type, "target_id": str(target_id)},
            )
            resp.raise_for_status()
            return resp.json()

    async def submit_review_verdict(self, review_id: uuid.UUID, verdict: str, comment: str) -> dict:
        async with self._client() as client:
            resp = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": verdict, "comment": comment},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_categories(self) -> list[str]:
        async with self._client() as client:
            resp = await client.get("/api/v1/questions/categories")
            resp.raise_for_status()
            return resp.json()

    async def delete_answer_options(self, question_id: uuid.UUID) -> None:
        async with self._client() as client:
            resp = await client.delete(f"/api/v1/questions/{question_id}/options")
            resp.raise_for_status()

    async def get_answer_options(self, question_id: uuid.UUID) -> list[dict]:
        async with self._client() as client:
            resp = await client.get(f"/api/v1/questions/{question_id}/options")
            resp.raise_for_status()
            return resp.json()


platform = PlatformClient()
