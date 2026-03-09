"""Slack message templates.

Each module exports pure formatting functions that accept typed kwargs
and return the message text(s) to post. No Slack SDK or side-effects here —
just string construction.

This separation makes formats easy to find, edit, test, and eventually localize.
"""

from app.templates.slack.answers import (
    fmt_answer_approved,
    fmt_answer_submitted,
    fmt_revision_requested,
)
from app.templates.slack.assignments import fmt_respondent_assigned, fmt_respondent_assigned_thread
from app.templates.slack.questions import (
    fmt_question_closed,
    fmt_question_published,
    fmt_question_rejected,
)
from app.templates.slack.reviews import (
    fmt_changes_requested_dm,
    fmt_review_verdict,
)

__all__ = [
    "fmt_answer_approved",
    "fmt_answer_submitted",
    "fmt_changes_requested_dm",
    "fmt_question_closed",
    "fmt_question_published",
    "fmt_question_rejected",
    "fmt_respondent_assigned",
    "fmt_respondent_assigned_thread",
    "fmt_review_verdict",
    "fmt_revision_requested",
]
