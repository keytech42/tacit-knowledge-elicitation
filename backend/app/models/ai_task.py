import enum

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base, UUIDMixin, TimestampMixin


class AITaskType(str, enum.Enum):
    GENERATE_QUESTIONS = "generate_questions"
    EXTRACT_QUESTIONS = "extract_questions"
    SCAFFOLD_OPTIONS = "scaffold_options"
    REVIEW_ASSIST = "review_assist"


class AITaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AITask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_tasks"

    task_type = Column(
        SAEnum(AITaskType, name="aitasktype", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status = Column(
        SAEnum(AITaskStatus, name="aitaskstatus", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=AITaskStatus.PENDING,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    worker_task_id = Column(String(100), nullable=True)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
