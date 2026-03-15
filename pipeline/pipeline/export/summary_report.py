"""Export a human-readable markdown summary report."""

from __future__ import annotations

from pathlib import Path

from pipeline.models import (
    Contradiction,
    GeneratedQuestion,
    NormStatement,
    ParsedDocument,
    RunManifest,
)


def _format_duration(start, end) -> str:
    if not start or not end:
        return "N/A"
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds}s"


def export_summary_report(
    manifest: RunManifest,
    documents: list[ParsedDocument],
    norms: list[NormStatement],
    contradictions: list[Contradiction],
    questions: list[GeneratedQuestion],
    output_path: Path,
) -> None:
    """Generate a human-readable markdown report."""
    lines: list[str] = []

    # --- Run Summary ---
    lines.append("# Pipeline Run Summary")
    lines.append("")
    lines.append(f"- **Run ID**: {manifest.run_id}")
    lines.append(f"- **Experiment**: {manifest.experiment_name}")
    lines.append(f"- **Started**: {manifest.started_at.isoformat()}")
    completed = manifest.completed_at.isoformat() if manifest.completed_at else "In progress"
    lines.append(f"- **Completed**: {completed}")
    lines.append(f"- **Duration**: {_format_duration(manifest.started_at, manifest.completed_at)}")
    lines.append("")

    # --- Stage Results ---
    lines.append("## Stage Results")
    lines.append("")
    lines.append("| Stage | Status | Items | Duration |")
    lines.append("|-------|--------|-------|----------|")
    for stage in manifest.stages:
        duration = _format_duration(stage.started_at, stage.completed_at)
        lines.append(f"| {stage.name} | {stage.status.value} | {stage.item_count} | {duration} |")
    lines.append("")

    # --- Documents ---
    lines.append("## Documents")
    lines.append("")
    if documents:
        for doc in documents:
            lines.append(f"- **{doc.title}** ({doc.source_type.value}) — {doc.source_path}")
    else:
        lines.append("No documents ingested.")
    lines.append("")

    # --- Norms ---
    lines.append(f"## Norms Extracted ({len(norms)})")
    lines.append("")
    for norm in norms:
        lines.append(f"- [{norm.norm_type.value}] {norm.text} (confidence: {norm.confidence:.2f})")
    lines.append("")

    # --- Top Contradictions ---
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_contradictions = sorted(contradictions, key=lambda c: severity_order.get(c.severity.value, 3))

    lines.append(f"## Top Contradictions ({len(contradictions)})")
    lines.append("")
    if sorted_contradictions:
        for c in sorted_contradictions:
            lines.append(f"- **[{c.severity.value.upper()}]** {c.tension_description} (confidence: {c.confidence:.2f})")
    else:
        lines.append("No contradictions detected.")
    lines.append("")

    # --- Generated Questions ---
    lines.append(f"## Generated Questions ({len(questions)})")
    lines.append("")
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. **{q.title}** — Category: {q.category}, Confidence: {q.confidence:.2f}")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
