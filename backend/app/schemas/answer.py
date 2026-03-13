import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserResponse


class AnswerCreate(BaseModel):
    body: str
    selected_option_id: uuid.UUID | None = None


class AnswerUpdate(BaseModel):
    body: str | None = None
    selected_option_id: uuid.UUID | None = None


class AnswerRevisionResponse(BaseModel):
    id: uuid.UUID
    answer_id: uuid.UUID
    version: int
    body: str
    selected_option_id: uuid.UUID | None = None
    created_by: UserResponse
    trigger: str
    previous_status: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    author: UserResponse
    body: str
    selected_option_id: uuid.UUID | None = None
    status: str
    current_version: int
    confirmed_by: UserResponse | None = None
    confirmed_at: datetime | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AnswerListResponse(BaseModel):
    answers: list[AnswerResponse]
    total: int


class AnswerDiffResponse(BaseModel):
    from_version: int
    to_version: int
    diff: str
    from_created_at: datetime
    to_created_at: datetime


class StagingDiffResponse(BaseModel):
    has_changes: bool
    latest_version: int | None = None
    diff: str | None = None


class CollaboratorAdd(BaseModel):
    user_id: uuid.UUID


class CollaboratorResponse(BaseModel):
    id: uuid.UUID
    answer_id: uuid.UUID
    user: UserResponse
    granted_by: UserResponse
    created_at: datetime
    model_config = {"from_attributes": True}


class ActivityEventResponse(BaseModel):
    type: str  # "version_submitted" | "reviewer_assigned" | "review_submitted"
    timestamp: datetime
    # Version event fields
    actor: UserResponse | None = None
    version: int | None = None
    trigger: str | None = None
    diff: str | None = None
    # Review event fields
    review_id: uuid.UUID | None = None
    reviewer: UserResponse | None = None
    assigned_by: UserResponse | None = None
    verdict: str | None = None
    comment: str | None = None
    answer_version: int | None = None
    is_stale: bool | None = None
    self_assigned: bool | None = None
    model_config = {"from_attributes": True}


class ActivityTimelineResponse(BaseModel):
    events: list[ActivityEventResponse]
    current_version: int
    answer_status: str
