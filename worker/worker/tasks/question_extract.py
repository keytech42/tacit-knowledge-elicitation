import logging
import uuid

from worker.config import settings
from worker.llm import call_llm
from worker.platform_client import platform
from worker.prompts.question_extract import (
    CONSOLIDATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_consolidation_prompt,
    build_extraction_prompt,
)
from worker.schemas import ExtractedQuestionSet

logger = logging.getLogger(__name__)

CHUNK_MAX_CHARS = 4000


def _chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split text on paragraph boundaries, keeping chunks under max_chars."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


async def run_question_extraction(
    source_text: str,
    document_title: str = "",
    domain: str = "",
    max_questions: int = 10,
    source_document_id: str | None = None,
) -> dict:
    """Extract knowledge elicitation questions from a source document via LLM."""
    existing_questions = await platform.get_questions()
    chunks = _chunk_text(source_text)
    logger.info(f"Document split into {len(chunks)} chunks")

    all_candidates = []
    doc_summary = ""

    # Pass 1: Extract from each chunk
    for i, chunk in enumerate(chunks):
        user_prompt = build_extraction_prompt(
            chunk=chunk,
            domain=domain,
            existing_questions=existing_questions,
            chunk_index=i + 1,
            total_chunks=len(chunks),
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        result = await call_llm(
            messages, ExtractedQuestionSet, temperature=settings.EXTRACTION_TEMPERATURE,
        )
        all_candidates.extend(result.questions)
        if not doc_summary and result.document_summary:
            doc_summary = result.document_summary

    logger.info(f"Extracted {len(all_candidates)} candidates from {len(chunks)} chunks")

    # Pass 2: Consolidation (only if multiple chunks or too many candidates)
    if len(chunks) > 1 or len(all_candidates) > max_questions:
        user_prompt = build_consolidation_prompt(
            candidates=all_candidates,
            max_questions=max_questions,
            existing_questions=existing_questions,
        )
        messages = [
            {"role": "system", "content": CONSOLIDATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        consolidated = await call_llm(
            messages, ExtractedQuestionSet, temperature=settings.EXTRACTION_TEMPERATURE,
        )
        final_questions = consolidated.questions[:max_questions]
        if consolidated.document_summary:
            doc_summary = consolidated.document_summary
    else:
        final_questions = all_candidates[:max_questions]

    # Create questions on platform
    created_ids: list[str] = []
    for eq in final_questions:
        try:
            question = await platform.create_question(
                title=eq.title,
                body=eq.body,
                category=eq.category,
                source_type="extracted",
                source_document_id=source_document_id,
                source_passage=eq.source_passage,
            )
            question_id = question["id"]
            created_ids.append(question_id)

            # Auto-submit if configured
            if settings.EXTRACTION_AUTO_SUBMIT:
                await platform.submit_question(uuid.UUID(question_id))

            # Create answer options if any
            if eq.suggested_options:
                options = [
                    {"body": opt, "display_order": i}
                    for i, opt in enumerate(eq.suggested_options)
                ]
                await platform.create_answer_options(uuid.UUID(question_id), options)

            logger.info(f"Created question: {eq.title}")
        except Exception:
            logger.exception(f"Failed to create question: {eq.title}")

    # Update source document with summary and count
    if source_document_id:
        try:
            await platform.update_source_document(
                source_document_id,
                summary=doc_summary,
                question_count=len(created_ids),
            )
        except Exception:
            logger.exception("Failed to update source document")

    return {
        "created_question_ids": created_ids,
        "count": len(created_ids),
        "document_summary": doc_summary,
    }
