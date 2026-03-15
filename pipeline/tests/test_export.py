"""Tests for export formatters."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from pipeline.export.platform_json import export_platform_json
from pipeline.export.summary_report import export_summary_report
from pipeline.models import (
    Contradiction,
    GeneratedQuestion,
    NormStatement,
    ParsedDocument,
    RunManifest,
    Severity,
    StageResult,
    StageStatus,
)


# --- Platform JSON Export ---


def test_platform_json_produces_valid_json(sample_questions, tmp_path):
    output = tmp_path / "questions.json"
    export_platform_json(sample_questions, output)

    assert output.exists()
    data = json.loads(output.read_text())
    assert isinstance(data, list)
    assert len(data) == 1


def test_platform_json_schema_structure(sample_questions, tmp_path):
    output = tmp_path / "questions.json"
    export_platform_json(sample_questions, output)

    data = json.loads(output.read_text())
    q = data[0]

    assert "title" in q
    assert "body" in q
    assert "category" in q
    assert "answer_options" in q
    assert "review_policy" in q

    assert q["title"] == "How are major hiring decisions actually made?"
    assert q["category"] == "Authority"
    assert q["review_policy"] == {"min_approvals": 1}


def test_platform_json_evidence_in_body(sample_questions, tmp_path):
    output = tmp_path / "questions.json"
    export_platform_json(sample_questions, output)

    data = json.loads(output.read_text())
    body = data[0]["body"]

    assert "## Evidence" in body
    assert "- Lean HR Policy: flat structure" in body
    assert "- Slack: CEO approved Q2 budget" in body


def test_platform_json_answer_options(sample_questions, tmp_path):
    output = tmp_path / "questions.json"
    export_platform_json(sample_questions, output)

    data = json.loads(output.read_text())
    options = data[0]["answer_options"]

    assert len(options) == 3
    assert options[0] == {"body": "CEO decides", "display_order": 0}
    assert options[1] == {"body": "Team consensus", "display_order": 1}
    assert options[2] == {"body": "Department lead recommends, CEO approves", "display_order": 2}


def test_platform_json_empty_questions(tmp_path):
    output = tmp_path / "questions.json"
    export_platform_json([], output)

    data = json.loads(output.read_text())
    assert data == []


def test_platform_json_no_evidence(tmp_path):
    questions = [
        GeneratedQuestion(title="Simple Q", body="Body text", confidence=0.8)
    ]
    output = tmp_path / "questions.json"
    export_platform_json(questions, output)

    data = json.loads(output.read_text())
    assert "## Evidence" not in data[0]["body"]


def test_platform_json_creates_parent_dirs(tmp_path):
    output = tmp_path / "nested" / "dir" / "questions.json"
    export_platform_json([], output)
    assert output.exists()


# --- Summary Report ---


@pytest.fixture
def sample_manifest() -> RunManifest:
    return RunManifest(
        run_id="test-run-001",
        experiment_name="Test Experiment",
        config_file="configs/experiments/test.yaml",
        started_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 3, 15, 10, 5, 30, tzinfo=timezone.utc),
        stages=[
            StageResult(
                name="ingest",
                status=StageStatus.completed,
                started_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 15, 10, 1, 0, tzinfo=timezone.utc),
                item_count=3,
            ),
            StageResult(
                name="norm_extraction",
                status=StageStatus.completed,
                started_at=datetime(2026, 3, 15, 10, 1, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 15, 10, 3, 0, tzinfo=timezone.utc),
                item_count=2,
            ),
            StageResult(
                name="question_generation",
                status=StageStatus.completed,
                started_at=datetime(2026, 3, 15, 10, 3, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 15, 10, 5, 30, tzinfo=timezone.utc),
                item_count=1,
            ),
        ],
    )


def test_summary_report_contains_run_summary(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )

    content = output.read_text()
    assert "# Pipeline Run Summary" in content
    assert "test-run-001" in content
    assert "Test Experiment" in content


def test_summary_report_contains_stage_table(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )

    content = output.read_text()
    assert "## Stage Results" in content
    assert "| Stage | Status | Items | Duration |" in content
    assert "ingest" in content
    assert "norm_extraction" in content
    assert "completed" in content


def test_summary_report_contains_documents(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )

    content = output.read_text()
    assert "## Documents" in content
    assert "Test Document" in content
    assert "text" in content


def test_summary_report_contains_contradictions(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )

    content = output.read_text()
    assert "## Top Contradictions" in content
    assert "[HIGH]" in content
    assert "flat hierarchy" in content


def test_summary_report_contains_questions(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )

    content = output.read_text()
    assert "## Generated Questions" in content
    assert "How are major hiring decisions actually made?" in content
    assert "Authority" in content


def test_summary_report_contradictions_sorted_by_severity(sample_manifest, sample_document, sample_norms, tmp_path):
    contradictions = [
        Contradiction(
            id="c1", norm_a_id="n1", norm_b_id="n2",
            tension_description="Low sev issue", severity=Severity.low, confidence=0.5,
        ),
        Contradiction(
            id="c2", norm_a_id="n1", norm_b_id="n2",
            tension_description="High sev issue", severity=Severity.high, confidence=0.9,
        ),
        Contradiction(
            id="c3", norm_a_id="n1", norm_b_id="n2",
            tension_description="Medium sev issue", severity=Severity.medium, confidence=0.7,
        ),
    ]
    output = tmp_path / "report.md"
    export_summary_report(sample_manifest, [sample_document], sample_norms, contradictions, [], output)

    content = output.read_text()
    high_pos = content.index("[HIGH]")
    medium_pos = content.index("[MEDIUM]")
    low_pos = content.index("[LOW]")
    assert high_pos < medium_pos < low_pos


def test_summary_report_empty_data(sample_manifest, tmp_path):
    output = tmp_path / "report.md"
    export_summary_report(sample_manifest, [], [], [], [], output)

    content = output.read_text()
    assert "No documents ingested." in content
    assert "No contradictions detected." in content
    assert "Generated Questions (0)" in content


def test_summary_report_creates_parent_dirs(
    sample_manifest, sample_document, sample_norms, sample_contradictions, sample_questions, tmp_path
):
    output = tmp_path / "nested" / "dir" / "report.md"
    export_summary_report(
        sample_manifest, [sample_document], sample_norms, sample_contradictions, sample_questions, output
    )
    assert output.exists()
