import pytest
from httpx import AsyncClient

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.asyncio


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


class TestSelfReviewDevMode:
    """Self-review gated on DEV_LOGIN_ENABLED — covers create, assign, and full flow."""

    async def test_create_review_self_review_blocked_in_prod(
        self, client: AsyncClient, reviewer_user: User, admin_user: User, db, roles,
    ):
        """Author cannot create a review for their own answer when DEV_LOGIN_ENABLED is off."""
        from app.config import settings
        original = settings.DEV_LOGIN_ENABLED
        settings.DEV_LOGIN_ENABLED = False
        try:
            q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
            db.add(q)
            await db.flush()
            a = Answer(question_id=q.id, author_id=reviewer_user.id, body="A", status=AnswerStatus.SUBMITTED.value, current_version=1)
            db.add(a)
            await db.flush()
            r = await client.post("/api/v1/reviews", json={
                "target_type": "answer", "target_id": str(a.id),
            }, headers=auth_header(reviewer_user))
            assert r.status_code == 409
        finally:
            settings.DEV_LOGIN_ENABLED = original

    async def test_create_review_self_review_allowed_in_dev(
        self, client: AsyncClient, reviewer_user: User, admin_user: User, db, roles,
    ):
        """Author can create a review for their own answer when DEV_LOGIN_ENABLED is on."""
        from app.config import settings
        original = settings.DEV_LOGIN_ENABLED
        settings.DEV_LOGIN_ENABLED = True
        try:
            q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
            db.add(q)
            await db.flush()
            a = Answer(question_id=q.id, author_id=reviewer_user.id, body="A", status=AnswerStatus.SUBMITTED.value, current_version=1)
            db.add(a)
            await db.flush()
            r = await client.post("/api/v1/reviews", json={
                "target_type": "answer", "target_id": str(a.id),
            }, headers=auth_header(reviewer_user))
            assert r.status_code == 201
        finally:
            settings.DEV_LOGIN_ENABLED = original

    async def test_self_review_full_flow(
        self, client: AsyncClient, reviewer_user: User, admin_user: User, db, roles,
    ):
        """End-to-end: author self-assigns, reviews, and approves their own answer in dev mode."""
        from app.config import settings
        original = settings.DEV_LOGIN_ENABLED
        settings.DEV_LOGIN_ENABLED = True
        try:
            q = Question(
                title="Q", body="B", created_by_id=admin_user.id,
                status=QuestionStatus.PUBLISHED.value,
                review_policy={"min_approvals": 1},
            )
            db.add(q)
            await db.flush()
            a = Answer(
                question_id=q.id, author_id=reviewer_user.id,
                body="Self-reviewed answer", status=AnswerStatus.SUBMITTED.value,
                current_version=1,
            )
            db.add(a)
            await db.flush()

            # Step 1: self-assign as reviewer
            assign_r = await client.post(
                f"/api/v1/reviews/assign/{a.id}",
                json={"reviewer_id": str(reviewer_user.id)},
                headers=auth_header(admin_user),
            )
            assert assign_r.status_code == 201
            review_id = assign_r.json()["id"]

            # Step 2: submit approve verdict
            verdict_r = await client.patch(
                f"/api/v1/reviews/{review_id}",
                json={"verdict": "approved", "comment": "Self-approved for testing"},
                headers=auth_header(reviewer_user),
            )
            assert verdict_r.status_code == 200
            assert verdict_r.json()["verdict"] == "approved"

            # Step 3: answer should be approved
            answer_r = await client.get(
                f"/api/v1/answers/{a.id}", headers=auth_header(reviewer_user),
            )
            assert answer_r.json()["status"] == "approved"
        finally:
            settings.DEV_LOGIN_ENABLED = original


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


class TestAssignReviewer:
    """Tests for POST /reviews/assign/{answer_id} — assign a reviewer to an answer."""

    async def _make_answer(self, db, admin_user, respondent_user, status=AnswerStatus.SUBMITTED.value):
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()
        a = Answer(question_id=q.id, author_id=respondent_user.id, body="A", status=status, current_version=1)
        db.add(a)
        await db.flush()
        return a

    async def test_assign_reviewer_happy_path(self, client, admin_user, reviewer_user, respondent_user, db):
        """Admin assigns a reviewer to a submitted answer."""
        a = await self._make_answer(db, admin_user, respondent_user)
        r = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["reviewer"]["id"] == str(reviewer_user.id)
        assert data["assigned_by"]["id"] == str(admin_user.id)
        assert data["verdict"] == "pending"
        assert data["answer_version"] == 1

    async def test_assign_transitions_submitted_to_under_review(self, client, admin_user, reviewer_user, respondent_user, db):
        """Assigning a reviewer to a submitted answer moves it to under_review."""
        a = await self._make_answer(db, admin_user, respondent_user, AnswerStatus.SUBMITTED.value)
        await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        ar = await client.get(f"/api/v1/answers/{a.id}", headers=auth_header(respondent_user))
        assert ar.json()["status"] == "under_review"

    async def test_assign_reviewer_by_reviewer(self, client, admin_user, reviewer_user, respondent_user, db, roles):
        """A reviewer can assign another reviewer (not just admins)."""
        from app.models.user import User, UserType, RoleName
        second_reviewer = User(user_type=UserType.HUMAN, external_id="google_rev2", display_name="Reviewer 2", email="rev2@test.com")
        db.add(second_reviewer)
        await db.flush()
        await db.refresh(second_reviewer, ["roles"])
        second_reviewer.roles.append(roles[RoleName.REVIEWER.value])
        await db.flush()

        a = await self._make_answer(db, admin_user, respondent_user)
        r = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(second_reviewer.id)},
            headers=auth_header(reviewer_user),
        )
        assert r.status_code == 201

    async def test_reject_non_reviewable_answer(self, client, admin_user, reviewer_user, respondent_user, db):
        """Cannot assign reviewer to a draft answer."""
        a = await self._make_answer(db, admin_user, respondent_user, AnswerStatus.DRAFT.value)
        r = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 409

    async def test_reject_self_review(self, client, admin_user, reviewer_user, db):
        """Cannot assign the answer author as reviewer when DEV_LOGIN_ENABLED is off."""
        from app.config import settings
        original = settings.DEV_LOGIN_ENABLED
        settings.DEV_LOGIN_ENABLED = False
        try:
            q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
            db.add(q)
            await db.flush()
            a = Answer(question_id=q.id, author_id=reviewer_user.id, body="A", status=AnswerStatus.SUBMITTED.value, current_version=1)
            db.add(a)
            await db.flush()
            r = await client.post(
                f"/api/v1/reviews/assign/{a.id}",
                json={"reviewer_id": str(reviewer_user.id)},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 409
            assert "author" in r.json()["detail"].lower()
        finally:
            settings.DEV_LOGIN_ENABLED = original

    async def test_allow_self_review_in_dev_mode(self, client, admin_user, reviewer_user, db):
        """Self-review is allowed when DEV_LOGIN_ENABLED is on (test mode)."""
        from app.config import settings
        original = settings.DEV_LOGIN_ENABLED
        settings.DEV_LOGIN_ENABLED = True
        try:
            q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
            db.add(q)
            await db.flush()
            a = Answer(question_id=q.id, author_id=reviewer_user.id, body="A", status=AnswerStatus.SUBMITTED.value, current_version=1)
            db.add(a)
            await db.flush()
            r = await client.post(
                f"/api/v1/reviews/assign/{a.id}",
                json={"reviewer_id": str(reviewer_user.id)},
                headers=auth_header(admin_user),
            )
            assert r.status_code == 201
        finally:
            settings.DEV_LOGIN_ENABLED = original

    async def test_reject_non_reviewer_role(self, client, admin_user, respondent_user, author_user, db):
        """Cannot assign a user who doesn't have the reviewer role."""
        a = await self._make_answer(db, admin_user, respondent_user)
        r = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(author_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 400
        assert "reviewer role" in r.json()["detail"].lower()

    async def test_reject_duplicate_pending_review(self, client, admin_user, reviewer_user, respondent_user, db):
        """Cannot assign the same reviewer twice for the same version."""
        a = await self._make_answer(db, admin_user, respondent_user)
        r1 = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r1.status_code == 201
        r2 = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r2.status_code == 409
        assert "already" in r2.json()["detail"].lower()

    async def test_answer_not_found(self, client, admin_user, reviewer_user):
        """404 for non-existent answer."""
        import uuid
        r = await client.post(
            f"/api/v1/reviews/assign/{uuid.uuid4()}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(admin_user),
        )
        assert r.status_code == 404

    async def test_respondent_cannot_assign(self, client, admin_user, reviewer_user, respondent_user, db):
        """Respondent role cannot assign reviewers."""
        a = await self._make_answer(db, admin_user, respondent_user)
        r = await client.post(
            f"/api/v1/reviews/assign/{a.id}",
            json={"reviewer_id": str(reviewer_user.id)},
            headers=auth_header(respondent_user),
        )
        assert r.status_code == 403
