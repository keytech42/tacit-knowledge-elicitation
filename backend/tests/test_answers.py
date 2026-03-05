from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


class TestAnswerCRUD:
    async def test_create_answer(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "My answer"}, headers=auth_header(respondent_user))
        assert r.status_code == 201
        assert r.json()["status"] == "draft"
        assert r.json()["author"]["id"] == str(respondent_user.id)

    async def test_cannot_answer_unpublished(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.DRAFT.value)
        db.add(q)
        await db.flush()
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Answer"}, headers=auth_header(respondent_user))
        assert r.status_code == 409

    async def test_list_answers(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value)
        db.add(a)
        await db.flush()
        r = await client.get(f"/api/v1/questions/{q.id}/answers", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["total"] >= 1


class TestAnswerSubmitAndRevision:
    async def test_submit_creates_revision(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V1 content")
        db.add(a)
        await db.flush()

        r = await client.post(f"/api/v1/answers/{a.id}/submit", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 1

        versions = await client.get(f"/api/v1/answers/{a.id}/versions", headers=auth_header(respondent_user))
        assert len(versions.json()) == 1
        assert versions.json()[0]["trigger"] == "initial_submit"

    async def test_post_approval_revision(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V1", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        # Revise atomically with new content
        r = await client.post(f"/api/v1/answers/{a.id}/revise", json={"body": "V2 updated"}, headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 2
        assert r.json()["body"] == "V2 updated"

    async def test_cannot_patch_approved_answer(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """Even admins cannot PATCH an approved answer — must use revise."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V1", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        r = await client.patch(f"/api/v1/answers/{a.id}", json={"body": "Sneaky edit"}, headers=auth_header(admin_user))
        assert r.status_code == 403

    async def test_diff_between_versions(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        from app.models.answer import AnswerRevision
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V2", status=AnswerStatus.SUBMITTED.value, current_version=2)
        db.add(a)
        await db.flush()
        r1 = AnswerRevision(answer_id=a.id, version=1, body="First version", created_by_id=respondent_user.id, trigger="initial_submit")
        r2 = AnswerRevision(answer_id=a.id, version=2, body="Second version", created_by_id=respondent_user.id, trigger="post_approval_update")
        db.add_all([r1, r2])
        await db.flush()

        r = await client.get(f"/api/v1/answers/{a.id}/diff", params={"from": 1, "to": 2}, headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert "First version" in r.json()["diff"] or "Second version" in r.json()["diff"]


class TestStagingDiff:
    async def test_staging_diff_shows_uncommitted_changes(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """After submitting (v1) and editing in revision_requested, staging diff shows changes."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        # Create, submit (creates v1)
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Original content"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # No changes yet — staging diff should be empty
        r = await client.get(f"/api/v1/answers/{a_id}/staging-diff", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["has_changes"] is False
        assert r.json()["latest_version"] == 1
        assert r.json()["diff"] is None

    async def test_staging_diff_after_edit(self, client: AsyncClient, respondent_user: User, admin_user: User, reviewer_user: User, db):
        """Edit a revision_requested answer, then check staging diff."""
        from app.models.review import Review, ReviewTargetType, ReviewVerdict
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Original"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Get changes requested
        rv = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))
        await client.patch(f"/api/v1/reviews/{rv.json()['id']}", json={"verdict": "changes_requested"}, headers=auth_header(reviewer_user))

        # Edit in revision_requested state
        await client.patch(f"/api/v1/answers/{a_id}", json={"body": "Improved content"}, headers=auth_header(respondent_user))

        # Staging diff should show the change
        r = await client.get(f"/api/v1/answers/{a_id}/staging-diff", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["has_changes"] is True
        assert r.json()["latest_version"] == 1
        assert "Original" in r.json()["diff"]
        assert "Improved content" in r.json()["diff"]

    async def test_staging_diff_no_revisions(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """Draft with no revisions yet — staging diff returns no changes."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Draft"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        r = await client.get(f"/api/v1/answers/{a_id}/staging-diff", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["has_changes"] is False
        assert r.json()["latest_version"] is None


class TestAtomicRevise:
    async def test_revise_with_body_creates_version(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """POST /revise with body atomically updates content and creates a new version."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V1", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        r = await client.post(f"/api/v1/answers/{a.id}/revise", json={"body": "V2 content"}, headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["body"] == "V2 content"
        assert r.json()["current_version"] == 2
        assert r.json()["status"] == "submitted"

        # Verify the revision snapshot has the new body
        versions = await client.get(f"/api/v1/answers/{a.id}/versions", headers=auth_header(respondent_user))
        v2 = [v for v in versions.json() if v["version"] == 2][0]
        assert v2["body"] == "V2 content"
        assert v2["trigger"] == "post_approval_update"

    async def test_revise_identical_content_rejected(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """POST /revise with same body as latest revision returns 409."""
        from app.models.answer import AnswerRevision
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Same", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()
        rev = AnswerRevision(answer_id=a.id, version=1, body="Same", created_by_id=respondent_user.id, trigger="initial_submit")
        db.add(rev)
        await db.flush()

        r = await client.post(f"/api/v1/answers/{a.id}/revise", json={"body": "Same"}, headers=auth_header(respondent_user))
        assert r.status_code == 409

    async def test_revise_without_body_uses_current(self, client: AsyncClient, respondent_user: User, admin_user: User, db):
        """POST /revise without body uses the current answer body (backwards compat, but still needs diff)."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="V1 content", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        # No body provided and current body hasn't changed — should fail duplicate check
        # (no revisions to compare against, so it should succeed since check_duplicate only checks if revisions exist)
        r = await client.post(f"/api/v1/answers/{a.id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["body"] == "V1 content"


class TestCollaborators:
    async def test_add_and_list_collaborator(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        r = await client.post(f"/api/v1/answers/{a.id}/collaborators", json={"user_id": str(reviewer_user.id)}, headers=auth_header(respondent_user))
        assert r.status_code == 201

        r = await client.get(f"/api/v1/answers/{a.id}/collaborators", headers=auth_header(respondent_user))
        assert len(r.json()) == 1
        assert r.json()[0]["user"]["id"] == str(reviewer_user.id)

    async def test_non_author_cannot_add_collaborator(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.APPROVED.value, current_version=1)
        db.add(a)
        await db.flush()

        r = await client.post(f"/api/v1/answers/{a.id}/collaborators", json={"user_id": str(reviewer_user.id)}, headers=auth_header(reviewer_user))
        assert r.status_code == 403
