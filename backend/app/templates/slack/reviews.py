"""Slack message templates for review events."""

_VERDICT_EMOJI = {
    "approved": ":white_check_mark:",
    "changes_requested": ":memo:",
    "rejected": ":no_entry:",
}


def fmt_review_verdict(
    verdict: str,
    reviewer_name: str,
    mention: str,
    question_title: str,
    answer_link: str,
    comment: str | None = None,
) -> str:
    """Notification when a review verdict is submitted."""
    emoji = _VERDICT_EMOJI.get(verdict, ":speech_balloon:")
    text = (
        f"{emoji} *Review: {verdict.replace('_', ' ')}* by {reviewer_name}\n"
        f"For {answer_link} on *{question_title}* — {mention}\n"
    )
    if comment:
        text += f"Comment: {comment}"
    return text


def fmt_reviewer_assigned_dm(
    reviewer_name: str,
    assigner_name: str,
    question_title: str,
    answer_link: str,
) -> str:
    """DM to reviewer when they are assigned to review an answer."""
    return (
        f":mag: Hi {reviewer_name}! {assigner_name} has assigned you to review an answer to *{question_title}*\n"
        f"{answer_link}"
    )


def fmt_changes_requested_dm(
    reviewer_name: str,
    question_title: str,
    answer_link: str,
    comment: str | None = None,
) -> str:
    """DM to answer author when changes are requested."""
    text = (
        f":memo: {reviewer_name} has requested changes on your answer to *{question_title}*\n"
        f"{answer_link}"
    )
    if comment:
        text += f"\nComment: {comment}"
    return text
