import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReviewTargetType(str, enum.Enum):
    QUESTION = "question"
    ANSWER = "answer"


class ReviewVerdict(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class Review(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reviews"

    target_type: Mapped[str] = mapped_column(
        SAEnum(ReviewTargetType, name="reviewtargettype", values_callable=lambda e: [x.value for x in e])
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verdict: Mapped[str] = mapped_column(
        SAEnum(ReviewVerdict, name="reviewverdict", values_callable=lambda e: [x.value for x in e]),
        default=ReviewVerdict.PENDING,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reviewer = relationship("User", foreign_keys=[reviewer_id], lazy="selectin")
    assigned_by = relationship("User", foreign_keys=[assigned_by_id], lazy="selectin")
    comments = relationship("ReviewComment", back_populates="review", lazy="selectin")

    __table_args__ = (Index("ix_reviews_target", "target_type", "target_id"),)


class ReviewComment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "review_comments"

    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reviews.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("review_comments.id"), nullable=True)

    review = relationship("Review", back_populates="comments", lazy="selectin")
    author = relationship("User", lazy="selectin")
    replies = relationship("ReviewComment", lazy="selectin")
