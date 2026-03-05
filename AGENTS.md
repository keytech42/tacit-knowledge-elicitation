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

frontend/
  src/api/          HTTP client (fetch wrapper with JWT)
  src/auth/         Auth context and login page
  src/components/   Layout, route guards
  src/pages/        Feature pages

docker-compose.yml  Three services: db, api, web
Makefile            Development shortcuts
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

- `conftest.py`: Fixtures for db sessions, HTTP client, user/role factories
- Each test file covers one domain: `test_auth.py`, `test_questions.py`, `test_answers.py`, `test_reviews.py`, `test_permissions.py`, `test_ai_logging.py`, `test_startup.py`, `test_admin_queue.py`, `test_e2e_workflows.py`

### Writing Tests

Use the fixtures from `conftest.py`:
- `client` — async HTTP client with dependency overrides
- `db` — async session with auto-rollback
- `admin_user`, `author_user`, `respondent_user`, `reviewer_user` — pre-configured users
- `roles` — dict of all Role objects
- `auth_header(user)` — returns `{"Authorization": "Bearer <jwt>"}` dict

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

## Gotchas

- The Dockerfile copies `pyproject.toml` before source for layer caching. `PYTHONPATH=/app` is set so `alembic` can find the `app` module.
- Docker Compose mounts `./backend:/app` as a volume, overriding the container's `/app`. Installed packages persist in the image layer.
- The `async_session` from `database.py` auto-commits. In tests, the `db` fixture wraps everything in a transaction that rolls back.
- All relationships use `lazy="selectin"` to avoid async lazy-load errors. Never use `lazy="select"` (the default) with async sessions.
- The AI logging middleware only logs write operations from service accounts. Human user requests are not logged.
