"""Add slack_thread_ts and slack_channel columns to questions

Revision ID: 007
Revises: 006
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("slack_thread_ts", sa.String(64), nullable=True))
    op.add_column("questions", sa.Column("slack_channel", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "slack_channel")
    op.drop_column("questions", "slack_thread_ts")
