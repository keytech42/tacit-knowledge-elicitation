"""Slack message templates for answer lifecycle events."""


def fmt_answer_submitted(
    author_name: str,
    question_title: str,
    answer_link: str,
) -> str:
    """Notification when an answer is submitted for review."""
    return (
        f":pencil: *Answer submitted* by {author_name}\n"
        f"For question: *{question_title}*\n"
        f"{answer_link}"
    )


def fmt_answer_approved(
    mention: str,
    question_title: str,
    answer_link: str,
) -> str:
    """Notification when an answer reaches approved status."""
    return (
        f":tada: *Answer approved!* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"{answer_link}"
    )


def fmt_revision_requested(
    mention: str,
    question_title: str,
    answer_link: str,
) -> str:
    """Notification when changes are requested on an answer."""
    return (
        f":arrows_counterclockwise: *Revision requested* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"{answer_link} — please revise and resubmit."
    )
