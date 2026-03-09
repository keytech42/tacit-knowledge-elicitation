"""Add source_documents table and extraction columns to questions

Revision ID: 009
Revises: 008
Create Date: 2026-03-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sourcetype enum
    op.execute("CREATE TYPE sourcetype AS ENUM ('manual', 'generated', 'extracted')")

    # Create source_documents table
    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("document_summary", sa.Text, nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add extraction columns to questions
    op.add_column(
        "questions",
        sa.Column(
            "source_type",
            sa.Enum("manual", "generated", "extracted", name="sourcetype", create_type=False),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "questions",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("source_passage", sa.Text, nullable=True),
    )
    op.create_foreign_key(
        "fk_questions_source_document_id",
        "questions",
        "source_documents",
        ["source_document_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_questions_source_document_id", "questions", type_="foreignkey")
    op.drop_column("questions", "source_passage")
    op.drop_column("questions", "source_document_id")
    op.drop_column("questions", "source_type")
    op.drop_table("source_documents")
    sa.Enum(name="sourcetype").drop(op.get_bind())
