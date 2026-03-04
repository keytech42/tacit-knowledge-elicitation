"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    usertype = sa.Enum("human", "service", name="usertype")
    rolename = sa.Enum("admin", "author", "respondent", "reviewer", name="rolename")
    questionstatus = sa.Enum("draft", "proposed", "in_review", "published", "closed", "archived", name="questionstatus")
    confirmation = sa.Enum("pending", "confirmed", "rejected", "revised", name="confirmation")
    answerstatus = sa.Enum("draft", "submitted", "under_review", "revision_requested", "approved", "rejected", name="answerstatus")
    revisiontrigger = sa.Enum("initial_submit", "revision_after_review", "post_approval_update", name="revisiontrigger")
    reviewtargettype = sa.Enum("question", "answer", name="reviewtargettype")
    reviewverdict = sa.Enum("pending", "approved", "changes_requested", "rejected", name="reviewverdict")

    op.create_table("roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", rolename, unique=True, nullable=False),
        sa.Column("permissions", postgresql.JSONB, nullable=True),
    )

    op.create_table("users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_type", usertype, nullable=False),
        sa.Column("external_id", sa.String(255), unique=True, nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("model_id", sa.String(255), nullable=True),
        sa.Column("system_version", sa.String(255), nullable=True),
        sa.Column("api_key_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), primary_key=True),
    )

    op.create_table("questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("category", sa.String(255), nullable=True, index=True),
        sa.Column("status", questionstatus, nullable=False, server_default="draft"),
        sa.Column("confirmation", confirmation, nullable=False, server_default="pending"),
        sa.Column("review_policy", postgresql.JSONB, nullable=True),
        sa.Column("show_suggestions", sa.Boolean, default=False, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("question_quality_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("question_id", "user_id", name="uq_question_user_feedback"),
    )

    op.create_table("answer_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False, index=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("display_order", sa.Integer, default=0, nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False, index=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("selected_option_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answer_options.id"), nullable=True),
        sa.Column("status", answerstatus, nullable=False, server_default="draft"),
        sa.Column("current_version", sa.Integer, default=0, nullable=False),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("answer_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answers.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("selected_option_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answer_options.id"), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trigger", revisiontrigger, nullable=False),
        sa.Column("previous_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("answer_id", "version", name="uq_answer_version"),
    )

    op.create_table("answer_collaborators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answers.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("granted_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("answer_id", "user_id", name="uq_answer_collaborator"),
    )

    op.create_table("reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", reviewtargettype, nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verdict", reviewverdict, nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_reviews_target", "target_type", "target_id"),
    )

    op.create_table("review_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id"), nullable=False, index=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("review_comments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("ai_interaction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("model_id", sa.String(255), nullable=True),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("request_body", postgresql.JSONB, nullable=True),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("created_entity_type", sa.String(255), nullable=True),
        sa.Column("created_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("token_usage", postgresql.JSONB, nullable=True),
        sa.Column("feedback_rating", sa.Integer, nullable=True),
        sa.Column("feedback_comment", sa.Text, nullable=True),
        sa.Column("feedback_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_interaction_logs")
    op.drop_table("review_comments")
    op.drop_table("reviews")
    op.drop_table("answer_collaborators")
    op.drop_table("answer_revisions")
    op.drop_table("answers")
    op.drop_table("answer_options")
    op.drop_table("question_quality_feedback")
    op.drop_table("questions")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
    sa.Enum(name="usertype").drop(op.get_bind())
    sa.Enum(name="rolename").drop(op.get_bind())
    sa.Enum(name="questionstatus").drop(op.get_bind())
    sa.Enum(name="confirmation").drop(op.get_bind())
    sa.Enum(name="answerstatus").drop(op.get_bind())
    sa.Enum(name="revisiontrigger").drop(op.get_bind())
    sa.Enum(name="reviewtargettype").drop(op.get_bind())
    sa.Enum(name="reviewverdict").drop(op.get_bind())
