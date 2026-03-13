# Agent Guide

## Project Summary

Knowledge Elicitation Platform — a FastAPI + React app for collaborative question-answer workflows with peer review. PostgreSQL (pgvector), Docker Compose deployment, Alembic migrations.

## Repository Layout

```
backend/          FastAPI API server
  app/api/v1/     Routes (HTTP layer only — no business logic)
  app/services/   Business logic (no HTTP awareness)
  app/models/     SQLAlchemy ORM models and enums
  app/schemas/    Pydantic request/response schemas
  alembic/        Database migrations
  tests/          pytest test suite

worker/           Separate FastAPI service for LLM-powered tasks
frontend/         React SPA (Vite + TypeScript)
backup/           pg_dump scripts and PostgreSQL config
```

## Running Commands

```bash
docker compose up --build                # start services
docker compose exec api pytest -xvs      # run tests
docker compose exec api alembic upgrade head                          # run migrations
docker compose exec api alembic revision --autogenerate -m "desc"     # create migration
docker compose exec web npx tsc -b --noEmit                           # type-check frontend
```

## Key Patterns

### Layer Separation

- **Routes** (`api/v1/`): Parse HTTP, call services, return responses. Use FastAPI deps for auth/DB.
- **Services** (`services/`): Domain logic. Accept `AsyncSession` and models. Never import FastAPI types.
- **Models** (`models/`): Data structure only. No business logic.
- **Schemas** (`schemas/`): API contract. Separate from ORM models.

### Enum Handling

All SQLAlchemy enum columns use `values_callable` to persist lowercase `.value`:

```python
SAEnum(RoleName, name="rolename", values_callable=lambda e: [x.value for x in e])
```

The test `test_model_enum_values_are_lowercase` enforces this. Always run it after enum changes.

### State Machines

Use service functions for state transitions — never set status directly.

- Question: `draft → proposed → in_review → published → closed → archived` (reject: `in_review → draft`)
- Answer: `draft → submitted → under_review → approved/revision_requested/rejected`

### Event Publishing

**Commit before publishing events.** `flush()` writes within a transaction — other sessions can't see it. Publish SSE/Slack/webhooks only after `await db.commit()`.

### Authentication

Three auth methods: JWT bearer token, API key (`X-API-Key`), dev login (`DEV_LOGIN_ENABLED`).
Use `Depends(require_role(RoleName.ADMIN))` for RBAC in routes.

## Workflow

- **Test-first for behavior changes.** Before modifying behavior: find all existing tests that assert on it, update them (xfail if needed), write new tests for new behavior, then implement. Trace all callers of modified interfaces. See `.claude/rules/workflow.md` for the full checklist.
- **One cohesive change per branch and PR.** A branch should tell one story — a feature with its tests and docs, a bug fix, a refactor. The test is: can you summarize the PR in 1-2 sentences without "and also"? If not, split it.
- **Branch before changing code.** Create a descriptive branch (`feat/...`, `fix/...`, `refactor/...`) off `main` before making changes.

## Gotchas

- **Env vars must be forwarded in `docker-compose.yml`** — adding to `config.py` + `.env` isn't enough. Add `${VAR:-}` in the service's `environment:` block.
- Relationships use `lazy="selectin"` — always use it for relationships in API responses to avoid async lazy-load errors.
- Tests use `Base.metadata.create_all()`, not Alembic. Verify migrations match models with `make migrate`.
- `conftest.py` creates pgvector extension before `create_all()` — required for Vector columns.
