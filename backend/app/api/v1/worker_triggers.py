import uuid

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/recommend", response_model=list[RecommendationItem])
async def recommend(
    request: RecommendRequest,
    admin: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    results = await recommend_respondents(db, request.question_id, request.top_k)
    return [RecommendationItem(**r) for r in results]


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
