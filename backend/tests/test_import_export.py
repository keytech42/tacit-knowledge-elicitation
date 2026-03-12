"""Tests for question import/export endpoints."""

from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import AnswerOption, Question, QuestionStatus
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import auth_header


class TestExport:
    async def test_empty(self, client: AsyncClient, admin_user: User):
        """Export with no questions returns empty list."""
        resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert data["questions"] == []
        assert "exported_at" in data

    async def test_with_questions(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export includes question fields and metadata."""
        q = Question(
            title="Test Q", body="Body text", category="Testing",
            created_by_id=admin_user.id, status=QuestionStatus.DRAFT.value,
        )
        db.add(q)
        await db.flush()
        db.add(AnswerOption(
            question_id=q.id, body="Option A", display_order=1,
            created_by_id=admin_user.id,
        ))
        await db.flush()

        resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["questions"]) == 1

        item = data["questions"][0]
        assert item["title"] == "Test Q"
        assert item["body"] == "Body text"
        assert item["category"] == "Testing"
        assert len(item["answer_options"]) == 1
        assert item["answer_options"][0]["body"] == "Option A"
        assert item["answer_options"][0]["display_order"] == 1

        meta = item["_metadata"]
        assert meta["status"] == "draft"
        assert meta["created_by"] == "Admin User"
        assert meta["answer_count"] == 0

    async def test_answer_counts(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export metadata includes answer counts."""
        q = Question(
            title="Q with answers", body="Body",
            created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value,
        )
        db.add(q)
        await db.flush()

        a1 = Answer(question_id=q.id, author_id=admin_user.id, body="A1", status=AnswerStatus.APPROVED.value)
        a2 = Answer(question_id=q.id, author_id=admin_user.id, body="A2", status=AnswerStatus.DRAFT.value)
        db.add_all([a1, a2])
        await db.flush()

        resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        data = resp.json()
        meta = data["questions"][0]["_metadata"]
        assert meta["answer_count"] == 2
        assert meta["approved_answer_count"] == 1

    async def test_status_filter(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export respects status filter."""
        q1 = Question(title="Draft Q", body="B1", created_by_id=admin_user.id, status=QuestionStatus.DRAFT.value)
        q2 = Question(title="Published Q", body="B2", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add_all([q1, q2])
        await db.flush()

        resp = await client.get(
            "/api/v1/questions/export?status=published",
            headers=auth_header(admin_user),
        )
        data = resp.json()
        assert len(data["questions"]) == 1
        assert data["questions"][0]["title"] == "Published Q"

    async def test_category_filter(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export respects category filter."""
        q1 = Question(title="Q1", body="B1", category="Alpha", created_by_id=admin_user.id)
        q2 = Question(title="Q2", body="B2", category="Beta", created_by_id=admin_user.id)
        db.add_all([q1, q2])
        await db.flush()

        resp = await client.get(
            "/api/v1/questions/export?category=Alpha",
            headers=auth_header(admin_user),
        )
        data = resp.json()
        assert len(data["questions"]) == 1
        assert data["questions"][0]["title"] == "Q1"

    async def test_content_disposition(self, client: AsyncClient, admin_user: User):
        """Export response has Content-Disposition header."""
        resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        assert "content-disposition" in resp.headers
        assert "questions-" in resp.headers["content-disposition"]
        assert ".json" in resp.headers["content-disposition"]

    async def test_requires_admin(self, client: AsyncClient, author_user: User):
        """Export is admin-only."""
        resp = await client.get("/api/v1/questions/export", headers=auth_header(author_user))
        assert resp.status_code == 403

    async def test_includes_show_suggestions(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export includes show_suggestions field."""
        q = Question(
            title="Sugg Q", body="Body",
            created_by_id=admin_user.id, show_suggestions=True,
        )
        db.add(q)
        await db.flush()

        resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        data = resp.json()
        assert data["questions"][0]["show_suggestions"] is True


class TestImport:
    async def test_basic(self, client: AsyncClient, admin_user: User):
        """Import creates questions as draft."""
        payload = {
            "version": "1.0",
            "questions": [
                {"title": "Imported Q1", "body": "Body 1", "category": "Test"},
                {"title": "Imported Q2", "body": "Body 2"},
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 2
        assert len(data["question_ids"]) == 2

        # Verify questions exist and are drafts
        for qid in data["question_ids"]:
            q_resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_header(admin_user))
            assert q_resp.status_code == 200
            assert q_resp.json()["status"] == "draft"

    async def test_with_options(self, client: AsyncClient, admin_user: User):
        """Import creates answer options alongside questions."""
        payload = {
            "version": "1.0",
            "questions": [
                {
                    "title": "Q with opts", "body": "Body",
                    "answer_options": [
                        {"body": "Opt A", "display_order": 1},
                        {"body": "Opt B", "display_order": 2},
                    ],
                },
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 201
        qid = resp.json()["question_ids"][0]

        q_resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_header(admin_user))
        opts = q_resp.json()["answer_options"]
        assert len(opts) == 2
        assert {o["body"] for o in opts} == {"Opt A", "Opt B"}

    async def test_review_policy_preserved(self, client: AsyncClient, admin_user: User):
        """Import preserves full review_policy dict without field loss."""
        policy = {
            "min_approvals": 3,
            "auto_assign": True,
            "allow_self_review": False,
            "require_comment_on_reject": True,
        }
        payload = {
            "version": "1.0",
            "questions": [
                {"title": "Q with policy", "body": "Body", "review_policy": policy},
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 201
        qid = resp.json()["question_ids"][0]

        q_resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_header(admin_user))
        saved_policy = q_resp.json()["review_policy"]
        assert saved_policy["min_approvals"] == 3
        assert saved_policy["require_comment_on_reject"] is True

    async def test_show_suggestions_preserved(self, client: AsyncClient, admin_user: User):
        """Import preserves show_suggestions flag."""
        payload = {
            "version": "1.0",
            "questions": [
                {"title": "Suggestions Q", "body": "Body", "show_suggestions": True},
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 201
        qid = resp.json()["question_ids"][0]
        q_resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_header(admin_user))
        assert q_resp.json()["show_suggestions"] is True

    async def test_requires_admin(self, client: AsyncClient, author_user: User):
        """Import is admin-only."""
        payload = {"version": "1.0", "questions": [{"title": "X", "body": "Y"}]}
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(author_user),
        )
        assert resp.status_code == 403

    async def test_rejects_empty_title(self, client: AsyncClient, admin_user: User):
        """Import validates non-empty title."""
        payload = {"version": "1.0", "questions": [{"title": "  ", "body": "Body"}]}
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422

    async def test_rejects_empty_body(self, client: AsyncClient, admin_user: User):
        """Import validates non-empty body."""
        payload = {"version": "1.0", "questions": [{"title": "Title", "body": ""}]}
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422

    async def test_rejects_bad_version(self, client: AsyncClient, admin_user: User):
        """Import rejects unsupported version."""
        payload = {"version": "2.0", "questions": [{"title": "X", "body": "Y"}]}
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422

    async def test_rejects_empty_questions(self, client: AsyncClient, admin_user: User):
        """Import rejects empty questions array."""
        payload = {"version": "1.0", "questions": []}
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422

    async def test_rejects_duplicate_display_order(self, client: AsyncClient, admin_user: User):
        """Import validates unique display_order within answer_options."""
        payload = {
            "version": "1.0",
            "questions": [
                {
                    "title": "Q", "body": "B",
                    "answer_options": [
                        {"body": "A", "display_order": 1},
                        {"body": "B", "display_order": 1},
                    ],
                },
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422

    async def test_rejects_invalid_review_policy(self, client: AsyncClient, admin_user: User):
        """Import validates review_policy.min_approvals range."""
        payload = {
            "version": "1.0",
            "questions": [
                {"title": "Q", "body": "B", "review_policy": {"min_approvals": 99}},
            ],
        }
        resp = await client.post(
            "/api/v1/questions/import", json=payload,
            headers=auth_header(admin_user),
        )
        assert resp.status_code == 422


class TestRoundtrip:
    async def test_export_then_import(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """Export then import produces equivalent questions."""
        q = Question(
            title="Roundtrip Q", body="Roundtrip body", category="RT",
            created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value,
            show_suggestions=True,
            review_policy={"min_approvals": 2, "require_comment_on_reject": True},
        )
        db.add(q)
        await db.flush()
        db.add(AnswerOption(question_id=q.id, body="RT Opt", display_order=1, created_by_id=admin_user.id))
        await db.flush()

        # Export
        export_resp = await client.get("/api/v1/questions/export", headers=auth_header(admin_user))
        export_data = export_resp.json()

        # Import the exported data (_metadata and exported_at are ignored)
        import_resp = await client.post(
            "/api/v1/questions/import", json=export_data,
            headers=auth_header(admin_user),
        )
        assert import_resp.status_code == 201
        data = import_resp.json()
        assert data["created"] == 1

        # Verify imported question matches original
        qid = data["question_ids"][0]
        q_resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_header(admin_user))
        imported = q_resp.json()
        assert imported["title"] == "Roundtrip Q"
        assert imported["body"] == "Roundtrip body"
        assert imported["category"] == "RT"
        assert imported["status"] == "draft"  # Always imported as draft
        assert imported["show_suggestions"] is True
        assert imported["review_policy"]["min_approvals"] == 2
        assert imported["review_policy"]["require_comment_on_reject"] is True
        assert len(imported["answer_options"]) == 1
        assert imported["answer_options"][0]["body"] == "RT Opt"
