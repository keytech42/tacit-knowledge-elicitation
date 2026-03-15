"""LLM-based semantic deduplication — uses an LLM to detect semantically duplicate questions."""

from __future__ import annotations

import logging
from collections import defaultdict

from pydantic import BaseModel

from pipeline.llm import call_llm
from pipeline.models import GeneratedQuestion
from pipeline.registry import register

logger = logging.getLogger(__name__)


class DedupResult(BaseModel):
    is_duplicate: bool
    confidence: float
    reason: str


@register("dedup", "llm")
class LLMDedup:
    def __init__(self, threshold: float = 0.85, **kwargs):
        self.threshold = threshold

    async def dedup(self, questions: list[GeneratedQuestion]) -> list[GeneratedQuestion]:
        if len(questions) <= 1:
            return list(questions)

        # Group by category to reduce pairwise comparisons
        groups: dict[str, list[int]] = defaultdict(list)
        for i, q in enumerate(questions):
            groups[q.category or "__uncategorized__"].append(i)

        # Track which indices to remove (keep the higher-confidence one)
        removed: set[int] = set()

        for _category, indices in groups.items():
            for i_pos in range(len(indices)):
                idx_a = indices[i_pos]
                if idx_a in removed:
                    continue
                for j_pos in range(i_pos + 1, len(indices)):
                    idx_b = indices[j_pos]
                    if idx_b in removed:
                        continue

                    q_a = questions[idx_a]
                    q_b = questions[idx_b]

                    result = await call_llm(
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a deduplication assistant. Compare two questions "
                                    "and determine if they are semantically duplicates — i.e., "
                                    "they ask essentially the same thing even if worded differently."
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Question A:\nTitle: {q_a.title}\nBody: {q_a.body}\n\n"
                                    f"Question B:\nTitle: {q_b.title}\nBody: {q_b.body}\n\n"
                                    "Are these semantically duplicate questions?"
                                ),
                            },
                        ],
                        response_model=DedupResult,
                    )

                    if result.is_duplicate and result.confidence >= self.threshold:
                        # Remove the one with lower confidence
                        if q_a.confidence >= q_b.confidence:
                            removed.add(idx_b)
                        else:
                            removed.add(idx_a)
                            break  # idx_a is removed, skip remaining comparisons

        return [q for i, q in enumerate(questions) if i not in removed]
