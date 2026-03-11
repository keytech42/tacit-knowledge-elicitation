# Agent Guide

Instructions for AI agents working on this codebase.

## Project Summary

Knowledge Elicitation Platform — a FastAPI + React app for collaborative question-answer workflows with peer review. PostgreSQL database, Docker Compose deployment, Alembic migrations.

## Repository Layout

```
backend/
  app/api/v1/       Routes (HTTP layer only — no business logic here)
  app/services/     Business logic (no HTTP awareness — receives db sessions and models)
  app/models/       SQLAlchemy ORM models and enums
  app/schemas/      Pydantic request/response schemas
  app/middleware/    AI logging middleware
  app/config.py     Settings from environment (pydantic-settings)
  app/database.py   Async engine and session factory
  app/main.py       App creation, lifespan hooks, middleware stack
  alembic/          Database migrations
  tests/            pytest test suite

worker/
  worker/main.py          FastAPI app — task trigger endpoints + health check
  worker/config.py        WorkerSettings (pydantic-settings)
  worker/platform_client.py  httpx async client for platform REST API
  worker/llm.py           litellm wrapper (structured output + retries)
  worker/tasks/           Task implementations (question_gen, answer_scaffold, review_assist)
  worker/prompts/         System/user prompt templates
  worker/schemas.py       Pydantic models for LLM structured outputs

frontend/
  src/api/          HTTP client (fetch wrapper with JWT)
  src/auth/         Auth context and login page
  src/components/   Layout, route guards
  src/pages/        Feature pages

backup/
  backup.sh           Automated pg_dump with rotation (7 daily, 4 weekly)
  restore.sh          Restore from backup file with verification
  verify.sh           Restore to temp DB and validate table counts
  postgresql.conf     Tuned PostgreSQL config (WAL archiving, checkpoints)

scripts/
  check-env.sh        Production pre-flight checks (rejects default credentials)

docker-compose.yml       Five services: db, api, web, worker, backup
docker-compose.prod.yml  Production overrides (resource limits, no bind mounts, log rotation)
Makefile                 Development shortcuts
```

## Running Commands

```bash
# Start services
docker compose up --build

# Run tests
docker compose exec api pytest -xvs

# Run specific tests
docker compose exec api pytest tests/test_questions.py -xvs

# Run migrations
docker compose exec api alembic upgrade head

# Create migration after model changes
docker compose exec api alembic revision --autogenerate -m "description"

# Type-check frontend (matches CI — catches errors vite dev silently ignores)
docker compose exec web npx tsc -b --noEmit
```

## Key Patterns

### Backend Layers

Keep these layers separate:

- **Routes** (`api/v1/`): Parse HTTP requests, call services, return responses. Use FastAPI dependencies for auth and DB sessions.
- **Services** (`services/`): Domain logic — state transitions, permission checks, validation. Accept `AsyncSession` and model instances. Never import FastAPI types.
- **Models** (`models/`): Data structure only. No business logic. Enums defined alongside their models.
- **Schemas** (`schemas/`): API contract. Separate from ORM models.

### Enum Handling

All SQLAlchemy enum columns use `values_callable` to persist lowercase `.value` (not uppercase `.name`):

```python
SAEnum(RoleName, name="rolename", values_callable=lambda e: [x.value for x in e])
```

This matches the Alembic migration which defines PostgreSQL enums with lowercase values. The test `test_model_enum_values_are_lowercase` enforces this.

### Database Sessions

Use the `get_db` dependency for routes. It auto-commits on success and rolls back on exception.

Tests use transaction-per-test with savepoint rollback (see `conftest.py`). The test database is `knowledge_elicitation_test`.

### Authentication

Three auth methods:
- JWT bearer token (`Authorization: Bearer <token>`) for human users
- API key (`X-API-Key: <key>`) for service accounts
- Dev login (`POST /auth/dev-login`) when `DEV_LOGIN_ENABLED` is true (the default)

Use `Depends(require_role(RoleName.ADMIN))` for role-based access control in routes.

### State Machines

Questions and answers follow strict state machines enforced in `services/question.py` and `services/answer.py`. Always use the service functions for state transitions — never set status directly.

Question: `draft → proposed → in_review → published → closed → archived` (reject sends `in_review → draft`)

Answer: `draft → submitted → under_review → approved/revision_requested/rejected` (revise sends `approved → submitted`)

## Testing

### Running

```bash
docker compose exec api pytest -xvs
```

Python 3.12 is required. Tests cannot run outside Docker without it.

### Test Structure

- `conftest.py`: Fixtures for db sessions, HTTP client, user/role factories. Enables the `vector` pgvector extension before creating tables.
- Each test file covers one domain: `test_admin_queue.py`, `test_ai_integration.py`, `test_ai_logging.py`, `test_ai_tasks.py`, `test_answer_options.py`, `test_answers.py`, `test_auth.py`, `test_config_integrity.py`, `test_e2e_workflows.py`, `test_event_bus.py`, `test_export.py`, `test_file_parser.py`, `test_fix_integration.py`, `test_permissions.py`, `test_questions.py`, `test_recommendation.py`, `test_respondent_assignment.py`, `test_respondent_pool.py`, `test_reviews.py`, `test_slack_dm.py`, `test_slack_threads.py`, `test_slack.py`, `test_source_documents.py`, `test_sse.py`, `test_startup.py`, `test_state_consistency.py`

### Writing Tests

Use the fixtures from `conftest.py`:
- `client` — async HTTP client with dependency overrides
- `db` — async session with auto-rollback
- `admin_user`, `author_user`, `respondent_user`, `reviewer_user` — pre-configured users
- `roles` — dict of all Role objects
- `auth_header(user)` — returns `{"Authorization": "Bearer <jwt>"}` dict
- `service_user` — returns `(User, api_key)` tuple for service account tests
- `api_key_header(api_key)` — returns `{"X-API-Key": key}` dict

Example:
```python
@pytest.mark.asyncio
async def test_create_question(client, author_user):
    resp = await client.post("/api/v1/questions", json={
        "title": "Test", "body": "Body text"
    }, headers=auth_header(author_user))
    assert resp.status_code == 200
```

### Important Test Caveats

- Tests use `Base.metadata.create_all()`, not Alembic migrations. If you add a migration, verify it matches the model by running `make migrate` in Docker.
- HTTPX's `ASGITransport` does not trigger FastAPI lifespan events. The `seed_roles()` function is tested separately in `test_startup.py`.
- The `test_model_enum_values_are_lowercase` parametrized test catches enum value mismatches between models and migrations. Always run this after adding or modifying enums.

## Common Tasks

### Add a new API endpoint

1. Define Pydantic schemas in `app/schemas/`
2. Add business logic in `app/services/` if needed
3. Create the route in `app/api/v1/`, use `Depends(get_db)` and `Depends(require_role(...))`
4. Write tests using the `client` fixture

### Add a new database model

1. Create model in `app/models/` using `UUIDMixin`, `TimestampMixin`, `Base`
2. Import in `app/models/__init__.py`
3. If using enums: use `values_callable` on SAEnum, and use lowercase values
4. Create migration: `docker compose exec api alembic revision --autogenerate -m "add_tablename"`
5. Verify enum values in the generated migration match the model

### Modify an enum

1. Update the Python enum class
2. Update the SAEnum column (keep `values_callable`)
3. Create a migration with `op.execute("ALTER TYPE ... ADD VALUE ...")`
4. Run `test_model_enum_values_are_lowercase` to verify consistency

### Frontend changes

- API functions: `frontend/src/api/client.ts`
- New pages: `frontend/src/pages/`, add route in `App.tsx`
- Auth changes: `frontend/src/auth/AuthContext.tsx`

### Worker Service

The worker is a separate FastAPI service that calls the platform REST API as a service account. It handles LLM-powered tasks:

- **Question generation**: `POST /tasks/generate-questions` — generates elicitation questions for a topic
- **Answer option scaffolding**: `POST /tasks/scaffold-options` — generates up to 4 maximally distinct answer options for a question. Each run replaces all existing options (delete + recreate). The question's `show_suggestions` flag is auto-enabled after scaffolding.
- **Review assistance**: `POST /tasks/review-assist` — AI-assisted preliminary review with confidence threshold (only submits if confidence >= 0.6)

The backend proxies trigger requests via `POST /api/v1/ai/*` endpoints (admin-only). Auto-triggers fire on question publish (scaffold options) and answer submit (review assist) when `WORKER_URL` is configured.

Backend services for the worker integration:
- `app/services/worker_client.py` — fire-and-forget HTTP calls to worker (wrapped in try/except)
- `app/services/embeddings.py` — embedding generation via litellm (optional, guarded by `EMBEDDING_MODEL`)
- `app/services/recommendation.py` — respondent recommendation (pgvector cosine similarity or LLM-based via worker, controlled by `RECOMMENDATION_STRATEGY`)

### Recommendation Strategy

| Strategy | Set in `.env` | What it does | Requirements |
|----------|--------------|--------------|--------------|
| `auto` (default) | `RECOMMENDATION_STRATEGY=auto` | Uses embeddings if `EMBEDDING_MODEL` is set, otherwise falls back to LLM | Either embedding or worker infra |
| `llm` | `RECOMMENDATION_STRATEGY=llm` | Sends candidate answer history to Haiku for scoring | `WORKER_URL` + `ANTHROPIC_API_KEY` |
| `embedding` | `RECOMMENDATION_STRATEGY=embedding` | pgvector cosine similarity on answer embeddings | `EMBEDDING_MODEL` + embedding server |

**Quickest setup** (no GPU needed): set `RECOMMENDATION_STRATEGY=llm` and configure `WORKER_URL` + `ANTHROPIC_API_KEY`. The worker defaults to `anthropic/claude-haiku-4-5-20251001` — override with `RECOMMENDATION_MODEL` if desired.

### Embeddings and pgvector

The Question and Answer models have optional `embedding` columns (`Vector(1024)`) backed by pgvector with hnsw indexes. Embeddings are generated via litellm when `EMBEDDING_MODEL` is set to a non-empty value.

**Model**: bge-m3 (1024 dimensions, 8K context, excellent English + Korean support).

**Inference engines**:
- **Docker Compose (CPU)**: `make up-embed` starts the `embedding` service (llama.cpp server, CPU-only). Model GGUF must be downloaded first via `make embed-download`.
- **macOS dev (Metal GPU)**: Run llama-server natively on host (Docker on macOS cannot access Metal GPU). Use `host.docker.internal` in `EMBEDDING_API_BASE`.
- **Linux GPU**: Use `ghcr.io/ggml-org/llama.cpp:server-cuda` or HuggingFace TEI via `docker-compose.override.yml`.

**litellm config**: Use `openai/` prefix with `api_base` pointing to the embedding server:
```
# Docker Compose (embedding service on compose network)
EMBEDDING_MODEL=openai/bge-m3
EMBEDDING_API_BASE=http://embedding:8090/v1/
EMBEDDING_API_KEY=no-key

# macOS dev (host-side llama-server)
EMBEDDING_API_BASE=http://host.docker.internal:8090/v1/
```

For cloud providers, use the provider's model name directly (e.g., `text-embedding-3-small` for OpenAI).

### Event Publishing and Transaction Ordering

**Never publish an event that triggers external reads of your data before the transaction is committed.**

`flush()` writes to the database within a transaction — other sessions can't see it under PostgreSQL's READ COMMITTED isolation. If you publish an SSE event (or webhook, WebSocket message, etc.) after `flush()` but before `commit()`, the recipient will re-fetch and read stale data.

```python
# WRONG — event fires before commit, re-fetch sees old data
await db.flush()
publish_event(channel, {"type": "status_changed", ...})
await slack.notify(...)  # slow — gives browser time to re-fetch stale data
return response  # get_db auto-commits here, too late

# RIGHT — commit first, then publish
await db.flush()
await db.commit()
publish_event(channel, {"type": "status_changed", ...})
await slack.notify(...)
return response
```

This is especially dangerous with in-process pub/sub (like `asyncio.Queue`) because events are delivered instantly — there's zero network latency to mask the race. External brokers (Redis, RabbitMQ) may hide the bug with slight delivery delay, making it even harder to diagnose when it surfaces.

The `get_db` dependency auto-commits after the handler returns. Calling `commit()` mid-handler is safe — the subsequent auto-commit is a no-op if no new changes were made.

### Backup & Restore

Automated backups run daily via a `backup` sidecar service (pg_dump to `/backups` volume). Scripts in `backup/`:

```bash
make backup        # trigger manual backup now
make restore       # restore from latest (or specify file)
make backup-verify # verify latest backup (restore to temp DB, check tables)
```

Backups rotate: 7 daily, 4 weekly (Sunday tagged). Weekly backups use hard-links to avoid doubling storage. WAL archiving is enabled in production via `backup/postgresql.conf` (mounted in `docker-compose.prod.yml`).

### Production Deployment

```bash
./scripts/check-env.sh                                                    # validate env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build  # start prod
curl http://localhost:8000/health/db | jq .                               # verify
```

`docker-compose.prod.yml` overrides: removes `--reload` and bind mounts, adds `--workers 2`, resource limits, log rotation, and mounts `backup/postgresql.conf`. `scripts/check-env.sh` rejects default `DB_PASSWORD`, `JWT_SECRET`, and `DEV_LOGIN_ENABLED=true`.

### Data Export

Three admin-only streaming JSONL endpoints for ML consumption:

- `GET /api/v1/export/training-data` — Q&A pairs with review verdicts (filters: date, status, category)
- `GET /api/v1/export/embeddings` — 1024-dim entity embeddings (filters: entity_type, date)
- `GET /api/v1/export/review-pairs` — answer-review pairs for RLHF (filters: verdict, date)

Implementation: `backend/app/api/v1/export.py`, schemas: `backend/app/schemas/export.py`, tests: `backend/tests/test_export.py`.

## Gotchas

- The Dockerfile copies `pyproject.toml` before source for layer caching. `PYTHONPATH=/app` is set so `alembic` can find the `app` module.
- Docker Compose mounts `./backend:/app` as a volume, overriding the container's `/app`. Installed packages persist in the image layer.
- The `async_session` from `database.py` auto-commits. In tests, the `db` fixture wraps everything in a transaction that rolls back.
- Most relationships use `lazy="selectin"` — always use it for relationships accessed in API responses to avoid async lazy-load errors.
- The AI logging middleware only logs write operations from service accounts. Human user requests are not logged.
- The worker uses in-memory task tracking (dict). If the worker restarts, in-flight tasks are lost.
- The `conftest.py` test fixture creates the pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`) before `Base.metadata.create_all()`. Without this, tests fail because the Question/Answer models reference the `vector` type.
- The `EMBEDDING_MODEL` default is empty (disabled). Setting it requires a corresponding API key (e.g., `OPENAI_API_KEY` for `text-embedding-3-small`).
