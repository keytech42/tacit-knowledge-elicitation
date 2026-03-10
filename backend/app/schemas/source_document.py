import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserResponse


class SourceDocumentCreate(BaseModel):
    title: str
    body: str
    domain: str | None = None


class SourceDocumentUpdate(BaseModel):
    document_summary: str | None = None
    question_count: int | None = None


class SourceDocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    domain: str | None = None
    document_summary: str | None = None
    uploaded_by: UserResponse
    question_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class SourceDocumentDetailResponse(SourceDocumentResponse):
    body: str


class SourceDocumentListResponse(BaseModel):
    items: list[SourceDocumentResponse]
    total: int
