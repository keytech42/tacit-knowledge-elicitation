import uuid
from typing import Literal

from pydantic import BaseModel, Field


# --- LLM output schemas ---

class GeneratedQuestion(BaseModel):
    title: str
    body: str
    category: str
    suggested_options: list[str] = []


class GeneratedQuestionSet(BaseModel):
    questions: list[GeneratedQuestion]


class ScaffoldedOption(BaseModel):
    body: str
    display_order: int


class ScaffoldedOptionSet(BaseModel):
    options: list[ScaffoldedOption]


class ReviewAssessment(BaseModel):
    verdict: Literal["approved", "changes_requested"]
    comment: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


# --- Task request/response schemas ---

class GenerateQuestionsRequest(BaseModel):
    topic: str
    domain: str = ""
    count: int = 3
    context: str | None = None


class ScaffoldOptionsRequest(BaseModel):
    question_id: uuid.UUID
    num_options: int = 4


class ReviewAssistRequest(BaseModel):
    answer_id: uuid.UUID


class ExtractedQuestion(BaseModel):
    title: str
    body: str
    category: str
    source_passage: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_options: list[str] = []


class ExtractedQuestionSet(BaseModel):
    questions: list[ExtractedQuestion]
    document_summary: str


class ExtractQuestionsRequest(BaseModel):
    source_text: str
    document_title: str = ""
    domain: str = ""
    max_questions: int = 10
    source_document_id: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # accepted, running, completed, failed
    result: dict | None = None
    error: str | None = None
