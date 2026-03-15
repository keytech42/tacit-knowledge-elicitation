"""CLI runner: load config → run stages → save outputs.

Usage:
    python -m pipeline.run configs/experiments/default.yaml
    python -m pipeline.run configs/experiments/default.yaml --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline.config import ExperimentConfig, load_experiment_config
from pipeline.models import (
    Contradiction,
    GeneratedQuestion,
    NormStatement,
    ParsedDocument,
    RunManifest,
    StageResult,
    StageStatus,
)

logger = logging.getLogger(__name__)

# Resolve repo root (pipeline/ is one level up from this file's package)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def create_run_dir(config: ExperimentConfig, base_dir: Path | None = None) -> Path:
    """Create a timestamped run directory and snapshot the config."""
    base = base_dir or (REPO_ROOT / config.output.base_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = base / f"{timestamp}-{config.experiment_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "export").mkdir(exist_ok=True)

    # Snapshot config
    snapshot_path = run_dir / "config_snapshot.yaml"
    with open(snapshot_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, allow_unicode=True)

    return run_dir


def save_jsonl(items: list, path: Path) -> None:
    """Save a list of Pydantic models as JSONL."""
    with open(path, "w") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def save_manifest(manifest: RunManifest, run_dir: Path) -> None:
    """Save run manifest as JSON."""
    with open(run_dir / "manifest.json", "w") as f:
        f.write(manifest.model_dump_json(indent=2))


async def run_pipeline(config: ExperimentConfig, config_path: str, dry_run: bool = False) -> Path:
    """Execute the full pipeline."""
    run_dir = create_run_dir(config)
    run_id = run_dir.name

    manifest = RunManifest(
        run_id=run_id,
        experiment_name=config.experiment_name,
        config_file=config_path,
        started_at=datetime.now(timezone.utc),
    )

    logger.info(f"Run directory: {run_dir}")

    if dry_run:
        logger.info("Dry run — config validated, run directory created. Exiting.")
        manifest.stages = [
            StageResult(name=name, status=StageStatus.skipped)
            for name in ["ingest", "norm_extraction", "contradiction_detection", "question_generation"]
        ]
        manifest.completed_at = datetime.now(timezone.utc)
        save_manifest(manifest, run_dir)
        return run_dir

    # --- Stage 1: Ingest ---
    stage1 = StageResult(name="ingest", status=StageStatus.running, started_at=datetime.now(timezone.utc))
    manifest.stages.append(stage1)
    try:
        from pipeline.ingest.runner import run_ingest
        documents = run_ingest(config)
        save_jsonl(documents, run_dir / "stage_1_documents.jsonl")
        stage1.status = StageStatus.completed
        stage1.item_count = len(documents)
        manifest.totals["documents"] = len(documents)
    except Exception as e:
        stage1.status = StageStatus.failed
        stage1.error = str(e)
        logger.exception("Stage 1 (ingest) failed")
        save_manifest(manifest, run_dir)
        raise
    finally:
        stage1.completed_at = datetime.now(timezone.utc)

    # --- Stage 2: Norm Extraction ---
    stage2 = StageResult(name="norm_extraction", status=StageStatus.running, started_at=datetime.now(timezone.utc))
    manifest.stages.append(stage2)
    try:
        from pipeline.stages.norm_extraction import extract_norms
        norms = await extract_norms(documents, config)
        save_jsonl(norms, run_dir / "stage_2_norms.jsonl")
        stage2.status = StageStatus.completed
        stage2.item_count = len(norms)
        manifest.totals["norms"] = len(norms)
    except Exception as e:
        stage2.status = StageStatus.failed
        stage2.error = str(e)
        logger.exception("Stage 2 (norm extraction) failed")
        save_manifest(manifest, run_dir)
        raise
    finally:
        stage2.completed_at = datetime.now(timezone.utc)

    # --- Stage 3: Contradiction Detection ---
    stage3 = StageResult(name="contradiction_detection", status=StageStatus.running, started_at=datetime.now(timezone.utc))
    manifest.stages.append(stage3)
    try:
        from pipeline.stages.contradiction_detection import detect_contradictions
        contradictions = await detect_contradictions(norms, config)
        save_jsonl(contradictions, run_dir / "stage_3_contradictions.jsonl")
        stage3.status = StageStatus.completed
        stage3.item_count = len(contradictions)
        manifest.totals["contradictions"] = len(contradictions)
    except Exception as e:
        stage3.status = StageStatus.failed
        stage3.error = str(e)
        logger.exception("Stage 3 (contradiction detection) failed")
        save_manifest(manifest, run_dir)
        raise
    finally:
        stage3.completed_at = datetime.now(timezone.utc)

    # --- Stage 4: Question Generation ---
    stage4 = StageResult(name="question_generation", status=StageStatus.running, started_at=datetime.now(timezone.utc))
    manifest.stages.append(stage4)
    try:
        from pipeline.stages.question_generation import generate_questions
        questions = await generate_questions(contradictions, norms, config)

        # Dedup
        from pipeline.dedup.runner import run_dedup
        questions = await run_dedup(questions, config)

        save_jsonl(questions, run_dir / "stage_4_questions.jsonl")
        stage4.status = StageStatus.completed
        stage4.item_count = len(questions)
        manifest.totals["questions"] = len(questions)
    except Exception as e:
        stage4.status = StageStatus.failed
        stage4.error = str(e)
        logger.exception("Stage 4 (question generation) failed")
        save_manifest(manifest, run_dir)
        raise
    finally:
        stage4.completed_at = datetime.now(timezone.utc)

    # --- Export ---
    try:
        from pipeline.export.platform_json import export_platform_json
        from pipeline.export.summary_report import export_summary_report
        export_platform_json(questions, run_dir / "export" / "platform_import.json")
        export_summary_report(manifest, documents, norms, contradictions, questions, run_dir / "export" / "report.md")
    except Exception:
        logger.exception("Export failed (non-fatal)")

    manifest.completed_at = datetime.now(timezone.utc)
    save_manifest(manifest, run_dir)
    logger.info(f"Pipeline complete. Results in {run_dir}")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the tacit knowledge mining pipeline")
    parser.add_argument("config", help="Path to experiment YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and create run dir only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_experiment_config(args.config)
    logger.info(f"Loaded experiment: {config.experiment_name}")

    run_dir = asyncio.run(run_pipeline(config, args.config, dry_run=args.dry_run))
    print(f"\nRun directory: {run_dir}")


if __name__ == "__main__":
    main()
