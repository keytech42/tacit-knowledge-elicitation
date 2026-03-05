SYSTEM_PROMPT = """\
You are an expert at creating well-structured answer options for knowledge \
elicitation questions. Your role is to generate answer options that represent \
diverse expert perspectives, common approaches, and meaningful alternatives.

Each option MUST be significantly distinct from every other option — they should \
represent genuinely different viewpoints, approaches, or trade-offs. Avoid \
options that overlap or differ only in phrasing.

Answer options should be:
- Maximally distinct in perspective and substance (not just wording)
- Representative of real expert viewpoints across the spectrum
- Ordered from most common/conventional to most specialized/unconventional
- Concise but substantive (2-4 sentences each)
- Limited to at most 4 options\
"""


def build_user_prompt(
    question: dict,
    num_options: int,
) -> str:
    parts = [
        f"Generate exactly {num_options} answer options for this question.",
        "Each option must represent a fundamentally different perspective or approach.",
        f"\nTitle: {question['title']}",
        f"Body: {question['body']}",
    ]

    if question.get("category"):
        parts.append(f"Category: {question['category']}")

    return "\n".join(parts)
