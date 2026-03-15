# Tacit Knowledge Mining Pipeline

Automated 4-stage pipeline: ingest sources (Slack JSON, Notion markdown, PDFs, text) → extract organizational norms → detect contradictions → generate evidence-grounded elicitation questions.

## Quick Start

```bash
# Install
cd pipeline && pip install -e ".[dev]"

# Dry run (validates config, creates run directory, no LLM calls)
python -m pipeline.run ../configs/experiments/default.yaml --dry-run

# Full run (requires API key in .env or environment)
ANTHROPIC_API_KEY=sk-... python -m pipeline.run ../configs/experiments/default.yaml
```

## How It Works

```
Sources (Slack, Notion, PDF, text)
  → Stage 1: Ingest & chunk documents
  → Stage 2: Extract norm statements (stated vs. practiced)
  → Stage 3: Detect contradictions between norms
  → Stage 4: Generate elicitation questions grounded in evidence
  → Export: Platform-importable JSON + summary report
```

Each run creates a timestamped directory under `runs/` with:
- `config_snapshot.yaml` — frozen copy of the experiment config
- `stage_1_documents.jsonl` through `stage_4_questions.jsonl` — intermediate outputs
- `export/platform_import.json` — ready for platform import
- `export/report.md` — human-readable summary
- `manifest.json` — timing, counts, status per stage

## Configuration

**"Change config, not code."** All experimental variables live in `configs/`:

- `configs/experiments/*.yaml` — one YAML per experiment (model, temperature, strategies, source paths)
- `configs/prompts/{stage}/system.md` + `user.md.jinja` — Jinja2 prompt templates
- `configs/quality_criteria.yaml` — question scoring weights and thresholds

### Pluggable Strategies

Code-level variation points use a `@register` decorator:

| Category | Strategies | Config key |
|----------|-----------|------------|
| PDF parsing | `pymupdf` (fast, text-layer), `docling` (OCR/scanned) | `sources[].filters.parser` |
| Chunking | `paragraph` (boundary-split), `sliding_window` (overlap) | `chunking.strategy` |
| Dedup | `exact` (title hash), `llm` (semantic) | `dedup.strategy` |

LLM stages are NOT strategies — they share the same code path (`run_llm_stage()`) and differ only in prompts and response models.

## Testing

```bash
cd pipeline && pytest tests/ -xvs
```

All 89 tests run locally with mocked LLM calls. No API keys needed.

### What is tested

- Config loading and validation
- Source ingestion (text, Slack JSON, Notion markdown, PDF) against fixture files in `tests/fixtures/`
- Chunking strategies (paragraph, sliding window) including edge cases
- LLM stage wiring (correct template variables, batching logic, max_items limits)
- Dedup strategies (exact normalization, LLM semantic dedup)
- Export formatters (platform JSON schema, summary report sections)
- Full pipeline end-to-end: ingest → norms → contradictions → questions → export

### What is NOT tested (requires manual validation)

- **Real LLM responses** — prompts have not been validated against a live model. The mocks verify that stages pass correct inputs and handle outputs, but not that prompts produce useful norms/contradictions/questions.
- **Real PDF parsing** — pymupdf is mocked in tests. Install `pymupdf` and test with actual PDFs.
- **Real organizational data** — only minimal fixture files (3 Slack messages, 2 Notion docs, 1 text file).
- **Docling OCR parser** — optional dependency, only the import guard is tested.

To validate prompt quality and end-to-end output, run the pipeline against real source data with a live API key and review the generated questions.

## Architecture

```
pipeline/
  pipeline/
    run.py              CLI entry point
    config.py           ExperimentConfig (Pydantic, loads YAML)
    models.py           Data types: ParsedDocument, NormStatement, Contradiction, GeneratedQuestion
    llm.py              litellm wrapper (adapted from worker/, no settings singleton)
    registry.py         @register decorator + get_strategy()
    ingest/             Source adapters (text, slack, notion, pdf)
    parsers/            PDF parsers (pymupdf, docling)
    chunking/           Text chunkers (paragraph, sliding_window)
    stages/             LLM stages (norm_extraction, contradiction_detection, question_generation)
    dedup/              Dedup strategies (exact, llm)
    export/             Output formatters (platform_json, summary_report)
  tests/                pytest suite with fixtures

configs/
  experiments/          Experiment YAML configs
  prompts/              Jinja2 prompt templates per stage
  quality_criteria.yaml Scoring weights
```
