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

        # Update body then revise
        await client.patch(f"/api/v1/answers/{a.id}", json={"body": "V2 updated"}, headers=auth_header(admin_user))

        r = await client.post(f"/api/v1/answers/{a.id}/revise", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["current_version"] == 2

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
