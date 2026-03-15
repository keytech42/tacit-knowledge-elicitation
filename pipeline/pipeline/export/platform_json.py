"""Export questions to platform-compatible JSON format."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import GeneratedQuestion


def export_platform_json(questions: list[GeneratedQuestion], output_path: Path) -> None:
    """Write questions as a JSON array matching the platform import schema."""
    records = []
    for q in questions:
        body = q.body
        if q.evidence:
            body += "\n\n## Evidence\n" + "\n".join(f"- {e}" for e in q.evidence)

        answer_options = [
            {"body": opt, "display_order": i}
            for i, opt in enumerate(q.suggested_options)
        ]

        records.append({
            "title": q.title,
            "body": body,
            "category": q.category,
            "answer_options": answer_options,
            "review_policy": {"min_approvals": 1},
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
