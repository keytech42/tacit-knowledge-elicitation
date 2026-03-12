import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class RespondentPoolRequest(BaseModel):
    user_ids: list[uuid.UUID]
    expected_version: int


class RespondentPoolMember(BaseModel):
    id: uuid.UUID
    user: UserResponse
    created_at: datetime
    model_config = {"from_attributes": True}


class RespondentPoolResponse(BaseModel):
    respondents: list[RespondentPoolMember]
    version: int


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
    assigned_respondents: list[RespondentPoolMember] = []
    respondent_pool_version: int = 0
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


# --- Import/Export schemas ---


class AnswerOptionExport(BaseModel):
    body: str
    display_order: int


class QuestionExportMetadata(BaseModel):
    id: str
    status: str
    source_type: str
    created_by: str | None = None
    created_at: str | None = None
    quality_score: float | None = None
    answer_count: int = 0
    approved_answer_count: int = 0


class QuestionExportItem(BaseModel):
    title: str
    body: str
    category: str | None = None
    review_policy: dict | None = None
    show_suggestions: bool = False
    answer_options: list[AnswerOptionExport] = []
    metadata_: QuestionExportMetadata | None = Field(alias="_metadata", default=None)

    model_config = ConfigDict(populate_by_name=True)


class QuestionExportEnvelope(BaseModel):
    version: str = "1.0"
    exported_at: str
    questions: list[QuestionExportItem]


class QuestionImportItem(BaseModel):
    title: str = Field(..., max_length=500)
    body: str = Field(..., min_length=1)
    category: str | None = Field(None, max_length=255)
    review_policy: dict | None = None
    show_suggestions: bool = False
    answer_options: list[AnswerOptionExport] = []

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be empty")
        return v

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body must not be empty")
        return v

    @field_validator("review_policy")
    @classmethod
    def validate_review_policy(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        if not isinstance(v.get("min_approvals", 1), int):
            raise ValueError("review_policy.min_approvals must be an integer")
        ma = v.get("min_approvals", 1)
        if not (1 <= ma <= 10):
            raise ValueError("review_policy.min_approvals must be between 1 and 10")
        return v

    @field_validator("answer_options")
    @classmethod
    def unique_display_order(cls, v: list[AnswerOptionExport]) -> list[AnswerOptionExport]:
        orders = [opt.display_order for opt in v]
        if len(orders) != len(set(orders)):
            raise ValueError("duplicate display_order in answer options")
        return v


class QuestionImportRequest(BaseModel):
    version: str = "1.0"
    questions: list[QuestionImportItem] = Field(..., min_length=1, max_length=500)

    @field_validator("version")
    @classmethod
    def supported_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"Unsupported schema version '{v}'. Expected '1.0'")
        return v


class QuestionImportResponse(BaseModel):
    created: int
    question_ids: list[str]
