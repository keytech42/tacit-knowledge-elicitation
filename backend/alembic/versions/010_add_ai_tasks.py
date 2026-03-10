"""Add ai_tasks table for persistent AI task tracking

Revision ID: 010
Revises: 009
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    aitasktype = sa.Enum(
        "generate_questions", "extract_questions", "scaffold_options", "review_assist",
        name="aitasktype",
    )
    aitasktype.create(op.get_bind(), checkfirst=True)

    aitaskstatus = sa.Enum(
        "pending", "running", "completed", "failed", "cancelled",
        name="aitaskstatus",
    )
    aitaskstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ai_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", aitasktype, nullable=False),
        sa.Column("status", aitaskstatus, nullable=False, server_default="pending"),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("worker_task_id", sa.String(100), nullable=True),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_ai_tasks_user_id", "ai_tasks", ["user_id"])
    op.create_index("ix_ai_tasks_status", "ai_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_tasks_status")
    op.drop_index("ix_ai_tasks_user_id")
    op.drop_table("ai_tasks")
    sa.Enum(name="aitaskstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="aitasktype").drop(op.get_bind(), checkfirst=True)
