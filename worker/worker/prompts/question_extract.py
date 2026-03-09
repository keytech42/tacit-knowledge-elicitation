SYSTEM_PROMPT = """\
You are an expert at analyzing documents to identify tacit and explicit knowledge. \
Your task is to extract knowledge elicitation questions from source material.

For each question:
- Formulate a clear title (concise summary) and detailed body that would prompt \
an expert to articulate the knowledge
- Identify the category of knowledge
- Include the relevant source passage verbatim
- Rate your confidence (0.0–1.0) that this passage contains valuable tacit knowledge
- Optionally suggest 2–4 answer options representing common expert perspectives

Focus on:
- Decision-making heuristics and trade-offs
- Implicit assumptions and mental models
- Practical know-how that is rarely documented
- Edge cases and failure modes experts watch for\
"""

CONSOLIDATION_SYSTEM_PROMPT = """\
You are consolidating extracted questions from multiple document sections.

Your tasks:
- Remove duplicate or near-duplicate questions
- Merge overlapping questions into stronger, more comprehensive ones
- Rank by quality and coverage of the source material
- Trim to the requested count, keeping the highest-value questions
- Preserve the source_passage verbatim from the original extraction
- Write a brief document_summary capturing the key themes of the source material\
"""


def build_extraction_prompt(
    chunk: str,
    domain: str,
    existing_questions: list[dict],
    chunk_index: int,
    total_chunks: int,
) -> str:
    parts = [
        f"Extract knowledge elicitation questions from the following document "
        f"section ({chunk_index}/{total_chunks})."
    ]

    if domain:
        parts.append(f"Domain: {domain}")

    if existing_questions:
        parts.append("\nExisting questions in the system (avoid duplicates):")
        for q in existing_questions[:15]:
            parts.append(f"- {q.get('title', '')}")

    parts.append("\n--- SOURCE TEXT ---")
    parts.append(chunk)
    parts.append("--- END SOURCE TEXT ---")

    parts.append(
        "\nExtract as many high-quality knowledge elicitation questions as you can "
        "from this section. Also provide a brief document_summary of this section."
    )

    return "\n".join(parts)


def build_consolidation_prompt(
    candidates: list,
    max_questions: int,
    existing_questions: list[dict],
) -> str:
    parts = [
        f"Consolidate the following {len(candidates)} extracted questions down to "
        f"at most {max_questions}, keeping the highest-quality ones."
    ]

    if existing_questions:
        parts.append("\nExisting questions in the system (avoid duplicates):")
        for q in existing_questions[:15]:
            parts.append(f"- {q.get('title', '')}")

    parts.append("\n--- CANDIDATE QUESTIONS ---")
    for i, q in enumerate(candidates):
        entry = f"\n{i + 1}. Title: {q.title}\n   Body: {q.body}"
        entry += f"\n   Category: {q.category}"
        entry += f"\n   Source passage: {q.source_passage}"
        entry += f"\n   Confidence: {q.confidence}"
        if q.suggested_options:
            entry += f"\n   Options: {'; '.join(q.suggested_options)}"
        parts.append(entry)
    parts.append("\n--- END CANDIDATES ---")

    parts.append(
        "\nReturn the consolidated set with duplicates removed, overlapping questions "
        "merged, and results ranked by quality. Include a document_summary that "
        "covers the overall source material."
    )

    return "\n".join(parts)
