---
description: Rules for Docker Compose and container configuration
globs: docker-compose*.yml, Dockerfile*, backup/**
---

# Docker & Deployment

## Environment Variables

**Env vars must be forwarded in `docker-compose.yml`.** Adding to `app/config.py` and `.env` is not enough — add `${VAR:-}` in the service's `environment:` block. Verify with:

```bash
docker compose exec api python -c "from app.config import settings; print(settings.YOUR_VAR)"
```

## Compose Files

- `docker-compose.yml` — production-safe base (log rotation, postgresql.conf mount, restart policies)
- `docker-compose.override.yml` — dev overrides (hot-reload, source mounts) — auto-loaded

## Build

- Dockerfile copies `pyproject.toml` before source for layer caching
- `PYTHONPATH=/app` so alembic can find the `app` module
- Docker Compose mounts `./backend:/app` as volume, overriding container's `/app`
