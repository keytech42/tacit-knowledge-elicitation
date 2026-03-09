import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class SourceDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    question_count: Mapped[int] = mapped_column(Integer, default=0)

    uploaded_by = relationship("User", lazy="selectin")
