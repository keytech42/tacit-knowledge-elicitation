# API Reference

## Interactive Documentation

FastAPI auto-generates interactive API docs from the source code. These are always up to date:

| Tool | URL | Best for |
|------|-----|----------|
| **Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) | Trying endpoints interactively |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) | Reading structured reference |
| **OpenAPI JSON** | [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) | Code generation, client SDKs |

Use those for endpoint signatures, request/response schemas, and query parameters. The rest of this page covers behavior that doesn't appear in the OpenAPI spec.

---

## Authentication Behavior

All endpoints require authentication unless noted. Two methods:

- `Authorization: Bearer <jwt>` — for human users
- `X-API-Key: <key>` — for service accounts

The `GET /health` endpoint is the only unauthenticated route.

### First-time Google login

When a user authenticates via Google for the first time, an account is created automatically with the `respondent` role. If their email matches the `BOOTSTRAP_ADMIN_EMAIL` environment variable, they receive all four roles instead.

### Dev login side effects

`POST /auth/dev-login` creates a `dev@localhost` user with all roles on first call. Subsequent calls return the same user. Returns 404 when `DEV_LOGIN_ENABLED` is false, so it can be disabled in production.

---

## Question State Machine

State transitions are enforced in `services/question.py`. The OpenAPI spec shows the endpoints, but not the allowed transitions or who can trigger them.

```
DRAFT ──[submit]──▶ PROPOSED ──[start-review]──▶ IN_REVIEW ──[publish]──▶ PUBLISHED ──[close]──▶ CLOSED ──[archive]──▶ ARCHIVED
                                                     │
                                                     └──[reject]──▶ DRAFT
```

| Endpoint | Transition | Who |
|----------|-----------|-----|
| `POST /questions/{id}/submit` | draft → proposed | author or admin |
| `POST /questions/{id}/start-review` | proposed → in_review | admin |
| `POST /questions/{id}/publish` | in_review → published | admin |
| `POST /questions/{id}/reject` | in_review → draft | admin |
| `POST /questions/{id}/close` | published → closed | admin |
| `POST /questions/{id}/archive` | closed → archived | admin |

**Publish side effect**: if `review_policy` is null, a default policy is set:
```json
{
  "min_approvals": 1,
  "auto_assign": false,
  "allow_self_review": false,
  "require_comment_on_reject": true
}
```

The optional field `auto_assign_count` (default: 1) controls how many reviewers are auto-assigned when `auto_assign` is true.

### Assign Respondent

`POST /api/v1/questions/{id}/assign-respondent` — assigns a user as the respondent for a published question. Admin only.

**Request body:**
```json
{"user_id": "<uuid>"}
```

**Response:** the updated `QuestionResponse` object.

Returns 409 if the question is not in `published` status. Returns 404 if the question or user is not found. A Slack DM notification is sent to the assigned respondent (fire-and-forget).

### Backfill Slack Threads

`POST /api/v1/questions/backfill-slack-threads` — creates Slack threads for published and closed questions that do not already have one. Admin only.

**Request body:** none.

**Response:**
```json
{"backfilled": 3, "total": 5}
```

`backfilled` is the number of questions that received a new Slack thread. `total` is the number of questions that were eligible (published or closed with no existing thread).

---

## Answer State Machine and Versioning

State transitions are enforced in `services/answer.py`.

```
DRAFT ──[submit]──▶ SUBMITTED ──[review starts]──▶ UNDER_REVIEW
                        ▲                              │
                        │                    ┌─────────┴─────────┐
                        │                    ▼                   ▼
                   REVISION_REQUESTED      APPROVED          REJECTED
                                             │
                                             └──[revise]──▶ SUBMITTED
```

### Revision triggers

Each submission creates an immutable `AnswerRevision`. The `trigger` field records why:

| Trigger | When |
|---------|------|
| `initial_submit` | First `POST .../submit` (creates version 1) |
| `revision_after_review` | Resubmit after `changes_requested` feedback |
| `post_approval_update` | `POST .../revise` on an already-approved answer |

### Edit permissions

- **Draft / revision_requested**: only the author (or admin) can edit
- **Approved**: author, collaborators, or admin can revise — this resets status to `submitted`

---

## Review Resolution Logic

When a reviewer submits a verdict via `PATCH /reviews/{id}`, the system automatically resolves the answer's status based on all reviews for that answer:

1. If **any** review has verdict `changes_requested` → answer becomes `revision_requested`
2. If **any** review has verdict `rejected` → answer becomes `rejected`
3. If approvals **≥** the question's `review_policy.min_approvals` → answer becomes `approved`
4. Otherwise, the answer stays in its current status (waiting for more reviews)

This logic runs in `services/review.py:resolve_answer_reviews()`.

---

## AI Logging (Implicit)

The AI logging middleware automatically records all write operations (POST, PUT, PATCH, DELETE) from service accounts. No explicit API call is needed — the middleware intercepts the request/response and creates an `AIInteractionLog` entry with:

- Endpoint and HTTP method
- Full request body
- Response status code
- Latency in milliseconds
- Service account's `model_id` at request time

Human users' requests are **not** logged. The middleware fails silently to avoid breaking requests.

---

## AI Trigger Endpoints (Admin Only)

These endpoints proxy requests to the LLM worker service. They return 503 if `WORKER_URL` is not configured.

| Endpoint | Description | Request Body |
|----------|-------------|-------------|
| `POST /api/v1/ai/generate-questions` | Trigger question generation | `{topic, domain, count?, context?}` |
| `POST /api/v1/ai/scaffold-options` | Trigger answer option scaffolding (replaces existing options, max 4) | `{question_id, num_options?}` |
| `POST /api/v1/ai/review-assist` | Trigger AI review of an answer | `{answer_id}` |
| `POST /api/v1/ai/extract-questions` | Extract questions from source text (creates a SourceDocument) | `{source_text, document_title?, domain?, max_questions?}` |
| `POST /api/v1/ai/extract-from-file` | Extract questions from an uploaded file (multipart form) | `file` (upload), `document_title?`, `domain?`, `max_questions?` |
| `POST /api/v1/ai/recommend` | Get respondent recommendations (runs in backend, no worker needed) | `{question_id, top_k?}` |
| `GET /api/v1/ai/tasks/{task_id}` | Check task status (proxied to worker) | -- |

Worker-proxied endpoints (`generate-questions`, `scaffold-options`, `review-assist`, `extract-questions`, `extract-from-file`) return `{task_id, status}` on acceptance (HTTP 202). Poll `GET /api/v1/ai/tasks/{task_id}` for completion. They return 503 if `WORKER_URL` is not configured, or 502 if the worker does not respond.

### Auto-Triggers

These fire automatically when `WORKER_URL` is configured (fire-and-forget, failures don't block the main operation):

- **Question published** → triggers `scaffold-options`
- **Answer submitted** → triggers `review-assist`

### Answer Option Scaffolding Behavior

Each scaffold run **replaces** all existing options for the question (deletes then recreates). A maximum of **4 options** are generated per run, emphasizing maximally distinct perspectives. After scaffolding, `show_suggestions` is automatically set to `true` on the question. Admins always see answer options regardless of the `show_suggestions` flag.

### Delete Answer Options

`DELETE /api/v1/questions/{id}/options` — removes all answer options for a question. Restricted to admin or the question author.

### Question Extraction Behavior

`POST /api/v1/ai/extract-questions` accepts raw text. A `SourceDocument` record is created before dispatching to the worker.

`POST /api/v1/ai/extract-from-file` accepts a multipart file upload. Supported file types are determined by the `parse_file` service. The file contents are extracted to text, a `SourceDocument` is created, and the extraction task is dispatched. Returns 400 if the file type is unsupported or the file contains no extractable text.

Both endpoints return the standard `{task_id, status}` response.

### Recommendation Response

`POST /api/v1/ai/recommend` returns results immediately (no async task):

```json
{
  "items": [
    {"user_id": "...", "display_name": "...", "score": 0.85, "reasoning": "..."}
  ],
  "reason": "...",
  "strategy": "embedding"
}
```

The `strategy` field indicates which recommendation method was used (e.g., `"embedding"` for pgvector cosine similarity). The `reason` field provides an explanation when recommendations are unavailable. Requires pgvector embeddings to be enabled (`EMBEDDING_MODEL` set). Returns an empty list if no embeddings exist.

---

## Source Documents (Admin Only)

CRUD endpoints for managing source documents used in question extraction. All endpoints require the admin role.

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/api/v1/source-documents` | `POST` | Create a source document | 201 |
| `/api/v1/source-documents` | `GET` | List all source documents (newest first) | 200 |
| `/api/v1/source-documents/{id}` | `GET` | Get a single source document | 200 |
| `/api/v1/source-documents/{id}` | `PATCH` | Update document summary or question count | 200 |
| `/api/v1/source-documents/{id}` | `DELETE` | Delete a source document | 204 |

### Create

**Request body:**
```json
{"title": "...", "body": "...", "domain": "..."}
```

`domain` is optional. The `uploaded_by` field is set to the authenticated admin.

### List

**Response:**
```json
{
  "items": [
    {"id": "...", "title": "...", "domain": "...", "document_summary": "...", "uploaded_by": {...}, "question_count": 0, "created_at": "...", "updated_at": "..."}
  ],
  "total": 1
}
```

### Update

Only `document_summary` and `question_count` can be patched. Both fields are optional; only provided fields are updated.

**Request body:**
```json
{"document_summary": "...", "question_count": 5}
```

### Delete

Deleting a source document nullifies the `source_document_id` on any linked questions before removing the document. Returns 204 with no body.

---

## Visibility Rules

Not captured in OpenAPI:

- **`GET /questions`** returns all published questions **plus** the caller's own questions in any status. Other users' drafts are not visible.
- **`GET /questions/{question_id}/answers`** visibility depends on the caller's relationship to the question and answer.
- **Quality feedback** is limited to one entry per user per question (enforced by unique constraint).
- **Answer options** are shown to respondents only when `show_suggestions` is true. Admins always see options regardless of the flag.
- **Service account API keys** are returned exactly once at creation (and on rotation). They cannot be retrieved later.
