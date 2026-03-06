"""Embedding generation via litellm (provider-agnostic).

Supports three deployment modes:
  - Local llama.cpp / TEI: EMBEDDING_MODEL="openai/bge-m3", EMBEDDING_API_BASE="http://host.docker.internal:8090/v1/"
  - Cloud (OpenAI):        EMBEDDING_MODEL="text-embedding-3-small", OPENAI_API_KEY="sk-..."
  - Cloud (Cohere):        EMBEDDING_MODEL="cohere/embed-v4.0", COHERE_API_KEY="..."

Requires EMBEDDING_MODEL to be set to a non-empty value to be active.
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


def _embedding_kwargs() -> dict:
    """Build extra kwargs for litellm.aembedding based on config."""
    kwargs: dict = {}
    if settings.EMBEDDING_API_BASE:
        kwargs["api_base"] = settings.EMBEDDING_API_BASE
    if settings.EMBEDDING_API_KEY:
        kwargs["api_key"] = settings.EMBEDDING_API_KEY
    return kwargs


async def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    response = await litellm.aembedding(
        model=settings.EMBEDDING_MODEL,
        input=[text],
        **_embedding_kwargs(),
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
