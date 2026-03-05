"""Add pgvector extension and embedding columns

Revision ID: 004
Revises: 003
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE questions ADD COLUMN embedding vector(1536)")
    op.execute("ALTER TABLE answers ADD COLUMN embedding vector(1536)")
    # ivfflat indexes require rows to build lists; on empty tables use hnsw instead
    op.execute("CREATE INDEX ix_questions_embedding ON questions USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_answers_embedding ON answers USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_answers_embedding")
    op.execute("DROP INDEX IF EXISTS ix_questions_embedding")
    op.drop_column("answers", "embedding")
    op.drop_column("questions", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
