import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AIInteractionLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_interaction_logs"

    service_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(2048))
    request_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_status: Mapped[int] = mapped_column(Integer)
    created_entity_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service_user = relationship("User", foreign_keys=[service_user_id], lazy="selectin")
    feedback_by = relationship("User", foreign_keys=[feedback_by_id], lazy="selectin")
