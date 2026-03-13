"""Activity timeline endpoint tests."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerStatus
from app.models.question import Question, QuestionStatus
from app.models.user import User
from tests.conftest import auth_header


@pytest.mark.asyncio
class TestActivityTimeline:

    async def test_draft_empty_timeline(self, client: AsyncClient, respondent_user: User, admin_user: User, db: AsyncSession):
        """Draft answer with no revisions has empty events."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Draft"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        assert r.status_code == 200
        assert r.json()["events"] == []
        assert r.json()["current_version"] == 0
        assert r.json()["answer_status"] == "draft"

    async def test_single_submit_timeline(self, client: AsyncClient, respondent_user: User, admin_user: User, db: AsyncSession):
        """Submit creates one version_submitted event."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Content"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 1
        assert events[0]["type"] == "version_submitted"
        assert events[0]["version"] == 1
        assert events[0]["trigger"] == "initial_submit"
        assert events[0]["actor"]["id"] == str(respondent_user.id)

    async def test_full_lifecycle_timeline(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db: AsyncSession):
        """Submit -> assign reviewer -> verdict -> edit -> resubmit produces correct event sequence."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()

        # Submit v1
        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "V1 content"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Assign reviewer (self-assign via POST /reviews)
        rv = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))
        review_id = rv.json()["id"]

        # Submit verdict
        await client.patch(f"/api/v1/reviews/{review_id}", json={"verdict": "changes_requested", "comment": "Fix it"}, headers=auth_header(reviewer_user))

        # Edit and resubmit
        await client.patch(f"/api/v1/answers/{a_id}", json={"body": "V2 content"}, headers=auth_header(respondent_user))
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        assert r.status_code == 200
        events = r.json()["events"]

        # 4 events total: 2 version_submitted, 1 reviewer_assigned, 1 review_submitted
        from collections import Counter
        type_counts = Counter(e["type"] for e in events)
        assert type_counts == {"version_submitted": 2, "reviewer_assigned": 1, "review_submitted": 1}

        # Check version events
        version_events = [e for e in events if e["type"] == "version_submitted"]
        versions = sorted(version_events, key=lambda e: e["version"])
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[1]["trigger"] == "revision_after_review"

        # Check review events
        assigned = [e for e in events if e["type"] == "reviewer_assigned"][0]
        assert assigned["reviewer"]["id"] == str(reviewer_user.id)
        submitted = [e for e in events if e["type"] == "review_submitted"][0]
        assert submitted["verdict"] == "changes_requested"
        assert submitted["comment"] == "Fix it"

    async def test_stale_review_flag(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db: AsyncSession):
        """After resubmit, old review's is_stale is True."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "V1"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        rv = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))
        await client.patch(f"/api/v1/reviews/{rv.json()['id']}", json={"verdict": "changes_requested"}, headers=auth_header(reviewer_user))

        await client.patch(f"/api/v1/answers/{a_id}", json={"body": "V2"}, headers=auth_header(respondent_user))
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        review_events = [e for e in r.json()["events"] if e["type"] == "review_submitted"]
        assert len(review_events) == 1
        assert review_events[0]["is_stale"] is True
        assert review_events[0]["answer_version"] == 1

    async def test_include_diffs_false(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db: AsyncSession):
        """Without include_diffs, diff fields are null."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "V1"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        rv = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))
        await client.patch(f"/api/v1/reviews/{rv.json()['id']}", json={"verdict": "changes_requested"}, headers=auth_header(reviewer_user))

        await client.patch(f"/api/v1/answers/{a_id}", json={"body": "V2"}, headers=auth_header(respondent_user))
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        version_events = [e for e in r.json()["events"] if e["type"] == "version_submitted"]
        for ev in version_events:
            assert ev["diff"] is None

    async def test_include_diffs_true(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db: AsyncSession):
        """With include_diffs=true, v2 event has unified diff text."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value, review_policy={"min_approvals": 1})
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "First version"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        rv = await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))
        await client.patch(f"/api/v1/reviews/{rv.json()['id']}", json={"verdict": "changes_requested"}, headers=auth_header(reviewer_user))

        await client.patch(f"/api/v1/answers/{a_id}", json={"body": "Second version"}, headers=auth_header(respondent_user))
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", params={"include_diffs": "true"}, headers=auth_header(respondent_user))
        version_events = [e for e in r.json()["events"] if e["type"] == "version_submitted"]
        assert version_events[0]["diff"] is None  # v1 has no previous
        assert version_events[1]["diff"] is not None
        assert "First version" in version_events[1]["diff"]
        assert "Second version" in version_events[1]["diff"]

    async def test_activity_not_found(self, client: AsyncClient, respondent_user: User, db: AsyncSession):
        """Activity endpoint returns 404 for nonexistent answer."""
        import uuid
        fake_id = str(uuid.uuid4())
        r = await client.get(f"/api/v1/answers/{fake_id}/activity", headers=auth_header(respondent_user))
        assert r.status_code == 404

    async def test_self_assigned_review(self, client: AsyncClient, respondent_user: User, reviewer_user: User, admin_user: User, db: AsyncSession):
        """Reviewer creates review directly (POST /reviews) -> self_assigned is True."""
        q = Question(title="Q", body="B", created_by_id=admin_user.id, status=QuestionStatus.PUBLISHED.value)
        db.add(q)
        await db.flush()

        r = await client.post(f"/api/v1/questions/{q.id}/answers", json={"body": "Content"}, headers=auth_header(respondent_user))
        a_id = r.json()["id"]
        await client.post(f"/api/v1/answers/{a_id}/submit", headers=auth_header(respondent_user))

        # Self-assign (POST /reviews without assigned_by)
        await client.post("/api/v1/reviews", json={"target_type": "answer", "target_id": a_id}, headers=auth_header(reviewer_user))

        r = await client.get(f"/api/v1/answers/{a_id}/activity", headers=auth_header(respondent_user))
        assigned_events = [e for e in r.json()["events"] if e["type"] == "reviewer_assigned"]
        assert len(assigned_events) == 1
        assert assigned_events[0]["self_assigned"] is True
