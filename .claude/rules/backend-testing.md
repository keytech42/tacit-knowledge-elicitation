---
description: Rules for writing and running backend tests
globs: backend/tests/**
---

# Backend Testing

## Running Tests

```bash
docker compose exec api pytest -xvs
docker compose exec api pytest tests/test_questions.py -xvs  # specific file
```

Python 3.12 required. Tests cannot run outside Docker.

## Fixtures (from conftest.py)

- `client` — async HTTP client with dependency overrides
- `db` — async session with auto-rollback
- `admin_user`, `author_user`, `respondent_user`, `reviewer_user` — pre-configured users
- `roles` — dict of all Role objects
- `auth_header(user)` — returns `{"Authorization": "Bearer <jwt>"}` dict
- `service_user` — returns `(User, api_key)` tuple for service account tests
- `api_key_header(api_key)` — returns `{"X-API-Key": key}` dict

## Example

```python
@pytest.mark.asyncio
async def test_create_question(client, author_user):
    resp = await client.post("/api/v1/questions", json={
        "title": "Test", "body": "Body text"
    }, headers=auth_header(author_user))
    assert resp.status_code == 200
```

## Caveats

- Tests use `Base.metadata.create_all()`, not Alembic migrations. Verify migrations match models.
- HTTPX `ASGITransport` does not trigger FastAPI lifespan events. `seed_roles()` is tested separately in `test_startup.py`.
- `test_model_enum_values_are_lowercase` catches enum mismatches — run after any enum change.
- The `db` fixture wraps everything in a transaction that rolls back.
- `conftest.py` creates pgvector extension before `create_all()`.
