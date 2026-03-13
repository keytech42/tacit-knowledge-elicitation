---
description: Rules for the worker service
globs: worker/**
---

# Worker Service

Separate FastAPI service that calls the platform REST API as a service account. Handles LLM-powered tasks via litellm.

## Tasks

- **Question generation**: `POST /tasks/generate-questions`
- **Answer option scaffolding**: `POST /tasks/scaffold-options` — replaces all existing options per run, auto-enables `show_suggestions`
- **Review assistance**: `POST /tasks/review-assist` — confidence threshold 0.6 for auto-submit
- **Question extraction**: `POST /tasks/extract-questions` — two-pass LLM (extract per chunk → consolidate)

## Auto-triggers

When `WORKER_URL` is configured and the corresponding platform setting is enabled:
- Question publish → scaffold options (`auto_scaffold_enabled`)
- Answer submit → review assist (`auto_review_enabled`)

Admins toggle these at runtime via `GET/PUT /api/v1/settings` — no container restart needed.

## Architecture

- `worker/main.py` — FastAPI app with task trigger endpoints + health check
- `worker/platform_client.py` — httpx async client for platform REST API
- `worker/llm.py` — litellm wrapper (structured output + retries)
- `worker/tasks/` — task implementations
- `worker/prompts/` — system/user prompt templates

## Caveats

- In-memory task tracking (dict). Worker restart loses in-flight tasks.
- All backend→worker calls are fire-and-forget (try/except) so worker downtime never blocks API.
