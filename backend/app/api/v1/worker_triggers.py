import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.database import get_db
from app.models.user import RoleName, User
from app.models.ai_task import AITask, AITaskType, AITaskStatus
from app.schemas.ai_task import AITaskResponse, AITaskListResponse
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


def _require_worker():
    if not settings.WORKER_URL:
        raise HTTPException(status_code=503, detail="Worker service not configured")


async def _create_and_dispatch(
    db: AsyncSession,
    user: User,
    task_type: AITaskType,
    worker_func,
    **worker_kwargs,
) -> AITask:
    """Create an AITask row, dispatch to worker, and update with worker_task_id."""
    ai_task = AITask(
        task_type=task_type,
        status=AITaskStatus.PENDING,
        user_id=user.id,
    )
    db.add(ai_task)
    await db.flush()
    await db.refresh(ai_task)

    result = await worker_func(**worker_kwargs)

    if result and result.get("task_id"):
        ai_task.worker_task_id = result["task_id"]
        ai_task.status = AITaskStatus.RUNNING
    else:
        ai_task.status = AITaskStatus.FAILED
        ai_task.error = "Worker did not respond"

    await db.flush()
    await db.refresh(ai_task)
    return ai_task


@router.post("/generate-questions", response_model=AITaskResponse)
async def generate_questions(
    request: GenerateQuestionsRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    _require_worker()
    ai_task = await _create_and_dispatch(
        db, admin, AITaskType.GENERATE_QUESTIONS,
        worker_client.trigger_generate_questions,
        topic=request.topic,
        domain=request.domain,
        count=request.count,
        context=request.context,
    )
    return ai_task


@router.post("/scaffold-options", response_model=AITaskResponse)
async def scaffold_options(
    request: ScaffoldOptionsRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    _require_worker()
    ai_task = await _create_and_dispatch(
        db, admin, AITaskType.SCAFFOLD_OPTIONS,
        worker_client.trigger_scaffold_options,
        question_id=request.question_id,
        num_options=request.capped_options(),
    )
    return ai_task


@router.post("/review-assist", response_model=AITaskResponse)
async def review_assist(
    request: ReviewAssistRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    _require_worker()
    ai_task = await _create_and_dispatch(
        db, admin, AITaskType.REVIEW_ASSIST,
        worker_client.trigger_review_assist,
        answer_id=request.answer_id,
    )
    return ai_task


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


@router.post("/extract-questions", response_model=AITaskResponse)
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

    ai_task = await _create_and_dispatch(
        db, admin, AITaskType.EXTRACT_QUESTIONS,
        worker_client.trigger_extract_questions,
        source_text=request.source_text,
        document_title=request.document_title,
        domain=request.domain,
        max_questions=request.max_questions,
        source_document_id=str(doc.id),
    )
    return ai_task


@router.post("/extract-from-file", response_model=AITaskResponse)
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

    ai_task = await _create_and_dispatch(
        db, admin, AITaskType.EXTRACT_QUESTIONS,
        worker_client.trigger_extract_questions,
        source_text=source_text,
        document_title=title,
        domain=domain,
        max_questions=max_questions,
        source_document_id=str(doc.id),
    )
    return ai_task


@router.get("/tasks", response_model=AITaskListResponse)
async def list_tasks(
    status: str | None = Query(None),
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    query = select(AITask).where(AITask.user_id == admin.id)
    count_query = select(func.count()).select_from(AITask).where(AITask.user_id == admin.id)

    if status:
        query = query.where(AITask.status == status)
        count_query = count_query.where(AITask.status == status)

    query = query.order_by(AITask.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    return AITaskListResponse(items=tasks, total=total)


@router.get("/tasks/{task_id}", response_model=AITaskResponse)
async def get_task_status(
    task_id: uuid.UUID,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AITask).where(AITask.id == task_id))
    ai_task = result.scalar_one_or_none()
    if not ai_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Sync status from worker if task is still in progress
    if ai_task.worker_task_id and ai_task.status in (
        AITaskStatus.PENDING, AITaskStatus.RUNNING,
    ):
        worker_status = await worker_client.get_task_status(ai_task.worker_task_id)
        if worker_status:
            worker_state = worker_status.get("status")
            if worker_state == "completed":
                ai_task.status = AITaskStatus.COMPLETED
                ai_task.result = worker_status.get("result")
            elif worker_state == "failed":
                ai_task.status = AITaskStatus.FAILED
                ai_task.error = worker_status.get("error")
            elif worker_state == "cancelled":
                ai_task.status = AITaskStatus.CANCELLED
            elif worker_state == "running":
                ai_task.status = AITaskStatus.RUNNING
            await db.flush()
            await db.refresh(ai_task)

    return ai_task


@router.post("/tasks/{task_id}/cancel", response_model=AITaskResponse)
async def cancel_task(
    task_id: uuid.UUID,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AITask).where(AITask.id == task_id))
    ai_task = result.scalar_one_or_none()
    if not ai_task:
        raise HTTPException(status_code=404, detail="Task not found")

    if ai_task.status not in (AITaskStatus.PENDING, AITaskStatus.RUNNING):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel task in '{ai_task.status.value}' state",
        )

    # Try to cancel on worker
    if ai_task.worker_task_id:
        await worker_client.cancel_task(ai_task.worker_task_id)

    ai_task.status = AITaskStatus.CANCELLED
    await db.flush()
    await db.refresh(ai_task)
    return ai_task
