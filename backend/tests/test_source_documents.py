import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.config import settings
from app.models.question import Question, QuestionStatus, SourceType
from app.models.source_document import SourceDocument
from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.asyncio


class TestSourceDocumentCRUD:
    """Tests for POST/GET/PATCH/DELETE /api/v1/source-documents."""

    async def test_create_source_document(self, client: AsyncClient, admin_user: User):
        r = await client.post(
            "/api/v1/source-documents",
            json={"title": "Test Doc", "body": "Document content here.", "domain": "engineering"},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Test Doc"
        assert data["domain"] == "engineering"
        assert data["document_summary"] is None
        assert data["question_count"] == 0
        assert data["uploaded_by"]["id"] == str(admin_user.id)

    async def test_create_without_domain(self, client: AsyncClient, admin_user: User):
        r = await client.post(
            "/api/v1/source-documents",
            json={"title": "No Domain", "body": "Content."},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        assert r.json()["domain"] is None

    async def test_list_source_documents(self, client: AsyncClient, admin_user: User, db):
        doc1 = SourceDocument(title="Doc 1", body="Body 1", uploaded_by_id=admin_user.id)
        doc2 = SourceDocument(title="Doc 2", body="Body 2", domain="science", uploaded_by_id=admin_user.id)
        db.add_all([doc1, doc2])
        await db.flush()

        r = await client.get("/api/v1/source-documents", headers=auth_header(admin_user))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2
        titles = [d["title"] for d in data["items"]]
        assert "Doc 1" in titles
        assert "Doc 2" in titles

    async def test_get_source_document(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Single Doc", body="Body", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.get(f"/api/v1/source-documents/{doc.id}", headers=auth_header(admin_user))
        assert r.status_code == 200
        assert r.json()["title"] == "Single Doc"

    async def test_get_nonexistent_returns_404(self, client: AsyncClient, admin_user: User):
        r = await client.get(f"/api/v1/source-documents/{uuid.uuid4()}", headers=auth_header(admin_user))
        assert r.status_code == 404

    async def test_update_source_document(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Update Me", body="Body", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.patch(
            f"/api/v1/source-documents/{doc.id}",
            json={"document_summary": "A summary of the doc.", "question_count": 5},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["document_summary"] == "A summary of the doc."
        assert data["question_count"] == 5

    async def test_partial_update(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Partial", body="Body", uploaded_by_id=admin_user.id, question_count=3)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.patch(
            f"/api/v1/source-documents/{doc.id}",
            json={"document_summary": "Only summary"},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 200
        assert r.json()["document_summary"] == "Only summary"
        assert r.json()["question_count"] == 3  # unchanged

    async def test_delete_source_document(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Delete Me", body="Body", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.delete(f"/api/v1/source-documents/{doc.id}", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Verify it's gone
        r2 = await client.get(f"/api/v1/source-documents/{doc.id}", headers=auth_header(admin_user))
        assert r2.status_code == 404

    async def test_delete_nullifies_linked_questions(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Linked Doc", body="Body", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        q = Question(
            title="Q from doc", body="Body", created_by_id=admin_user.id,
            source_type=SourceType.EXTRACTED.value,
            source_document_id=doc.id,
            source_passage="Some passage",
        )
        db.add(q)
        await db.flush()
        await db.refresh(q)

        r = await client.delete(f"/api/v1/source-documents/{doc.id}", headers=auth_header(admin_user))
        assert r.status_code == 204

        # Question should still exist but with null source_document_id
        qr = await client.get(f"/api/v1/questions/{q.id}", headers=auth_header(admin_user))
        assert qr.status_code == 200
        assert qr.json()["source_document_id"] is None


class TestSourceDocumentPermissions:
    """Non-admin users cannot access source document endpoints."""

    async def test_author_cannot_create(self, client: AsyncClient, author_user: User):
        r = await client.post(
            "/api/v1/source-documents",
            json={"title": "T", "body": "B"},
            headers=auth_header(author_user),
        )
        assert r.status_code == 403

    async def test_respondent_cannot_list(self, client: AsyncClient, respondent_user: User):
        r = await client.get("/api/v1/source-documents", headers=auth_header(respondent_user))
        assert r.status_code == 403

    async def test_reviewer_cannot_delete(self, client: AsyncClient, reviewer_user: User, admin_user: User, db):
        doc = SourceDocument(title="T", body="B", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.delete(f"/api/v1/source-documents/{doc.id}", headers=auth_header(reviewer_user))
        assert r.status_code == 403


class TestQuestionSourceFields:
    """Tests for source_type, source_document_id, source_passage on questions."""

    async def test_create_question_defaults_to_manual(self, client: AsyncClient, admin_user: User):
        r = await client.post(
            "/api/v1/questions",
            json={"title": "Plain Q", "body": "Body"},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        assert r.json()["source_type"] == "manual"
        assert r.json()["source_document_id"] is None
        assert r.json()["source_passage"] is None

    async def test_create_question_with_source_type(self, client: AsyncClient, admin_user: User):
        r = await client.post(
            "/api/v1/questions",
            json={"title": "Generated Q", "body": "Body", "source_type": "generated"},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        assert r.json()["source_type"] == "generated"

    async def test_create_question_with_source_document(self, client: AsyncClient, admin_user: User, db):
        doc = SourceDocument(title="Source", body="Content", uploaded_by_id=admin_user.id)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        r = await client.post(
            "/api/v1/questions",
            json={
                "title": "Extracted Q", "body": "Body",
                "source_type": "extracted",
                "source_document_id": str(doc.id),
                "source_passage": "Relevant passage from the doc.",
            },
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["source_type"] == "extracted"
        assert data["source_document_id"] == str(doc.id)
        assert data["source_passage"] == "Relevant passage from the doc."

    async def test_source_type_in_list_response(self, client: AsyncClient, admin_user: User):
        await client.post(
            "/api/v1/questions",
            json={"title": "List Test", "body": "Body", "source_type": "generated"},
            headers=auth_header(admin_user),
        )
        r = await client.get("/api/v1/questions", headers=auth_header(admin_user))
        assert r.status_code == 200
        questions = r.json()["questions"]
        matched = [q for q in questions if q["title"] == "List Test"]
        assert len(matched) == 1
        assert matched[0]["source_type"] == "generated"


class TestExtractQuestionsEndpoint:
    """Tests for POST /api/v1/ai/extract-questions trigger."""

    async def test_extract_creates_source_document_and_triggers_worker(
        self, client: AsyncClient, admin_user: User, db,
    ):
        mock_response = {"task_id": "test-task-123", "status": "accepted"}
        with patch("app.services.worker_client.trigger_extract_questions", new_callable=AsyncMock, return_value=mock_response), \
             patch.object(settings, "WORKER_URL", "http://worker:8001"):
            r = await client.post(
                "/api/v1/ai/extract-questions",
                json={
                    "source_text": "This is the document content for extraction.",
                    "document_title": "Test Document",
                    "domain": "testing",
                    "max_questions": 5,
                },
                headers=auth_header(admin_user),
            )

        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == "test-task-123"
        assert data["status"] == "accepted"

    async def test_extract_requires_admin(self, client: AsyncClient, author_user: User):
        r = await client.post(
            "/api/v1/ai/extract-questions",
            json={"source_text": "Content"},
            headers=auth_header(author_user),
        )
        assert r.status_code == 403

    async def test_extract_requires_worker(self, client: AsyncClient, admin_user: User):
        with patch.object(settings, "WORKER_URL", ""):
            r = await client.post(
                "/api/v1/ai/extract-questions",
                json={"source_text": "Content"},
                headers=auth_header(admin_user),
            )
        assert r.status_code == 503
