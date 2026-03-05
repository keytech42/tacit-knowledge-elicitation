"""Embedding generation via litellm (provider-agnostic).

Requires EMBEDDING_MODEL to be set to a non-empty value to be active.
Anthropic does not offer embeddings — use OpenAI (text-embedding-3-small)
or Voyage AI (voyage/voyage-3) models. The corresponding API key
(OPENAI_API_KEY or VOYAGE_API_KEY) must be set.
"""
import logging

import litellm
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.answer import Answer
from app.models.question import Question

logger = logging.getLogger(__name__)


def _embeddings_enabled() -> bool:
    return bool(settings.EMBEDDING_MODEL)


async def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    response = await litellm.aembedding(
        model=settings.EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0]["embedding"]


async def update_question_embedding(db: AsyncSession, question: Question) -> None:
    """Generate and store embedding for a question."""
    if not _embeddings_enabled():
        return
    try:
        text = f"{question.title}\n{question.body}"
        question.embedding = await generate_embedding(text)
    except Exception:
        logger.warning(f"Failed to generate embedding for question {question.id} — skipping")


async def update_answer_embedding(db: AsyncSession, answer: Answer) -> None:
    """Generate and store embedding for an answer."""
    if not _embeddings_enabled():
        return
    try:
        answer.embedding = await generate_embedding(answer.body)
    except Exception:
        logger.warning(f"Failed to generate embedding for answer {answer.id} — skipping")
