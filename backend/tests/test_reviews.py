from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


class TestReviewCRUD:
    async def test_create_review(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        r = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        assert r.json()["verdict"] == "pending"

    async def test_approve_answer(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review_id}", json={"verdict": "approved"}, headers=auth_header(reviewer_user))
        assert r.status_code == 200
        assert r.json()["verdict"] == "approved"

        # Answer should be approved
        ar = await client.get(f"/api/v1/answers/{a.id}", headers=auth_header(respondent_user))
        assert ar.json()["status"] == "approved"

    async def test_changes_requested(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        r = await client.patch(f"/api/v1/reviews/{review_id}", json={"verdict": "changes_requested", "comment": "Fix typo"}, headers=auth_header(reviewer_user))
        assert r.status_code == 200

        ar = await client.get(f"/api/v1/answers/{a.id}", headers=auth_header(respondent_user))
        assert ar.json()["status"] == "revision_requested"


class TestReviewComments:
    async def test_add_comment(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        r = await client.post(f"/api/v1/reviews/{review_id}/comments", json={"body": "Nice work"}, headers=auth_header(reviewer_user))
        assert r.status_code == 201
        assert r.json()["body"] == "Nice work"

    async def test_threaded_comment(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        review_r = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        review_id = review_r.json()["id"]

        parent = await client.post(f"/api/v1/reviews/{review_id}/comments", json={"body": "Parent"}, headers=auth_header(reviewer_user))
        parent_id = parent.json()["id"]

        reply = await client.post(f"/api/v1/reviews/{review_id}/comments", json={"body": "Reply", "parent_id": parent_id}, headers=auth_header(respondent_user))
        assert reply.status_code == 201
        assert reply.json()["parent_id"] == parent_id


class TestMyReviewQueue:
    async def test_review_queue(self, client: AsyncClient, reviewer_user: User, respondent_user: User, admin_user: User, db):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="Answer", status=AnswerStatus.SUBMITTED.value, current_version=1)
        db.add(a)
        await db.flush()

        await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": str(a.id)}, headers=auth_header(reviewer_user))
        r = await client.get("/api/v1/reviews/my-queue", headers=auth_header(reviewer_user))
        assert r.status_code == 200
        assert len(r.json()) >= 1
