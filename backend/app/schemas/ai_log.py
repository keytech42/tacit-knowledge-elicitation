import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class AILogFeedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class AILogResponse(BaseModel):
    id: uuid.UUID
    service_user: UserResponse
    model_id: str | None = None
    endpoint: str
    request_body: dict | None = None
    response_status: int
    created_entity_type: str | None = None
    created_entity_id: uuid.UUID | None = None
    latency_ms: int | None = None
    token_usage: dict | None = None
    feedback_rating: int | None = None
    feedback_comment: str | None = None
    feedback_by: UserResponse | None = None
    feedback_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AILogListResponse(BaseModel):
    logs: list[AILogResponse]
    total: int
