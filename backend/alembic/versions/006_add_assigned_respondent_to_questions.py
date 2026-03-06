"""Add assigned_respondent_id to questions

Revision ID: 006
Revises: 005
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("assigned_respondent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_questions_assigned_respondent_id",
        "questions",
        "users",
        ["assigned_respondent_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_questions_assigned_respondent_id", "questions", type_="foreignkey")
    op.drop_column("questions", "assigned_respondent_id")
