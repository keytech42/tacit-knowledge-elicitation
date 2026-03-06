"""Resize embedding columns from vector(1536) to vector(1024) for bge-m3

Revision ID: 005
Revises: 004
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop indexes first (they reference the old column type)
    op.execute("DROP INDEX IF EXISTS ix_questions_embedding")
    op.execute("DROP INDEX IF EXISTS ix_answers_embedding")
    # Clear existing embeddings (incompatible dimensions)
    op.execute("UPDATE questions SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("UPDATE answers SET embedding = NULL WHERE embedding IS NOT NULL")
    # Alter column types
    op.execute("ALTER TABLE questions ALTER COLUMN embedding TYPE vector(1024)")
    op.execute("ALTER TABLE answers ALTER COLUMN embedding TYPE vector(1024)")
    # Recreate indexes
    op.execute("CREATE INDEX ix_questions_embedding ON questions USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_answers_embedding ON answers USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_answers_embedding")
    op.execute("DROP INDEX IF EXISTS ix_questions_embedding")
    op.execute("UPDATE questions SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("UPDATE answers SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("ALTER TABLE questions ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("ALTER TABLE answers ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("CREATE INDEX ix_questions_embedding ON questions USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_answers_embedding ON answers USING hnsw (embedding vector_cosine_ops)")
