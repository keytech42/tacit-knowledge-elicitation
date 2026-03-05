# Architecture

## System Overview

The platform is a three-service stack deployed via Docker Compose.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   web :5173  │────▶│  api :8000   │────▶│  db :5432    │
│  React/Vite  │     │   FastAPI    │     │ PostgreSQL 16│
└──────────────┘     └──────────────┘     └──────────────┘
```

All communication is HTTP. The frontend calls the backend API at `/api/v1/*`, proxied through Vite in development.

## Backend (FastAPI)

### Layer Structure

```
app/
├── api/           # HTTP layer — routes, request parsing, response formatting
│   ├── deps.py    # Shared dependencies (auth extraction, role checks)
│   └── v1/        # Versioned endpoint modules
├── services/      # Business logic — state transitions, validation, domain rules
├── models/        # SQLAlchemy ORM models and enums
├── schemas/       # Pydantic request/response schemas
├── middleware/     # Request/response interceptors
├── config.py      # Environment-based settings
├── database.py    # Engine and session factory
└── main.py        # App creation, lifespan hooks, middleware registration
```

Each layer has a single responsibility:

- **Routes** handle HTTP concerns: parse requests, call services, format responses.
- **Services** own domain logic: validate state transitions, enforce business rules. They receive a database session and model objects — no HTTP awareness.
- **Models** define data structure and relationships. No business logic.
- **Schemas** define API contracts. Separate from ORM models to decouple the API surface from storage.

### Middleware Stack

Middleware executes in registration order (top = outermost):

1. **AILoggingMiddleware** — intercepts write operations (POST/PUT/PATCH/DELETE) from service accounts. Captures request body, response status, and latency. Writes `AIInteractionLog` entries asynchronously. Fails silently to avoid breaking requests.
2. **CORSMiddleware** — handles cross-origin requests from the frontend.

### Lifespan Hooks

On startup, the app seeds default roles (`admin`, `author`, `respondent`, `reviewer`) if they don't exist. On shutdown, it disposes the database engine.

### Dependency Injection

FastAPI's `Depends()` system provides:

- **`get_db()`** — async database session with auto-commit/rollback
- **`get_current_user()`** — extracts user from JWT bearer token or `X-API-Key` header
- **`require_role(*roles)`** — factory that returns a dependency enforcing role membership

## Frontend (React)

### Structure

```
src/
├── api/client.ts          # HTTP client with token management
├── auth/                  # Auth context, login page
├── components/            # Layout, route guards
└── pages/                 # Feature pages (questions, answers, reviews, admin)
```

### State Management

Auth state lives in React Context (`AuthContext`). All other state is local to pages — fetched on mount, no global store.

### API Client

A thin wrapper around `fetch()` that:
- Attaches the JWT bearer token from localStorage
- Redirects to `/login` on 401 responses
- Parses JSON responses and error details

## Database

PostgreSQL 16 with the `asyncpg` driver. All primary keys are UUIDs. Timestamps are timezone-aware with server-side defaults.

### Migrations

Alembic manages schema migrations. The initial migration (`001_initial_schema.py`) creates 13 tables and 8 PostgreSQL enum types. Subsequent migrations add fields: `002_add_review_answer_version.py` (review → answer version tracking) and `003_add_revision_content_hash.py` (content deduplication via SHA-256 hash).

Migrations run automatically on `docker compose up` via the api service command: `alembic upgrade head && uvicorn ...`.

## Service Accounts

LLM agents and automated systems authenticate as service accounts via API keys. The AI logging middleware automatically records all their write operations for audit and monitoring.
