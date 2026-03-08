"""
Seed script for dev onboarding and E2E testing.

Populates the database with realistic demo data covering all question and answer states.
Idempotent — safe to run multiple times.

Usage:
    docker compose exec api python scripts/seed.py
"""

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

# Ensure the app module is importable
sys.path.insert(0, "/app")

from app.database import async_session
from app.main import seed_roles
from app.models.user import Role, RoleName, User, UserType, user_roles
from app.models.question import (
    AnswerOption,
    Question,
    QuestionQualityFeedback,
    QuestionStatus,
)
from app.models.answer import Answer, AnswerStatus
from app.models.review import Review, ReviewTargetType, ReviewVerdict
from app.services.question import apply_publish, apply_start_review, apply_submit
from app.services.answer import submit_answer


# ---------------------------------------------------------------------------
# User definitions
# ---------------------------------------------------------------------------
USERS = [
    {
        "email": "admin@example.com",
        "display_name": "Alex Admin",
        "roles": [RoleName.ADMIN, RoleName.AUTHOR],
    },
    {
        "email": "author@example.com",
        "display_name": "Jordan Author",
        "roles": [RoleName.AUTHOR],
    },
    {
        "email": "respondent1@example.com",
        "display_name": "Sam Respondent",
        "roles": [RoleName.RESPONDENT],
    },
    {
        "email": "respondent2@example.com",
        "display_name": "Taylor Respondent",
        "roles": [RoleName.RESPONDENT],
    },
    {
        "email": "reviewer@example.com",
        "display_name": "Casey Reviewer",
        "roles": [RoleName.REVIEWER],
    },
]

# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "key": "draft",
        "title": "What debugging strategies do you use for production issues?",
        "body": (
            "Production debugging is a critical skill. Walk us through your approach "
            "when something breaks in production — how do you triage, investigate, and resolve?\n\n"
            "Consider aspects like log analysis, reproducing issues locally, rollback decisions, "
            "and communication with stakeholders during incidents."
        ),
        "category": "Debugging",
    },
    {
        "key": "proposed",
        "title": "How do you decide when to refactor vs rewrite?",
        "body": (
            "Technical debt accumulates over time. Describe your decision framework "
            "for when code should be incrementally refactored versus fully rewritten.\n\n"
            "What signals tell you a rewrite is necessary? How do you manage risk during "
            "large-scale code changes?"
        ),
        "category": "Architecture",
    },
    {
        "key": "in_review",
        "title": "What's your approach to code review feedback?",
        "body": (
            "Code reviews are essential for quality and knowledge sharing. Share your "
            "approach to both giving and receiving code review feedback.\n\n"
            "How do you balance thoroughness with velocity? How do you handle disagreements "
            "in code reviews?"
        ),
        "category": "Collaboration",
    },
    {
        "key": "published_with_answers",
        "title": "How do you handle knowledge transfer during team transitions?",
        "body": (
            "Team changes are inevitable. Describe your strategies for effective knowledge "
            "transfer when team members join or leave.\n\n"
            "How do you capture tacit knowledge? What documentation practices have you "
            "found most effective? How do you onboard new team members quickly?"
        ),
        "category": "Knowledge Management",
    },
    {
        "key": "published_with_approved",
        "title": "What patterns help you write testable code?",
        "body": (
            "Testability is a design concern. Share the patterns and principles that "
            "guide you toward writing code that is easy to test.\n\n"
            "Consider dependency injection, interface segregation, pure functions, "
            "and how you structure modules for testability."
        ),
        "category": "Testing",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def get_or_create_user(
    session, email: str, display_name: str, role_names: list[RoleName], role_map: dict
) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        print(f"  [skip] User {email} already exists")
        return user

    user = User(
        user_type=UserType.HUMAN.value,
        email=email,
        display_name=display_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # Assign roles via the association table
    for rn in role_names:
        role = role_map[rn.value]
        await session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))

    # Refresh to load roles relationship
    await session.refresh(user, ["roles"])
    print(f"  [created] User {email} with roles {[r.value for r in role_names]}")
    return user


async def get_existing_question(session, title: str) -> Question | None:
    result = await session.execute(select(Question).where(Question.title == title))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------
async def seed():
    print("=== Seeding database ===\n")

    # Ensure roles exist
    print("[1/6] Ensuring roles exist...")
    await seed_roles()

    async with async_session() as session:
        # Load role map
        result = await session.execute(select(Role))
        roles = result.scalars().all()
        role_map = {r.name: r for r in roles}
        print(f"  Roles available: {list(role_map.keys())}\n")

        # --- Users ---
        print("[2/6] Creating users...")
        users = {}
        for u in USERS:
            user = await get_or_create_user(
                session, u["email"], u["display_name"], u["roles"], role_map
            )
            users[u["email"]] = user
        await session.commit()
        # Refresh all users so roles are loaded for service functions
        for u in users.values():
            await session.refresh(u, ["roles"])

        admin = users["admin@example.com"]
        author = users["author@example.com"]
        respondent1 = users["respondent1@example.com"]
        respondent2 = users["respondent2@example.com"]
        reviewer = users["reviewer@example.com"]

        # --- Questions ---
        print(f"\n[3/6] Creating questions...")
        questions = {}
        for q_def in QUESTIONS:
            existing = await get_existing_question(session, q_def["title"])
            if existing:
                print(f"  [skip] Question '{q_def['key']}' already exists")
                questions[q_def["key"]] = existing
                continue

            q = Question(
                title=q_def["title"],
                body=q_def["body"],
                category=q_def["category"],
                created_by_id=author.id,
            )
            session.add(q)
            await session.flush()
            questions[q_def["key"]] = q
            print(f"  [created] Question '{q_def['key']}': {q_def['title'][:50]}...")

        await session.commit()
        # Refresh questions to load relationships
        for q in questions.values():
            await session.refresh(q, ["created_by", "confirmed_by", "answer_options"])

        # --- State transitions ---
        print(f"\n[4/6] Applying state transitions...")

        # Q1: draft — no transitions needed
        q_draft = questions["draft"]
        if q_draft.status == QuestionStatus.DRAFT.value:
            print(f"  [ok] '{q_draft.title[:40]}...' stays in draft")

        # Q2: proposed — submit
        q_proposed = questions["proposed"]
        if q_proposed.status == QuestionStatus.DRAFT.value:
            apply_submit(q_proposed, author)
            print(f"  [transition] '{q_proposed.title[:40]}...' -> proposed")
        else:
            print(f"  [skip] '{q_proposed.title[:40]}...' already {q_proposed.status}")

        # Q3: in_review — submit + start review
        q_in_review = questions["in_review"]
        if q_in_review.status == QuestionStatus.DRAFT.value:
            apply_submit(q_in_review, author)
            apply_start_review(q_in_review, admin)
            print(f"  [transition] '{q_in_review.title[:40]}...' -> in_review")
        else:
            print(f"  [skip] '{q_in_review.title[:40]}...' already {q_in_review.status}")

        # Q4: published (with answers) — submit + review + publish
        q_pub_answers = questions["published_with_answers"]
        if q_pub_answers.status == QuestionStatus.DRAFT.value:
            apply_submit(q_pub_answers, author)
            apply_start_review(q_pub_answers, admin)
            apply_publish(q_pub_answers, admin)
            print(f"  [transition] '{q_pub_answers.title[:40]}...' -> published")
        else:
            print(f"  [skip] '{q_pub_answers.title[:40]}...' already {q_pub_answers.status}")

        # Q5: published (with approved answer) — submit + review + publish
        q_pub_approved = questions["published_with_approved"]
        if q_pub_approved.status == QuestionStatus.DRAFT.value:
            apply_submit(q_pub_approved, author)
            apply_start_review(q_pub_approved, admin)
            apply_publish(q_pub_approved, admin)
            print(f"  [transition] '{q_pub_approved.title[:40]}...' -> published")
        else:
            print(f"  [skip] '{q_pub_approved.title[:40]}...' already {q_pub_approved.status}")

        await session.commit()

        # --- Answer options for published questions ---
        print(f"\n[5/6] Creating answer options, answers, and reviews...")

        # Answer options for Q4
        if not q_pub_answers.answer_options:
            options_q4 = [
                AnswerOption(
                    question_id=q_pub_answers.id,
                    body="Pair programming and shadowing sessions with departing team members",
                    display_order=0,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_answers.id,
                    body="Comprehensive documentation wikis with decision logs",
                    display_order=1,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_answers.id,
                    body="Recorded video walkthroughs of key systems and processes",
                    display_order=2,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_answers.id,
                    body="Structured onboarding checklists with progressive complexity",
                    display_order=3,
                    created_by_id=admin.id,
                ),
            ]
            for opt in options_q4:
                session.add(opt)
            q_pub_answers.show_suggestions = True
            print(f"  [created] 4 answer options for Q4")
        else:
            print(f"  [skip] Q4 answer options already exist")

        # Answer options for Q5 — varied lengths to visually test grid alignment
        if not q_pub_approved.answer_options:
            options_q5 = [
                AnswerOption(
                    question_id=q_pub_approved.id,
                    body=(
                        "Dependency injection and constructor-based wiring — making all external "
                        "dependencies explicit parameters rather than hidden globals or singletons, "
                        "so every collaborator can be replaced with a test double"
                    ),
                    display_order=0,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_approved.id,
                    body="Pure functions with explicit inputs and outputs",
                    display_order=1,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_approved.id,
                    body="Interface segregation and port/adapter patterns",
                    display_order=2,
                    created_by_id=admin.id,
                ),
                AnswerOption(
                    question_id=q_pub_approved.id,
                    body=(
                        "Separating pure business logic from I/O side effects — keep the core "
                        "domain rules in pure functions that are trivial to unit test, and push "
                        "database, HTTP, and file system access to thin adapter layers at the edges"
                    ),
                    display_order=3,
                    created_by_id=admin.id,
                ),
            ]
            for opt in options_q5:
                session.add(opt)
            q_pub_approved.show_suggestions = True
            print(f"  [created] 4 answer options for Q5")
        else:
            print(f"  [skip] Q5 answer options already exist")

        await session.flush()

        # --- Answers for Q4 ---
        result = await session.execute(
            select(Answer).where(Answer.question_id == q_pub_answers.id)
        )
        existing_answers_q4 = result.scalars().all()

        if not existing_answers_q4:
            # Answer 1: by respondent1, submitted + approved
            a1 = Answer(
                question_id=q_pub_answers.id,
                author_id=respondent1.id,
                body=(
                    "In my experience, the most effective knowledge transfer happens through "
                    "a combination of structured documentation and hands-on pairing.\n\n"
                    "When someone is leaving the team, I prioritize:\n"
                    "1. Recording decision logs — capturing *why* things were built a certain way\n"
                    "2. Pair programming on the most critical code paths\n"
                    "3. Creating runbooks for operational procedures\n\n"
                    "The key insight is that tacit knowledge — the stuff people know but can't easily "
                    "articulate — is best transferred through observation and practice, not documents."
                ),
            )
            session.add(a1)
            await session.flush()
            # Refresh to load revisions for submit_answer
            await session.refresh(a1, ["revisions", "author"])
            rev1 = submit_answer(a1, respondent1)
            session.add(rev1)
            await session.flush()

            # Mark as under_review then approved
            a1.status = AnswerStatus.UNDER_REVIEW.value
            await session.flush()

            review_a1 = Review(
                target_type=ReviewTargetType.ANSWER.value,
                target_id=a1.id,
                reviewer_id=reviewer.id,
                assigned_by_id=admin.id,
                verdict=ReviewVerdict.APPROVED.value,
                comment="Excellent answer with practical, actionable advice. The distinction between tacit and explicit knowledge is well articulated.",
                answer_version=a1.current_version,
            )
            session.add(review_a1)

            a1.status = AnswerStatus.APPROVED.value
            a1.confirmed_by_id = reviewer.id
            a1.confirmed_at = datetime.now(timezone.utc)
            print(f"  [created] Answer 1 for Q4 (approved)")

            # Answer 2: by respondent2, submitted + changes_requested
            a2 = Answer(
                question_id=q_pub_answers.id,
                author_id=respondent2.id,
                body=(
                    "Knowledge transfer is mostly about good documentation. When I join a new "
                    "team, I look for README files, architecture diagrams, and API docs.\n\n"
                    "I think the best approach is to write everything down thoroughly."
                ),
            )
            session.add(a2)
            await session.flush()
            await session.refresh(a2, ["revisions", "author"])
            rev2 = submit_answer(a2, respondent2)
            session.add(rev2)
            await session.flush()

            # Mark as under_review then changes_requested
            a2.status = AnswerStatus.UNDER_REVIEW.value
            await session.flush()

            review_a2 = Review(
                target_type=ReviewTargetType.ANSWER.value,
                target_id=a2.id,
                reviewer_id=reviewer.id,
                assigned_by_id=admin.id,
                verdict=ReviewVerdict.CHANGES_REQUESTED.value,
                comment="Good start, but could benefit from more specific examples. What types of documentation have you found most useful? Consider addressing tacit knowledge that is hard to document.",
                answer_version=a2.current_version,
            )
            session.add(review_a2)

            a2.status = AnswerStatus.REVISION_REQUESTED.value
            print(f"  [created] Answer 2 for Q4 (changes requested)")

            # Answer 3: by respondent1, submitted + pending review (for reviewer queue)
            a3_q4 = Answer(
                question_id=q_pub_answers.id,
                author_id=respondent1.id,
                body=(
                    "I've found that the best knowledge transfer combines async documentation "
                    "with synchronous sessions:\n\n"
                    "- **Architecture Decision Records (ADRs)**: Short docs capturing the context, "
                    "options considered, and rationale for key decisions\n"
                    "- **Mob programming sessions**: Whole-team sessions working on unfamiliar code "
                    "areas to spread understanding\n"
                    "- **Rotation schedules**: Regularly rotating who works on which subsystem\n\n"
                    "The underrated practice is *progressive onboarding* — don't dump everything "
                    "on day one. Instead, give new members increasingly complex tasks and let them "
                    "pull knowledge as needed."
                ),
            )
            session.add(a3_q4)
            await session.flush()
            await session.refresh(a3_q4, ["revisions", "author"])
            rev3_q4 = submit_answer(a3_q4, respondent1)
            session.add(rev3_q4)
            await session.flush()

            # Under review with a pending review — this shows up in reviewer's queue
            a3_q4.status = AnswerStatus.UNDER_REVIEW.value
            await session.flush()

            review_a3_q4 = Review(
                target_type=ReviewTargetType.ANSWER.value,
                target_id=a3_q4.id,
                reviewer_id=reviewer.id,
                assigned_by_id=admin.id,
                verdict=ReviewVerdict.PENDING.value,
                answer_version=a3_q4.current_version,
            )
            session.add(review_a3_q4)
            print(f"  [created] Answer 3 for Q4 (pending review)")
        else:
            print(f"  [skip] Q4 answers already exist ({len(existing_answers_q4)})")

        # --- Answer for Q5 ---
        result = await session.execute(
            select(Answer).where(Answer.question_id == q_pub_approved.id)
        )
        existing_answers_q5 = result.scalars().all()

        if not existing_answers_q5:
            a3 = Answer(
                question_id=q_pub_approved.id,
                author_id=respondent1.id,
                body=(
                    "The single most impactful pattern for testability is dependency injection — "
                    "making all external dependencies explicit constructor parameters rather than "
                    "hidden globals.\n\n"
                    "Beyond DI, I follow these principles:\n"
                    "- **Separate pure logic from I/O**: Keep business rules in pure functions that "
                    "are trivial to test\n"
                    "- **Thin adapters**: Database, HTTP, and file system access go through thin "
                    "adapter layers that are easy to mock\n"
                    "- **Small, focused modules**: Each module does one thing, making it easy to "
                    "test in isolation\n\n"
                    "The key insight is that testability is a *design* property — if code is hard "
                    "to test, it usually means the design needs improvement, not that you need "
                    "better testing tools."
                ),
            )
            session.add(a3)
            await session.flush()
            await session.refresh(a3, ["revisions", "author"])
            rev3 = submit_answer(a3, respondent1)
            session.add(rev3)
            await session.flush()

            # Mark as under_review then approved
            a3.status = AnswerStatus.UNDER_REVIEW.value
            await session.flush()

            review_a3 = Review(
                target_type=ReviewTargetType.ANSWER.value,
                target_id=a3.id,
                reviewer_id=reviewer.id,
                assigned_by_id=admin.id,
                verdict=ReviewVerdict.APPROVED.value,
                comment="Clear, well-structured answer with actionable principles. The point about testability being a design property is spot on.",
                answer_version=a3.current_version,
            )
            session.add(review_a3)

            a3.status = AnswerStatus.APPROVED.value
            a3.confirmed_by_id = reviewer.id
            a3.confirmed_at = datetime.now(timezone.utc)
            print(f"  [created] Answer for Q5 (approved)")
        else:
            print(f"  [skip] Q5 answers already exist ({len(existing_answers_q5)})")

        # --- Quality feedback for published questions ---
        print(f"\n[6/6] Creating quality feedback...")

        for q, feedbacks in [
            (q_pub_answers, [
                {"user": admin, "rating": 5, "comment": "Excellent question that captures a real challenge teams face."},
                {"user": respondent1, "rating": 4, "comment": "Very relevant to my experience."},
            ]),
            (q_pub_approved, [
                {"user": admin, "rating": 4, "comment": "Good practical question."},
                {"user": reviewer, "rating": 5, "comment": "Gets to the heart of software design quality."},
            ]),
        ]:
            for fb in feedbacks:
                result = await session.execute(
                    select(QuestionQualityFeedback).where(
                        QuestionQualityFeedback.question_id == q.id,
                        QuestionQualityFeedback.user_id == fb["user"].id,
                    )
                )
                if result.scalar_one_or_none():
                    print(f"  [skip] Feedback from {fb['user'].display_name} on '{q.title[:30]}...' exists")
                    continue
                session.add(QuestionQualityFeedback(
                    question_id=q.id,
                    user_id=fb["user"].id,
                    rating=fb["rating"],
                    comment=fb["comment"],
                ))
                print(f"  [created] Feedback from {fb['user'].display_name} on '{q.title[:30]}...'")

        await session.commit()

    print("\n=== Seed complete ===")
    print("\nDemo accounts (use dev-login):")
    print("  admin@example.com       — Admin + Author")
    print("  author@example.com      — Author")
    print("  respondent1@example.com  — Respondent")
    print("  respondent2@example.com  — Respondent")
    print("  reviewer@example.com     — Reviewer")


if __name__ == "__main__":
    asyncio.run(seed())
