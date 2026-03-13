from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TrainingDataRow(BaseModel):
    """One Q&A pair with full context for training."""
    question_id: UUID = Field(description="UUID of the source question")
    question_title: str = Field(description="Title of the question")
    question_body: str = Field(description="Full body text of the question (Markdown)")
    question_category: Optional[str] = Field(description="Question category label, if assigned")
    question_status: str = Field(description="Current question status (e.g. published, closed)")
    quality_score: Optional[float] = Field(description="Computed quality score for the question, if available")
    source_type: str = Field(description="How the question was created: manual, generated, or extracted")
    answer_id: UUID = Field(description="UUID of the answer")
    answer_body: str = Field(description="Full body text of the answer (Markdown)")
    answer_status: str = Field(description="Current answer status (e.g. approved, submitted)")
    answer_version: int = Field(description="Version number of the answer (increments on revision)")
    selected_option: Optional[str] = Field(description="Body text of the selected answer option, if one was chosen")
    review_verdicts: list[str] = Field(description="List of review verdicts for this answer (e.g. ['approved', 'approved'])")
    created_at: datetime = Field(description="Timestamp when the answer was created")


class EmbeddingRow(BaseModel):
    """Entity embedding for vector operations."""
    entity_type: str = Field(description="Type of entity: 'question' or 'answer'")
    entity_id: UUID = Field(description="UUID of the question or answer")
    embedding: list[float] = Field(description="1024-dimensional embedding vector")


class ReviewPairRow(BaseModel):
    """Answer-review pair for reward modeling / RLHF."""
    answer_id: UUID = Field(description="UUID of the reviewed answer")
    question_id: UUID = Field(description="UUID of the parent question")
    question_title: str = Field(description="Title of the parent question")
    answer_body: str = Field(description="Full body text of the answer (Markdown)")
    answer_version: int = Field(description="Version number of the answer at time of review")
    review_verdict: str = Field(description="Reviewer's verdict: approved, changes_requested, rejected, or superseded")
    review_comment: Optional[str] = Field(description="Optional comment left by the reviewer")
    reviewer_id: UUID = Field(description="UUID of the reviewer")
    created_at: datetime = Field(description="Timestamp when the review was created")
