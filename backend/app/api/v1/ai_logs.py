import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.database import get_db
from app.models.ai_log import AIInteractionLog
from app.models.user import RoleName, User
from app.schemas.ai_log import AILogFeedback, AILogListResponse, AILogResponse

router = APIRouter(prefix="/ai-logs", tags=["ai-logs"])


@router.get("", response_model=AILogListResponse)
async def list_ai_logs(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    service_user_id: uuid.UUID | None = None,
    endpoint: str | None = None,
    skip: int = 0, limit: int = 50,
):
    query = select(AIInteractionLog)
    count_query = select(func.count(AIInteractionLog.id))

    if service_user_id:
        query = query.where(AIInteractionLog.service_user_id == service_user_id)
        count_query = count_query.where(AIInteractionLog.service_user_id == service_user_id)
    if endpoint:
        query = query.where(AIInteractionLog.endpoint.contains(endpoint))
        count_query = count_query.where(AIInteractionLog.endpoint.contains(endpoint))

    result = await db.execute(query.offset(skip).limit(limit).order_by(AIInteractionLog.created_at.desc()))
    logs = result.scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return AILogListResponse(logs=logs, total=total)


@router.get("/export")
async def export_ai_logs(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    result = await db.execute(select(AIInteractionLog).order_by(AIInteractionLog.created_at.desc()))
    logs = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "service_user_id", "model_id", "endpoint", "response_status", "latency_ms", "feedback_rating", "created_at"])
        for log in logs:
            writer.writerow([str(log.id), str(log.service_user_id), log.model_id, log.endpoint, log.response_status, log.latency_ms, log.feedback_rating, str(log.created_at)])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ai_logs.csv"})

    return [AILogResponse.model_validate(log) for log in logs]


@router.get("/{log_id}", response_model=AILogResponse)
async def get_ai_log(log_id: uuid.UUID, current_user: User = require_role(RoleName.ADMIN), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIInteractionLog).where(AIInteractionLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="AI log not found")
    return log


@router.post("/{log_id}/feedback", response_model=AILogResponse)
async def submit_feedback(
    log_id: uuid.UUID,
    request: AILogFeedback,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AIInteractionLog).where(AIInteractionLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="AI log not found")

    log.feedback_rating = request.rating
    log.feedback_comment = request.comment
    log.feedback_by_id = current_user.id
    log.feedback_at = datetime.now(timezone.utc)
    return log
