import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class QuestionCreate(BaseModel):
    title: str = Field(max_length=500)
    body: str
    category: str | None = None
    review_policy: dict | None = None
    show_suggestions: bool = False


class QuestionUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    review_policy: dict | None = None
    show_suggestions: bool | None = None


class QuestionRejectRequest(BaseModel):
    comment: str | None = None


class AnswerOptionResponse(BaseModel):
    id: uuid.UUID
    body: str
    display_order: int
    created_by: UserResponse
    created_at: datetime
    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    category: str | None = None
    status: str
    confirmation: str
    review_policy: dict | None = None
    show_suggestions: bool
    quality_score: float | None = None
    created_by: UserResponse
    confirmed_by: UserResponse | None = None
    confirmed_at: datetime | None = None
    published_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    answer_options: list[AnswerOptionResponse] = []
    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    questions: list[QuestionResponse]
    total: int


class AdminQueueItem(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    category: str | None = None
    status: str
    quality_score: float | None = None
    created_by: UserResponse
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    answer_count: int = 0
    model_config = {"from_attributes": True}


class AdminQueueResponse(BaseModel):
    proposed: list[AdminQueueItem] = []
    in_review: list[AdminQueueItem] = []
    published: list[AdminQueueItem] = []
    closed: list[AdminQueueItem] = []


class AnswerOptionCreate(BaseModel):
    body: str
    display_order: int = 0


class AnswerOptionBatchCreate(BaseModel):
    options: list[AnswerOptionCreate]


class QualityFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class QualityFeedbackResponse(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    user: UserResponse
    rating: int
    comment: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}
