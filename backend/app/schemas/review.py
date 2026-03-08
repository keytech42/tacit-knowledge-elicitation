import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserResponse


class ReviewCreate(BaseModel):
    target_type: str  # "question" or "answer"
    target_id: uuid.UUID


class ReviewUpdate(BaseModel):
    verdict: str  # "approved", "changes_requested", "rejected"
    comment: str | None = None


class ReviewCommentCreate(BaseModel):
    body: str
    parent_id: uuid.UUID | None = None


class ReviewCommentResponse(BaseModel):
    id: uuid.UUID
    review_id: uuid.UUID
    author: UserResponse
    body: str
    parent_id: uuid.UUID | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ReviewResponse(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reviewer: UserResponse
    assigned_by: UserResponse | None = None
    verdict: str
    comment: str | None = None
    answer_version: int | None = None
    question_title: str | None = None
    question_status: str | None = None
    answer_status: str | None = None
    approval_count: int | None = None
    min_approvals: int | None = None
    comments: list[ReviewCommentResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
