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

## Visibility Rules

Not captured in OpenAPI:

- **`GET /questions`** returns all published questions **plus** the caller's own questions in any status. Other users' drafts are not visible.
- **`GET /questions/{question_id}/answers`** visibility depends on the caller's relationship to the question and answer.
- **Quality feedback** is limited to one entry per user per question (enforced by unique constraint).
- **Service account API keys** are returned exactly once at creation (and on rotation). They cannot be retrieved later.
