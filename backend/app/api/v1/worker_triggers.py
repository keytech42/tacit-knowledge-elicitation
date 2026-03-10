import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.database import get_db
from app.models.user import RoleName, User
from app.services import worker_client
from app.services.recommendation import recommend_respondents

router = APIRouter(prefix="/ai", tags=["ai"])


class GenerateQuestionsRequest(BaseModel):
    topic: str
    domain: str = ""
    count: int = 3
    context: str | None = None


class ScaffoldOptionsRequest(BaseModel):
    question_id: uuid.UUID
    num_options: int = 4

    def capped_options(self) -> int:
        return min(self.num_options, 4)


class ReviewAssistRequest(BaseModel):
    answer_id: uuid.UUID


class RecommendRequest(BaseModel):
    question_id: uuid.UUID
    top_k: int = 5


class RecommendationItem(BaseModel):
    user_id: str
    display_name: str
    score: float
    reasoning: str


class RecommendationResponse(BaseModel):
    items: list[RecommendationItem]
    reason: str | None = None
    strategy: str | None = None


class TaskAcceptedResponse(BaseModel):
    task_id: str
    status: str


def _require_worker():
    if not settings.WORKER_URL:
        raise HTTPException(status_code=503, detail="Worker service not configured")


@router.post("/generate-questions", response_model=TaskAcceptedResponse)
async def generate_questions(
    request: GenerateQuestionsRequest,
    admin: User = require_role(RoleName.ADMIN),
):
    _require_worker()
    result = await worker_client.trigger_generate_questions(
        topic=request.topic,
        domain=request.domain,
        count=request.count,
        context=request.context,
    )
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return TaskAcceptedResponse(task_id=result["task_id"], status=result["status"])


@router.post("/scaffold-options", response_model=TaskAcceptedResponse)
async def scaffold_options(
    request: ScaffoldOptionsRequest,
    admin: User = require_role(RoleName.ADMIN),
):
    _require_worker()
    result = await worker_client.trigger_scaffold_options(
        question_id=request.question_id,
        num_options=request.capped_options(),
    )
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return TaskAcceptedResponse(task_id=result["task_id"], status=result["status"])


@router.post("/review-assist", response_model=TaskAcceptedResponse)
async def review_assist(
    request: ReviewAssistRequest,
    admin: User = require_role(RoleName.ADMIN),
):
    _require_worker()
    result = await worker_client.trigger_review_assist(
        answer_id=request.answer_id,
    )
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return TaskAcceptedResponse(task_id=result["task_id"], status=result["status"])


@router.post("/recommend", response_model=RecommendationResponse)
async def recommend(
    request: RecommendRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await recommend_respondents(db, request.question_id, request.top_k)
    return RecommendationResponse(
        items=[RecommendationItem(**r) for r in result["items"]],
        reason=result.get("reason"),
        strategy=result.get("strategy"),
    )


class ExtractQuestionsRequest(BaseModel):
    source_text: str
    document_title: str = ""
    domain: str = ""
    max_questions: int = 10


@router.post("/extract-questions", response_model=TaskAcceptedResponse)
async def extract_questions(
    request: ExtractQuestionsRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    _require_worker()
    from app.models.source_document import SourceDocument

    doc = SourceDocument(
        title=request.document_title or "Untitled",
        body=request.source_text,
        domain=request.domain or None,
        uploaded_by_id=admin.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    result = await worker_client.trigger_extract_questions(
        source_text=request.source_text,
        document_title=request.document_title,
        domain=request.domain,
        max_questions=request.max_questions,
        source_document_id=str(doc.id),
    )
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return TaskAcceptedResponse(task_id=result["task_id"], status=result["status"])


@router.post("/extract-from-file", response_model=TaskAcceptedResponse)
async def extract_from_file(
    file: UploadFile = File(...),
    document_title: str = Form(""),
    domain: str = Form(""),
    max_questions: int = Form(10),
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    _require_worker()
    from app.models.source_document import SourceDocument
    from app.services.file_parser import parse_file

    content = await file.read()
    try:
        source_text = parse_file(content, file.filename or "unknown", file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not source_text.strip():
        raise HTTPException(status_code=400, detail="File contains no extractable text")

    title = document_title or file.filename or "Untitled"

    doc = SourceDocument(
        title=title,
        body=source_text,
        domain=domain or None,
        uploaded_by_id=admin.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    result = await worker_client.trigger_extract_questions(
        source_text=source_text,
        document_title=title,
        domain=domain,
        max_questions=max_questions,
        source_document_id=str(doc.id),
    )
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return TaskAcceptedResponse(task_id=result["task_id"], status=result["status"])


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    admin: User = require_role(RoleName.ADMIN),
):
    _require_worker()
    result = await worker_client.get_task_status(task_id)
    if not result:
        raise HTTPException(status_code=502, detail="Worker did not respond")
    return result
