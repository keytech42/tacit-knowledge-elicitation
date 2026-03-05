SYSTEM_PROMPT = """\
You are a careful and constructive peer reviewer for expert knowledge \
elicitation responses. Your role is to assess whether an answer adequately \
captures useful tacit knowledge.

Review criteria:
- Relevance: Does the answer address the question?
- Completeness: Does it cover key aspects without major gaps?
- Clarity: Is the knowledge expressed clearly and actionably?
- Specificity: Does it contain concrete details vs. vague generalities?

Guidelines:
- Be constructive, not harsh
- Highlight both strengths and areas for improvement
- Never use "rejected" — only "approved" or "changes_requested"
- Include a confidence score (0.0 to 1.0) reflecting how certain you are
- If confidence < 0.6, indicate this clearly — the review may not be submitted\
"""


def build_user_prompt(question: dict, answer: dict) -> str:
    parts = [
        "Review this answer to a knowledge elicitation question:",
        f"\n## Question",
        f"Title: {question['title']}",
        f"Body: {question['body']}",
    ]

    if question.get("category"):
        parts.append(f"Category: {question['category']}")

    parts.extend([
        f"\n## Answer",
        f"Body: {answer['body']}",
    ])

    if answer.get("current_version"):
        parts.append(f"Version: {answer['current_version']}")

    return "\n".join(parts)
