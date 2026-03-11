from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TrainingDataRow(BaseModel):
    """One Q&A pair with full context for training."""
    question_id: UUID
    question_title: str
    question_body: str
    question_category: Optional[str]
    question_status: str
    quality_score: Optional[float]
    source_type: str
    answer_id: UUID
    answer_body: str
    answer_status: str
    answer_version: int
    selected_option: Optional[str]
    review_verdicts: list[str]
    created_at: datetime


class EmbeddingRow(BaseModel):
    """Entity embedding for vector operations."""
    entity_type: str  # "question" or "answer"
    entity_id: UUID
    embedding: list[float]


class ReviewPairRow(BaseModel):
    """Answer-review pair for reward modeling / RLHF."""
    answer_id: UUID
    question_id: UUID
    question_title: str
    answer_body: str
    answer_version: int
    review_verdict: str
    review_comment: Optional[str]
    reviewer_id: UUID
    created_at: datetime
