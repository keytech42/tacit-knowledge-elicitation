import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AITaskResponse(BaseModel):
    id: uuid.UUID
    task_type: str
    status: str
    worker_task_id: str | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AITaskListResponse(BaseModel):
    items: list[AITaskResponse]
    total: int
