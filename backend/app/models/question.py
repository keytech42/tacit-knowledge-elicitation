import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class QuestionStatus(str, enum.Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    CLOSED = "closed"
    ARCHIVED = "archived"


class Confirmation(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVISED = "revised"


class Question(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        SAEnum(QuestionStatus, name="questionstatus", values_callable=lambda e: [x.value for x in e]),
        default=QuestionStatus.DRAFT,
    )
    confirmation: Mapped[str] = mapped_column(
        SAEnum(Confirmation, name="confirmation", values_callable=lambda e: [x.value for x in e]),
        default=Confirmation.PENDING,
    )
    review_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    show_suggestions: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id], lazy="selectin")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id], lazy="selectin")
    answer_options = relationship("AnswerOption", back_populates="question", lazy="selectin")
    feedback = relationship("QuestionQualityFeedback", back_populates="question")


class QuestionQualityFeedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "question_quality_feedback"

    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    question = relationship("Question", back_populates="feedback")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("question_id", "user_id", name="uq_question_user_feedback"),
    )


class AnswerOption(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_options"

    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    question = relationship("Question", back_populates="answer_options")
    created_by = relationship("User", lazy="selectin")
