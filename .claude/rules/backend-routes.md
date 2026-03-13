---
description: Rules for API route handlers
globs: backend/app/api/**
---

# Backend Routes

## Layer Rules

- Routes are the HTTP layer only — parse requests, call services, return responses.
- Use `Depends(get_db)` for database sessions.
- Use `Depends(require_role(RoleName.ADMIN))` for role-based access control.
- No business logic in routes — delegate to `app/services/`.

## Adding an Endpoint

1. Define Pydantic schemas in `app/schemas/`
2. Add business logic in `app/services/`
3. Create route in `app/api/v1/`, wire deps
4. Write tests using the `client` fixture

## Auth Methods

- JWT bearer token (`Authorization: Bearer <token>`)
- API key (`X-API-Key: <key>`) for service accounts
- Dev login (`POST /auth/dev-login`) when `DEV_LOGIN_ENABLED=true`
