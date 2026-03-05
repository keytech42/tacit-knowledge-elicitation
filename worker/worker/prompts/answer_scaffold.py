SYSTEM_PROMPT = """\
You are an expert at creating well-structured answer options for knowledge \
elicitation questions. Your role is to generate answer options that represent \
diverse expert perspectives, common approaches, and meaningful alternatives.

Answer options should be:
- Distinct and non-overlapping
- Representative of real expert viewpoints
- Ordered from most common/conventional to most specialized/unconventional
- Written clearly and concisely\
"""


def build_user_prompt(
    question: dict,
    num_options: int,
    existing_options: list[dict],
) -> str:
    parts = [
        f"Generate {num_options} answer options for this question:",
        f"\nTitle: {question['title']}",
        f"Body: {question['body']}",
    ]

    if question.get("category"):
        parts.append(f"Category: {question['category']}")

    if existing_options:
        parts.append("\nExisting options (do not duplicate):")
        for opt in existing_options:
            parts.append(f"- {opt.get('body', '')}")

    return "\n".join(parts)
