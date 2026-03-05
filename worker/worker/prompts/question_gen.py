SYSTEM_PROMPT = """\
You are an expert knowledge elicitation specialist. Your role is to generate \
high-quality questions that help capture tacit knowledge from domain experts.

Questions should be:
- Specific enough to elicit concrete, actionable knowledge
- Open-ended enough to allow for nuanced expert responses
- Focused on practical decision-making, trade-offs, and heuristics
- Categorized appropriately for the domain

Each question should include a title (concise summary) and body (detailed question text).\
"""


def build_user_prompt(
    topic: str,
    domain: str,
    count: int,
    existing_categories: list[str],
    existing_questions: list[dict],
    context: str | None = None,
) -> str:
    parts = [f"Generate {count} knowledge elicitation questions about: {topic}"]

    if domain:
        parts.append(f"Domain: {domain}")

    if context:
        parts.append(f"Additional context: {context}")

    if existing_categories:
        parts.append(f"Existing categories in the system: {', '.join(existing_categories)}")
        parts.append("Use existing categories where appropriate, or create new ones if needed.")

    if existing_questions:
        parts.append("\nExisting questions (avoid duplicates):")
        for q in existing_questions[:10]:
            parts.append(f"- {q.get('title', '')}")

    parts.append(
        "\nFor each question, also suggest 2-4 answer options that represent "
        "common expert perspectives or approaches."
    )

    return "\n".join(parts)
