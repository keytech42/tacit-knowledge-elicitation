SYSTEM_PROMPT = """\
You are an expert at matching questions to the most suitable respondents in a \
knowledge elicitation platform.

Given a question and a list of candidate respondents (with their answer history), \
rank the candidates by how well-suited they are to answer the question.

Consider:
- **Expertise match**: Does the respondent's answer history show relevant domain knowledge?
- **Answer quality**: Has the respondent been approved or had answers rejected?
- **Category experience**: Has the respondent answered questions in the same category?
- **Recency**: Is the respondent recently active on the platform?

Be concise in your reasoning — one sentence per respondent explaining why they are \
or are not a good fit.\
"""


def build_user_prompt(
    question: dict,
    candidates: list[dict],
    top_k: int = 5,
) -> str:
    parts = [
        f"## Question to be answered\n",
        f"**Title:** {question.get('title', 'Untitled')}",
        f"**Body:** {question.get('body', '')}",
    ]
    if question.get("category"):
        parts.append(f"**Category:** {question['category']}")
    parts.append("")

    parts.append(f"## Candidate Respondents ({len(candidates)} total)\n")
    for i, c in enumerate(candidates, 1):
        parts.append(f"### Candidate {i}: {c['display_name']} (ID: {c['user_id']})")
        if c.get("answer_summaries"):
            parts.append("Recent answers:")
            for ans in c["answer_summaries"]:
                status_label = ans.get("status", "unknown")
                parts.append(
                    f"- [{status_label}] Q: \"{ans.get('question_title', '?')}\" "
                    f"(category: {ans.get('category', 'none')})"
                )
        else:
            parts.append("No answer history.")
        parts.append("")

    parts.append(
        f"Select the top {top_k} most suitable respondents. "
        f"If fewer than {top_k} candidates are suitable, return only the suitable ones. "
        f"Score each from 0.0 to 1.0 based on overall fit."
    )

    return "\n".join(parts)
