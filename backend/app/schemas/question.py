import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class ReviewPolicyInput(BaseModel):
    min_approvals: int = Field(default=1, ge=1, le=10)
    auto_assign: bool = False
    auto_assign_count: int = Field(default=1, ge=1, le=10)
    allow_self_review: bool = False


class QuestionCreate(BaseModel):
    title: str = Field(max_length=500)
    body: str
    category: str | None = None
    review_policy: ReviewPolicyInput | None = None
    show_suggestions: bool = False
    source_type: str | None = None
    source_document_id: uuid.UUID | None = None
    source_passage: str | None = None


class QuestionUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    review_policy: ReviewPolicyInput | None = None
    show_suggestions: bool | None = None


class QuestionRejectRequest(BaseModel):
    comment: str | None = None


class AssignRespondentRequest(BaseModel):
    user_id: uuid.UUID


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
    assigned_respondent: UserResponse | None = None
    confirmed_at: datetime | None = None
    published_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    source_type: str | None = None
    source_document_id: uuid.UUID | None = None
    source_passage: str | None = None
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
    approved_count: int = 0
    pending_count: int = 0
    model_config = {"from_attributes": True}


class AdminQueueResponse(BaseModel):
    proposed: list[AdminQueueItem] = []
    in_review: list[AdminQueueItem] = []
    pending: list[AdminQueueItem] = []
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
