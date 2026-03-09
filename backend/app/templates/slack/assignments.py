"""Slack message templates for assignment events."""


def fmt_respondent_assigned(
    respondent_name: str,
    assigner_name: str,
    question_title: str,
    question_link: str,
) -> str:
    """DM to respondent when they are assigned to a question."""
    return (
        f":wave: Hi {respondent_name}! {assigner_name} has assigned you to answer a question:\n"
        f"*{question_title}*\n"
        f"{question_link}"
    )


def fmt_respondent_assigned_thread(
    respondent_mention: str,
    assigner_name: str,
) -> str:
    """Thread reply when a respondent is assigned to a question."""
    return f":busts_in_silhouette: {respondent_mention} has been assigned as respondent by {assigner_name}"
