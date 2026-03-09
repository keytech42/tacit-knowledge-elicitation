import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.question import Question
from app.models.source_document import SourceDocument
from app.models.user import RoleName, User
from app.schemas.source_document import (
    SourceDocumentCreate,
    SourceDocumentListResponse,
    SourceDocumentResponse,
    SourceDocumentUpdate,
)

router = APIRouter(prefix="/source-documents", tags=["source-documents"])


@router.post("", response_model=SourceDocumentResponse, status_code=201)
async def create_source_document(
    request: SourceDocumentCreate,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    doc = SourceDocument(
        title=request.title,
        body=request.body,
        domain=request.domain,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@router.get("", response_model=SourceDocumentListResponse)
async def list_source_documents(
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceDocument).order_by(SourceDocument.created_at.desc())
    )
    items = result.scalars().all()
    return SourceDocumentListResponse(items=items, total=len(items))


@router.get("/{doc_id}", response_model=SourceDocumentResponse)
async def get_source_document(
    doc_id: uuid.UUID,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceDocument).where(SourceDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Source document not found")
    return doc


@router.patch("/{doc_id}", response_model=SourceDocumentResponse)
async def update_source_document(
    doc_id: uuid.UUID,
    request: SourceDocumentUpdate,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceDocument).where(SourceDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Source document not found")
    if request.document_summary is not None:
        doc.document_summary = request.document_summary
    if request.question_count is not None:
        doc.question_count = request.question_count
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_source_document(
    doc_id: uuid.UUID,
    current_user: User = require_role(RoleName.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceDocument).where(SourceDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Source document not found")
    # Nullify source_document_id on linked questions before deleting
    await db.execute(
        update(Question)
        .where(Question.source_document_id == doc_id)
        .values(source_document_id=None)
    )
    await db.delete(doc)
    await db.flush()
