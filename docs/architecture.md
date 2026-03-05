# Architecture

## System Overview

The platform is a four-service stack deployed via Docker Compose.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   web :5173  │────▶│  api :8000   │────▶│    db :5432      │
│  React/Vite  │     │   FastAPI    │     │ pgvector/pg16    │
└──────────────┘     └──────┬───────┘     └──────────────────┘
                            │
                     ┌──────▼───────┐
                     │ worker :8001 │
                     │ FastAPI+LLM  │
                     └──────────────┘
```

The frontend calls the backend API at `/api/v1/*`, proxied through Vite in development. The worker service is optional — the platform functions fully without it. When configured, the backend triggers LLM tasks on the worker via HTTP, and the worker calls back to the platform API as a service account.

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

## Worker (LLM Tasks)

A separate FastAPI service that handles LLM-powered capabilities via litellm (provider-agnostic). Authenticates to the platform API as a service account using `X-API-Key`.

### Tasks

| Task | Endpoint | Trigger |
|------|----------|---------|
| Question generation | `POST /tasks/generate-questions` | Admin on-demand |
| Answer option scaffolding | `POST /tasks/scaffold-options` | Auto on question publish, or on-demand |
| Review assistance | `POST /tasks/review-assist` | Auto on answer submit, or on-demand |

Tasks run as background `asyncio.Task` instances with in-memory status tracking. The backend proxies trigger requests via admin-only `/api/v1/ai/*` endpoints.

### Architecture

```
worker/
├── main.py              # FastAPI app, task endpoints, in-memory tracking
├── config.py            # WorkerSettings (pydantic-settings)
├── platform_client.py   # httpx async client for platform REST API
├── llm.py               # litellm wrapper (structured output + retries)
├── schemas.py           # Pydantic models for LLM outputs
├── tasks/               # Task implementations
│   ├── question_gen.py
│   ├── answer_scaffold.py
│   └── review_assist.py
└── prompts/             # System/user prompt templates
```

The LLM wrapper (`llm.py`) appends JSON schemas from Pydantic models to system prompts for structured output, strips markdown code fences from responses, and retries with exponential backoff.

## Database

PostgreSQL 16 with pgvector extension (`pgvector/pgvector:pg16` Docker image) and the `asyncpg` driver. All primary keys are UUIDs. Timestamps are timezone-aware with server-side defaults.

### pgvector

The `vector` extension enables embedding storage and cosine similarity search. The `questions` and `answers` tables have optional `embedding vector(1536)` columns with hnsw indexes. Embeddings are generated via litellm when `EMBEDDING_MODEL` is configured.

### Migrations

Alembic manages schema migrations:
- `001_initial_schema.py` — creates 13 tables and 8 PostgreSQL enum types
- `002_add_review_answer_version.py` — review → answer version tracking
- `003_add_revision_content_hash.py` — content deduplication via SHA-256 hash
- `004_add_pgvector_embeddings.py` — enables pgvector extension, adds embedding columns and hnsw indexes

Migrations run automatically on `docker compose up` via the api service command: `alembic upgrade head && uvicorn ...`.

## Service Accounts

LLM agents and automated systems authenticate as service accounts via API keys. Service accounts can be created with multiple roles (e.g., `["author", "reviewer"]` for the worker). The AI logging middleware automatically records all their write operations for audit and monitoring.

## Respondent Recommendation

Embedding-based respondent recommendation runs entirely in the backend (no LLM call at query time):

1. Questions and answers get embeddings generated on create/update (via litellm)
2. `POST /api/v1/ai/recommend` finds answers with similar embeddings using pgvector cosine similarity
3. Results are grouped by author and scored: `0.4 * semantic_similarity + 0.3 * approval_rate + 0.2 * category_match + 0.1 * recency`
