import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base, TimestampMixin, UUIDMixin


class AnswerStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class RevisionTrigger(str, enum.Enum):
    INITIAL_SUBMIT = "initial_submit"
    REVISION_AFTER_REVIEW = "revision_after_review"
    POST_APPROVAL_UPDATE = "post_approval_update"


class Answer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answers"

    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("answer_options.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(AnswerStatus, name="answerstatus", values_callable=lambda e: [x.value for x in e]),
        default=AnswerStatus.DRAFT,
    )
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    embedding = mapped_column(Vector(1536), nullable=True)

    question = relationship("Question", lazy="selectin")
    author = relationship("User", foreign_keys=[author_id], lazy="selectin")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id], lazy="selectin")
    selected_option = relationship("AnswerOption", lazy="selectin")
    revisions = relationship("AnswerRevision", back_populates="answer", order_by="AnswerRevision.version", lazy="selectin")
    collaborators = relationship("AnswerCollaborator", back_populates="answer")


class AnswerRevision(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_revisions"

    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("answers.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("answer_options.id"), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    trigger: Mapped[str] = mapped_column(
        SAEnum(RevisionTrigger, name="revisiontrigger", values_callable=lambda e: [x.value for x in e])
    )
    previous_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    answer = relationship("Answer", back_populates="revisions")
    created_by = relationship("User", lazy="selectin")

    __table_args__ = (UniqueConstraint("answer_id", "version", name="uq_answer_version"),)


class AnswerCollaborator(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_collaborators"

    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("answers.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    granted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    answer = relationship("Answer", back_populates="collaborators")
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    granted_by = relationship("User", foreign_keys=[granted_by_id], lazy="selectin")

    __table_args__ = (UniqueConstraint("answer_id", "user_id", name="uq_answer_collaborator"),)
