"""Slack message templates for question lifecycle events."""


def fmt_question_published(
    publisher_name: str,
    question_title: str,
    question_link: str,
) -> str:
    """Thread-starting message when a question is published."""
    return (
        f":clipboard: *New question published* by {publisher_name}\n"
        f"*{question_title}*\n"
        f"{question_link}"
    )


def fmt_question_rejected(
    mention: str,
    question_title: str,
    question_link: str,
    comment: str | None = None,
) -> str:
    """Notification when a question is rejected."""
    text = (
        f":x: *Question rejected* — {mention}\n"
        f"*{question_title}*\n"
        f"{question_link}"
    )
    if comment:
        text += f"\nReason: {comment}"
    return text


def fmt_question_closed(
    question_title: str,
    question_link: str,
) -> str:
    """Thread reply when a question is closed."""
    return (
        f":lock: *Question closed* — *{question_title}*\n"
        f"{question_link}\n"
        f"This question is no longer accepting new answers."
    )
