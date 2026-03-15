# Architecture

## System Overview

The platform is a four-service stack deployed via Docker Compose, plus a standalone pipeline for offline knowledge mining.

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

┌─────────────────────────────────────────────────────┐
│ pipeline (standalone, runs locally)                  │
│ Slack/Notion/PDF → Norms → Contradictions → Questions│
│ Output: platform_import.json (importable to api)    │
└─────────────────────────────────────────────────────┘
```

The frontend calls the backend API at `/api/v1/*`, proxied through Vite in development. The worker service is optional — the platform functions fully without it. When configured, the backend triggers LLM tasks on the worker via HTTP, and the worker calls back to the platform API as a service account.

The **pipeline** (`pipeline/`) is a standalone Python package that runs locally — not containerized, not part of Docker Compose. It ingests organizational data sources (Slack exports, Notion exports, PDFs), mines tacit knowledge through LLM-powered stages, and outputs `platform_import.json` which can be imported into the platform. See [Pipeline Guide](pipeline.md) for details.

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
| Answer option scaffolding | `POST /tasks/scaffold-options` | Auto on question publish, or on-demand. Replaces existing options (max 4, maximally distinct). |
| Review assistance | `POST /tasks/review-assist` | Auto on answer submit, or on-demand |
| Question extraction | `POST /tasks/extract-questions` | Admin on-demand. Two-pass LLM extraction from source documents: pass 1 extracts candidates from each chunk, pass 2 consolidates and deduplicates. Text is split on paragraph boundaries at ~4K chars; single-chunk documents skip consolidation. Extracted questions land as `draft` by default (`EXTRACTION_AUTO_SUBMIT` to override). |
| Respondent recommendation | `POST /tasks/recommend-respondents` | On-demand via recommendation service. LLM-based alternative to embedding similarity -- evaluates candidate respondent profiles against the question and scores them. Uses Haiku by default (`RECOMMENDATION_MODEL`). |

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
│   ├── review_assist.py
│   ├── question_extract.py
│   └── respondent_recommend.py
└── prompts/             # System/user prompt templates
```

The LLM wrapper (`llm.py`) appends JSON schemas from Pydantic models to system prompts for structured output, strips markdown code fences from responses, and retries with exponential backoff.

## Database

PostgreSQL 16 with pgvector extension (`pgvector/pgvector:pg16` Docker image) and the `asyncpg` driver. All primary keys are UUIDs. Timestamps are timezone-aware with server-side defaults.

### pgvector

The `vector` extension enables embedding storage and cosine similarity search. The `questions` and `answers` tables have optional `embedding vector(1024)` columns with hnsw indexes. Embeddings are generated via litellm when `EMBEDDING_MODEL` is configured.

### Migrations

Alembic manages schema migrations:
- `001_initial_schema.py` — creates 13 tables and 8 PostgreSQL enum types
- `002_add_review_answer_version.py` — review → answer version tracking
- `003_add_revision_content_hash.py` — content deduplication via SHA-256 hash
- `004_add_pgvector_embeddings.py` — enables pgvector extension, adds embedding columns and hnsw indexes
- `005_resize_embeddings_to_1024.py` — resizes embedding columns from 1536 to 1024 dimensions
- `006_add_assigned_respondent_to_questions.py` — respondent assignment FK on questions
- `007_add_slack_thread_columns_to_questions.py` — Slack thread tracking (channel, thread_ts) on questions
- `008_add_superseded_review_verdict.py` — adds `superseded` to the reviewverdict enum
- `009_add_source_documents_and_extraction.py` — source_documents table, source_type enum, extraction columns on questions

Migrations run automatically on `docker compose up` via the api service command: `alembic upgrade head && uvicorn ...`.

## Service Accounts

LLM agents and automated systems authenticate as service accounts via API keys. Service accounts can be created with multiple roles (e.g., `["author", "reviewer"]` for the worker). The AI logging middleware automatically records all their write operations for audit and monitoring.

## Slack Integration

The platform sends Slack notifications via the `slack_sdk` async client. All notification functions follow a fire-and-forget pattern -- exceptions are caught internally so Slack outages or misconfiguration never block core operations.

### Thread Lifecycle

When a question is published, a message is posted to the configured channel, creating a Slack thread. The thread timestamp and channel are stored on the Question model. All subsequent events for that question (answer submissions, review verdicts, respondent assignments, approval, closure) are posted as replies in that thread.

### DM Notifications

Certain events send direct messages to the affected user:

- **Respondent assignment** -- DMs the respondent when they are assigned to a question, with a link to the question. Also posts a thread reply mentioning the assignee.
- **Changes requested** -- DMs the answer author when a reviewer requests changes, including the reviewer comment if provided.

Slack user IDs are resolved by email lookup (`users.lookupByEmail`) with an in-memory cache.

### Markdown Conversion

Message bodies are converted from markdown to Slack's mrkdwn format (`_md_to_mrkdwn()`): headings become bold, `**bold**` becomes `*bold*`, links become `<url|text>`, bullets become `\u2022`, and HTML tags are stripped. Code spans and fenced blocks are preserved. Output is truncated to 2000 characters.

### Configuration

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`). When empty, all notifications are silently skipped. |
| `SLACK_DEFAULT_CHANNEL` | Channel name or ID for question threads (e.g., `#knowledge-elicitation`). |
| `FRONTEND_URL` | Base URL for deep links in Slack messages (e.g., `http://localhost:5173`). |

### Templates

Message formatting functions live in `backend/app/templates/slack/`:

- `questions.py` -- question published, rejected, closed
- `answers.py` -- answer submitted, approved
- `reviews.py` -- review verdict, revision requested, changes requested DM
- `assignments.py` -- respondent assigned (DM and thread)

## File Parsing

The file upload and parsing layer (`backend/app/services/file_parser.py`) extracts plain text from uploaded documents for the question extraction pipeline. Supported formats:

| Format | Parser | Library |
|--------|--------|---------|
| `.txt` | `TextParser` | Built-in (UTF-8 decode) |
| `.md` | `TextParser` | Built-in (UTF-8 decode) |
| `.pdf` | `PdfParser` | pymupdf |
| `.docx` | `DocxParser` | python-docx |
| `.json` | `JsonParser` | Built-in (recursive string extraction) |

Files are resolved by content type first, then by extension as a fallback. Maximum file size is 10 MB.

## Respondent Recommendation

Recommendations match questions to suitable respondents using one of two strategies, configured via `RECOMMENDATION_STRATEGY`:

| Strategy | How it works |
|----------|-------------|
| `embedding` | pgvector cosine similarity between question and answer embeddings, scored: `0.4 * semantic_similarity + 0.3 * approval_rate + 0.2 * category_match + 0.1 * recency`. Runs entirely in the backend -- no LLM call at query time. Requires `EMBEDDING_MODEL` to be configured. |
| `llm` | The backend gathers candidate profiles from the database and sends them to the worker, which uses LLM reasoning to score and rank respondents. Uses Haiku by default (`RECOMMENDATION_MODEL`). Requires `WORKER_URL` to be configured. |
| `auto` (default) | Prefers `embedding` when `EMBEDDING_MODEL` is set, otherwise falls back to `llm`. |

The API endpoint is `POST /api/v1/ai/recommend`.
