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

The `GET /health` and `GET /auth/config` endpoints are the only unauthenticated routes.

### Auth Endpoints

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `GET` | `/api/v1/auth/config` | None | Return public auth configuration | 200 |
| `POST` | `/api/v1/auth/google` | None | Exchange Google authorization code for JWT | 200 |
| `POST` | `/api/v1/auth/dev-login` | None | Create/return dev admin user | 200 |
| `POST` | `/api/v1/auth/refresh` | None | Exchange an existing JWT for a new one | 200 |

#### GET /api/v1/auth/config

Returns the public auth configuration so the frontend can determine which login methods are available. No authentication required.

**Response (200):**
```json
{
  "google_client_id": "...",
  "dev_login_enabled": true
}
```

#### POST /api/v1/auth/refresh

Exchanges an existing (valid or recently expired) JWT for a fresh one. The token is passed as the `token` query parameter.

**Query parameters:**
- `token` (string) — the JWT to refresh

**Response (200):**
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user_id": "<uuid>",
  "email": "...",
  "display_name": "...",
  "roles": ["admin", "author"]
}
```

Returns 401 if the token is invalid or the user is inactive.

### First-time Google login

When a user authenticates via Google for the first time, an account is created automatically with the `respondent` role. If their email matches the `BOOTSTRAP_ADMIN_EMAIL` environment variable, they receive all four roles instead.

### Dev login side effects

`POST /auth/dev-login` creates a `dev@localhost` user with all roles on first call. Subsequent calls return the same user. Returns 404 when `DEV_LOGIN_ENABLED` is false, so it can be disabled in production.

---

## User Management

### Endpoints

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `GET` | `/api/v1/users/me` | Any authenticated user | Get the current user's profile | 200 |
| `GET` | `/api/v1/users/search` | Reviewer or Admin | Search users by name/email | 200 |
| `GET` | `/api/v1/users` | Admin | List all users (paginated) | 200 |
| `POST` | `/api/v1/users/{user_id}/roles` | Admin | Assign a role to a user | 200 |
| `DELETE` | `/api/v1/users/{user_id}/roles/{role_name}` | Admin | Remove a role from a user | 200 |

#### GET /api/v1/users/me

Returns the authenticated user's profile. Works with both JWT and API key authentication.

**Response (200):** `UserResponse`
```json
{
  "id": "<uuid>",
  "user_type": "human",
  "display_name": "...",
  "email": "...",
  "avatar_url": "...",
  "is_active": true,
  "roles": [{"id": "<uuid>", "name": "admin"}],
  "created_at": "..."
}
```

#### GET /api/v1/users/search

Search human users by display name or email. Available to reviewers and admins.

**Query parameters:**
- `q` (string, optional) — search term matched against display name and email (case-insensitive substring match)
- `role` (string, optional) — filter by role name (e.g., `"reviewer"`)
- `limit` (int, default 20, max 50) — maximum results to return

**Response (200):**
```json
{
  "users": [UserResponse, ...],
  "total": 5
}
```

Only active human users are returned (service accounts are excluded).

#### GET /api/v1/users

List all users with pagination. Admin only.

**Query parameters:**
- `skip` (int, default 0) — offset
- `limit` (int, default 50) — page size

**Response (200):**
```json
{
  "users": [UserResponse, ...],
  "total": 42
}
```

#### POST /api/v1/users/{user_id}/roles

Assign a role to a user. Admin only.

**Request body:**
```json
{"role_name": "reviewer"}
```

Valid role names: `admin`, `author`, `reviewer`, `respondent`.

**Response (200):** the updated `UserResponse`.

Returns 400 if the role name is invalid. Returns 404 if the user or role is not found. Returns 409 if the user already has the role.

#### DELETE /api/v1/users/{user_id}/roles/{role_name}

Remove a role from a user. Admin only.

**Response (200):** the updated `UserResponse`.

Returns 404 if the user, role, or assignment is not found.

---

## Service Accounts (Admin Only)

### Endpoints

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `POST` | `/api/v1/service-accounts` | Admin | Create a service account | 201 |
| `GET` | `/api/v1/service-accounts` | Admin | List all service accounts | 200 |
| `GET` | `/api/v1/service-accounts/{account_id}` | Admin | Get a service account | 200 |
| `PATCH` | `/api/v1/service-accounts/{account_id}` | Admin | Update a service account | 200 |
| `POST` | `/api/v1/service-accounts/{account_id}/rotate-key` | Admin | Rotate API key | 200 |

#### POST /api/v1/service-accounts

Create a new service account with an API key.

**Request body:**
```json
{
  "display_name": "AI Worker",
  "model_id": "gpt-4o",
  "system_version": "1.0",
  "roles": ["author", "reviewer"]
}
```

- `display_name` (string, required)
- `model_id` (string, optional) — identifier for the LLM model used
- `system_version` (string, optional)
- `roles` (list of strings, optional) — defaults to `["author"]` if omitted

**Response (201):** `ServiceAccountWithKeyResponse` — includes the `api_key` field. The API key is returned exactly once at creation and cannot be retrieved later.

```json
{
  "id": "<uuid>",
  "display_name": "AI Worker",
  "model_id": "gpt-4o",
  "system_version": "1.0",
  "is_active": true,
  "roles": [{"id": "<uuid>", "name": "author"}, ...],
  "created_at": "...",
  "api_key": "ke_..."
}
```

Returns 400 if any role name is invalid.

#### GET /api/v1/service-accounts

List all service accounts, newest first.

**Response (200):** `list[ServiceAccountResponse]` (no `api_key` field).

#### GET /api/v1/service-accounts/{account_id}

Get a single service account by ID.

**Response (200):** `ServiceAccountResponse`.

Returns 404 if the account is not found or is not a service account.

#### PATCH /api/v1/service-accounts/{account_id}

Update a service account's metadata. Only `display_name`, `model_id`, and `system_version` can be changed.

**Request body:**
```json
{
  "display_name": "Updated Name",
  "model_id": "claude-3.5-sonnet",
  "system_version": "2.0"
}
```

**Response (200):** `ServiceAccountResponse`.

Returns 404 if the account is not found.

#### POST /api/v1/service-accounts/{account_id}/rotate-key

Generate a new API key for a service account, invalidating the previous one.

**Request body:** none.

**Response (200):** `ServiceAccountWithKeyResponse` — includes the new `api_key`. This is the only opportunity to capture the new key.

Returns 404 if the account is not found.

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

### Admin Queue

`GET /api/v1/questions/admin-queue` — returns all actionable questions grouped by status bucket. Admin only.

**Request body:** none.

**Response (200):** `AdminQueueResponse`
```json
{
  "proposed": [AdminQueueItem, ...],
  "in_review": [AdminQueueItem, ...],
  "pending": [AdminQueueItem, ...],
  "published": [AdminQueueItem, ...],
  "closed": [AdminQueueItem, ...]
}
```

Each `AdminQueueItem` contains:
```json
{
  "id": "<uuid>",
  "title": "...",
  "body": "...",
  "category": "...",
  "status": "proposed",
  "quality_score": null,
  "created_by": {UserResponse},
  "created_at": "...",
  "updated_at": "...",
  "published_at": null,
  "answer_count": 3,
  "approved_count": 1,
  "pending_count": 2
}
```

The `pending` bucket contains published questions that have in-progress answers (submitted, under_review, or revision_requested). Published questions with no in-progress answers appear in the `published` bucket. Questions are ordered newest first within each bucket.

### Categories

`GET /api/v1/questions/categories` — returns a deduplicated list of all category strings currently in use. Any authenticated user.

**Request body:** none.

**Response (200):** `list[str]`
```json
["Security", "Architecture", "Deployment"]
```

Returns only non-null categories. The list is unordered.

### Quality Feedback

`POST /api/v1/questions/{question_id}/feedback` — submit quality feedback for a question. Any authenticated user. Limited to one entry per user per question.

**Request body:**
```json
{
  "rating": 4,
  "comment": "Well-structured question"
}
```

- `rating` (int, required) — 1 to 5
- `comment` (string, optional)

**Response (201):** `QualityFeedbackResponse`
```json
{
  "id": "<uuid>",
  "question_id": "<uuid>",
  "user": {UserResponse},
  "rating": 4,
  "comment": "Well-structured question",
  "created_at": "..."
}
```

Submitting feedback automatically recalculates the question's `quality_score` as the average of all feedback ratings.

Returns 404 if the question is not found. Returns 409 if the user has already submitted feedback for this question.

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

### Answer Transition Endpoints

| Endpoint | Transition | Who |
|----------|-----------|-----|
| `POST /answers/{id}/submit` | draft → submitted | author or admin |
| `PATCH /reviews/{id}` (verdict) | submitted → under_review / approved / changes_requested / rejected | reviewer |
| `POST /answers/{id}/revise` | approved → submitted | author, collaborator, or admin |

#### POST /api/v1/answers/{answer_id}/submit

Submit an answer (transitions from `draft` to `submitted`). Creates an `AnswerRevision` with trigger `initial_submit` (version 1) or `revision_after_review` (subsequent versions). Also generates an embedding and triggers the review-assist auto-trigger when `WORKER_URL` is configured.

**Request body:** none.

**Response (200):** `AnswerResponse` — the updated answer with status `submitted`.

Returns 409 if the answer is not in a submittable state (`draft` or `revision_requested`).

### Revision triggers

Each submission creates an immutable `AnswerRevision`. The `trigger` field records why:

| Trigger | When |
|---------|------|
| `initial_submit` | First `POST .../submit` (creates version 1) |
| `revision_after_review` | Resubmit after `changes_requested` feedback |
| `post_approval_update` | `POST .../revise` on an already-approved answer |

### Post-Approval Revision

`POST /api/v1/answers/{answer_id}/revise` — create a post-approval revision on an already-approved answer. Resets the answer status to `submitted` and creates a new revision with trigger `post_approval_update`. Available to the answer author, collaborators, or admin.

**Request body (optional):**
```json
{
  "body": "Updated answer text",
  "selected_option_id": "<uuid>"
}
```

- `body` (string, optional) — new answer body; if omitted, the existing body is snapshotted
- `selected_option_id` (uuid, optional) — new selected option; if omitted, the existing selection is kept

**Response (200):** `AnswerResponse` — the updated answer with status `submitted` and incremented `current_version`.

Returns 404 if the answer is not found. Returns 403 if the caller is not the author, a collaborator, or an admin. Returns 409 if the answer is not in `approved` status.

### Edit permissions

- **Draft / revision_requested**: only the author (or admin) can edit
- **Approved**: author, collaborators, or admin can revise — this resets status to `submitted`

### Answer Versions and Diff

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `GET` | `/api/v1/answers/{answer_id}/versions` | Any authenticated user | List all revisions for an answer | 200 |
| `GET` | `/api/v1/answers/{answer_id}/versions/{version}` | Any authenticated user | Get a specific revision by version number | 200 |
| `GET` | `/api/v1/answers/{answer_id}/diff` | Any authenticated user | Get a unified diff between two revisions | 200 |
| `GET` | `/api/v1/answers/{answer_id}/staging-diff` | Any authenticated user | Compare working copy against latest committed revision | 200 |

#### GET /api/v1/answers/{answer_id}/versions

Returns all revisions for an answer, ordered by version number ascending.

**Response (200):** `list[AnswerRevisionResponse]`
```json
[
  {
    "id": "<uuid>",
    "answer_id": "<uuid>",
    "version": 1,
    "body": "...",
    "selected_option_id": null,
    "created_by": {UserResponse},
    "trigger": "initial_submit",
    "previous_status": null,
    "created_at": "..."
  }
]
```

#### GET /api/v1/answers/{answer_id}/versions/{version}

Get a specific revision by version number.

**Response (200):** `AnswerRevisionResponse`.

Returns 404 if the revision is not found.

#### GET /api/v1/answers/{answer_id}/diff

Get a unified text diff between two revisions.

**Query parameters (required):**
- `from` (int) — source version number
- `to` (int) — target version number

**Response (200):**
```json
{
  "from_version": 1,
  "to_version": 2,
  "diff": "--- version 1\n+++ version 2\n...",
  "from_created_at": "...",
  "to_created_at": "..."
}
```

Returns 404 if either revision is not found.

#### GET /api/v1/answers/{answer_id}/staging-diff

Compare the current working copy (live `answer.body`) against the latest committed revision. Useful for showing unsaved changes before submission.

**Response (200):**
```json
{
  "has_changes": true,
  "latest_version": 2,
  "diff": "--- version 2\n+++ working copy\n..."
}
```

`has_changes` is false and `diff` is null when the working copy matches the latest revision. `latest_version` is null if no revisions exist yet.

### Answer Collaborators

Collaborators can edit an approved answer (triggering a post-approval revision). Only the answer author or an admin can manage collaborators.

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `POST` | `/api/v1/answers/{answer_id}/collaborators` | Author or Admin | Add a collaborator | 201 |
| `GET` | `/api/v1/answers/{answer_id}/collaborators` | Any authenticated user | List collaborators | 200 |
| `DELETE` | `/api/v1/answers/{answer_id}/collaborators/{user_id}` | Author or Admin | Remove a collaborator | 204 |

#### POST /api/v1/answers/{answer_id}/collaborators

**Request body:**
```json
{"user_id": "<uuid>"}
```

**Response (201):** `CollaboratorResponse`
```json
{
  "id": "<uuid>",
  "answer_id": "<uuid>",
  "user": {UserResponse},
  "granted_by": {UserResponse},
  "created_at": "..."
}
```

Returns 403 if the current user is not the answer author or admin. Returns 404 if the answer or target user is not found. Returns 409 if the user is already a collaborator.

#### GET /api/v1/answers/{answer_id}/collaborators

**Response (200):** `list[CollaboratorResponse]`

#### DELETE /api/v1/answers/{answer_id}/collaborators/{user_id}

Removes a collaborator from the answer.

Returns 204 with no body on success. Returns 403 if the current user is not the answer author or admin. Returns 404 if the answer or collaborator is not found.

---

## Reviews

### Endpoints

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `POST` | `/api/v1/reviews` | Reviewer or Admin | Create a new review | 201 |
| `POST` | `/api/v1/reviews/assign/{answer_id}` | Reviewer or Admin | Assign a reviewer to an answer | 201 |
| `GET` | `/api/v1/reviews` | Any authenticated user | List reviews with optional filters | 200 |
| `GET` | `/api/v1/reviews/my-queue` | Reviewer or Admin | Get the caller's pending reviews | 200 |
| `GET` | `/api/v1/reviews/{review_id}` | Any authenticated user | Get a single review | 200 |
| `PATCH` | `/api/v1/reviews/{review_id}` | Reviewer or Admin | Submit a verdict on a review | 200 |
| `POST` | `/api/v1/reviews/{review_id}/comments` | Any authenticated user | Add a threaded comment to a review | 201 |

#### POST /api/v1/reviews

Create a new pending review for a question or answer.

**Request body:**
```json
{
  "target_type": "answer",
  "target_id": "<uuid>"
}
```

`target_type` must be `"question"` or `"answer"`. For answer reviews, the answer must be in `submitted` or `under_review` status. Creating a review on a `submitted` answer automatically transitions it to `under_review`. The reviewer cannot be the answer's author (self-review is prevented).

**Response (201):** `ReviewResponse`

Returns 404 if the target is not found. Returns 409 if the target is not in a reviewable state, the reviewer is the author, or a duplicate pending review already exists for the same reviewer and version.

#### POST /api/v1/reviews/assign/{answer_id}

Assign a specific reviewer to an answer. The caller does not need to be the assigned reviewer.

**Request body:**
```json
{"reviewer_id": "<uuid>"}
```

The target reviewer must have the `reviewer` role and cannot be the answer author. Like `POST /reviews`, this transitions `submitted` answers to `under_review`.

**Response (201):** `ReviewResponse`

Returns 400 if the target user lacks the reviewer role. Returns 404 if the answer or reviewer is not found. Returns 409 if the answer is not reviewable, the reviewer is the author, or a duplicate pending review already exists.

#### GET /api/v1/reviews

List reviews with optional filters.

**Query parameters (all optional):**
- `target_type` (string) — `"question"` or `"answer"`
- `target_id` (uuid) — filter by target entity
- `reviewer_id` (uuid) — filter by reviewer

**Response (200):** `list[ReviewResponse]`

Each `ReviewResponse` is enriched with contextual fields: `question_title`, `question_status`, `answer_status`, `approval_count`, and `min_approvals`.

#### GET /api/v1/reviews/my-queue

Get the current user's pending reviews, ordered oldest first.

**Response (200):** `list[ReviewResponse]`

#### GET /api/v1/reviews/{review_id}

Get a single review by ID.

**Response (200):** `ReviewResponse`

Returns 404 if the review is not found.

#### PATCH /api/v1/reviews/{review_id}

Submit a verdict on a pending review. Only the assigned reviewer or an admin can submit.

**Request body:**
```json
{
  "verdict": "approved",
  "comment": "Looks good."
}
```

Valid verdicts: `approved`, `changes_requested`, `rejected`. The `comment` field is optional.

Submitting a verdict triggers automatic answer status resolution (see Review Resolution Logic below). Slack notifications are sent for the verdict and any resulting status change (approval, revision requested).

**Response (200):** the updated `ReviewResponse`.

Returns 400 if the verdict is invalid. Returns 403 if the caller is not the reviewer or admin. Returns 409 if the review is already resolved (not pending).

#### POST /api/v1/reviews/{review_id}/comments

Add a threaded comment to a review. Any authenticated user can comment.

**Request body:**
```json
{
  "body": "Could you clarify this point?",
  "parent_id": null
}
```

- `body` (string, required) — comment text
- `parent_id` (uuid, optional) — ID of a parent comment for threading

**Response (201):** `ReviewCommentResponse`
```json
{
  "id": "<uuid>",
  "review_id": "<uuid>",
  "author": {UserResponse},
  "body": "...",
  "parent_id": null,
  "created_at": "..."
}
```

Returns 404 if the review or parent comment is not found.

---

## Review Resolution Logic

When a reviewer submits a verdict via `PATCH /reviews/{id}`, the system automatically resolves the answer's status based on all reviews for that answer:

1. If **any** review has verdict `changes_requested` → answer becomes `revision_requested`
2. If **any** review has verdict `rejected` → answer becomes `rejected`
3. If approvals **≥** the question's `review_policy.min_approvals` → answer becomes `approved`
4. Otherwise, the answer stays in its current status (waiting for more reviews)

This logic runs in `services/review.py:resolve_answer_reviews()`.

---

## AI Logging

### Implicit Capture

The AI logging middleware automatically records all write operations (POST, PUT, PATCH, DELETE) from service accounts. No explicit API call is needed — the middleware intercepts the request/response and creates an `AIInteractionLog` entry with:

- Endpoint and HTTP method
- Full request body
- Response status code
- Latency in milliseconds
- Service account's `model_id` at request time

Human users' requests are **not** logged. The middleware fails silently to avoid breaking requests.

### AI Log Endpoints

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| `GET` | `/api/v1/ai-logs` | Admin | List AI interaction logs (paginated) | 200 |
| `GET` | `/api/v1/ai-logs/export` | Admin | Export all logs as JSON or CSV | 200 |
| `GET` | `/api/v1/ai-logs/{log_id}` | Admin | Get a single log entry | 200 |
| `POST` | `/api/v1/ai-logs/{log_id}/feedback` | Any authenticated user | Submit feedback on an AI interaction | 200 |

#### GET /api/v1/ai-logs

List AI interaction logs with optional filters.

**Query parameters:**
- `service_user_id` (uuid, optional) — filter by service account
- `endpoint` (string, optional) — substring match on the endpoint path
- `skip` (int, default 0) — offset
- `limit` (int, default 50) — page size

**Response (200):**
```json
{
  "logs": [
    {
      "id": "<uuid>",
      "service_user": {UserResponse},
      "model_id": "gpt-4o",
      "endpoint": "/api/v1/questions",
      "request_body": {...},
      "response_status": 200,
      "created_entity_type": "question",
      "created_entity_id": "<uuid>",
      "latency_ms": 342,
      "token_usage": null,
      "feedback_rating": null,
      "feedback_comment": null,
      "feedback_by": null,
      "feedback_at": null,
      "created_at": "..."
    }
  ],
  "total": 15
}
```

#### GET /api/v1/ai-logs/export

Export all AI interaction logs. Admin only.

**Query parameters:**
- `format` (string, default `"json"`) — must be `"json"` or `"csv"`

**Response (200):**
- When `format=json`: returns `list[AILogResponse]` as JSON.
- When `format=csv`: returns a streaming CSV download with columns: `id`, `service_user_id`, `model_id`, `endpoint`, `response_status`, `latency_ms`, `feedback_rating`, `created_at`. The response has `Content-Disposition: attachment; filename=ai_logs.csv`.

#### GET /api/v1/ai-logs/{log_id}

Get a single AI interaction log by ID. Admin only.

**Response (200):** `AILogResponse`

Returns 404 if the log entry is not found.

#### POST /api/v1/ai-logs/{log_id}/feedback

Submit human feedback on an AI interaction. Available to any authenticated user (not just admins), allowing respondents and reviewers to rate AI-generated content.

**Request body:**
```json
{
  "rating": 4,
  "comment": "Accurate but could be more concise"
}
```

- `rating` (int, required) — 1 to 5
- `comment` (string, optional)

**Response (200):** the updated `AILogResponse` with `feedback_rating`, `feedback_comment`, `feedback_by`, and `feedback_at` populated.

Returns 404 if the log entry is not found.

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

Worker-proxied endpoints (`generate-questions`, `scaffold-options`, `review-assist`, `extract-questions`, `extract-from-file`) return `{task_id, status}` on acceptance (HTTP 200). Poll `GET /api/v1/ai/tasks/{task_id}` for completion. They return 503 if `WORKER_URL` is not configured, or 502 if the worker does not respond.

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
| `/api/v1/source-documents/{id}` | `GET` | Get a single source document (includes body) | 200 |
| `/api/v1/source-documents/{id}/download` | `GET` | Download document body as text file | 200 |
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

### Download

Returns the document body as a `text/plain` attachment. The filename is derived from the document title with `.txt` extension.

### Update

Only `document_summary` and `question_count` can be patched. Both fields are optional; only provided fields are updated.

**Request body:**
```json
{"document_summary": "...", "question_count": 5}
```

### Delete

Deleting a source document nullifies the `source_document_id` on any linked questions before removing the document. Returns 204 with no body.

---

## Real-Time Events (SSE)

### `GET /questions/{question_id}/events?token=<jwt>`

Server-Sent Events endpoint for real-time answer status updates on a question. The browser holds a persistent connection and receives events as they happen — no polling needed.

**Authentication**: JWT passed via `token` query parameter (the browser's `EventSource` API cannot set custom headers).

**Event types**:

| Event | Fired when | Payload fields |
|-------|-----------|----------------|
| `answer_status_changed` | Answer status transitions (submit, review verdict, reviewer assignment) | `answer_id`, `status`, `previous_status` (optional) |

**SSE format**:
```
event: answer_status_changed
data: {"type":"answer_status_changed","answer_id":"...","status":"approved","previous_status":"under_review"}
```

**Keepalive**: A comment (`: keepalive`) is sent every 30 seconds to prevent proxy/browser timeout. An initial `: connected` comment is sent on connection.

**Reconnection**: The browser's `EventSource` API auto-reconnects on connection loss with exponential backoff.

---

## Visibility Rules

Not captured in OpenAPI:

- **`GET /questions`** returns all published questions **plus** the caller's own questions in any status. Other users' drafts are not visible.
- **`GET /questions/{question_id}/answers`** visibility depends on the caller's relationship to the question and answer.
- **Quality feedback** is limited to one entry per user per question (enforced by unique constraint).
- **Answer options** are shown to respondents only when `show_suggestions` is true. Admins always see options regardless of the flag.
- **Service account API keys** are returned exactly once at creation (and on rotation). They cannot be retrieved later.
