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


class CollaboratorAdd(BaseModel):
    user_id: uuid.UUID


class CollaboratorResponse(BaseModel):
    id: uuid.UUID
    answer_id: uuid.UUID
    user: UserResponse
    granted_by: UserResponse
    created_at: datetime
    model_config = {"from_attributes": True}
