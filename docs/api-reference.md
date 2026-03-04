# API Reference

Base URL: `/api/v1`

All endpoints require authentication unless noted. Pass a JWT token via `Authorization: Bearer <token>` or an API key via `X-API-Key: <key>`.

---

## Authentication

### POST /auth/google

Exchange a Google OAuth authorization code for a JWT token.

**Body:** `{ "code": "string" }`

**Response 200:**
```json
{
  "access_token": "eyJ...",
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "Jane Doe",
  "roles": ["author", "respondent"]
}
```

If the user doesn't exist, an account is created with the `respondent` role. If the email matches `BOOTSTRAP_ADMIN_EMAIL`, all roles are granted.

### POST /auth/dev-login

Development-only login. Returns 404 when `GOOGLE_CLIENT_ID` is configured.

**Body:** none

**Response 200:** same schema as `/auth/google`

Creates a dev admin user (`dev@localhost`) with all roles on first call.

### POST /auth/refresh

Refresh an existing token.

**Query:** `?token=<jwt>`

**Response 200:** same schema as `/auth/google`

---

## Questions

### POST /questions

Create a question in draft status.

**Requires:** `author` or `admin` role

**Body:**
```json
{
  "title": "string (required)",
  "body": "string (required)",
  "category": "string (optional)"
}
```

### GET /questions

List questions. Returns published questions plus the caller's own questions in any status.

**Query params:** `status`, `category`, `skip` (default 0), `limit` (default 50)

### GET /questions/categories

List all distinct category values.

### GET /questions/{id}

Get a single question with its answer options and creator info.

### PATCH /questions/{id}

Update a question. Editable fields: `title`, `body`, `category`, `review_policy`, `show_suggestions`.

**Requires:** question owner (draft only) or admin

### DELETE /questions/{id}

Delete a draft question.

**Requires:** question owner or admin

### State Transitions

All return the updated question.

| Endpoint | Transition | Role |
|----------|-----------|------|
| POST /questions/{id}/submit | draft → proposed | author, admin |
| POST /questions/{id}/start-review | proposed → in_review | admin |
| POST /questions/{id}/publish | in_review → published | admin |
| POST /questions/{id}/reject | in_review → draft | admin |
| POST /questions/{id}/close | published → closed | admin |
| POST /questions/{id}/archive | closed → archived | admin |

### Answer Options

**POST /questions/{id}/options** — Create options. Body: `{ "options": [{ "body": "string", "display_order": 0 }] }`

**GET /questions/{id}/options** — List options for a question.

### Quality Feedback

**POST /questions/{id}/feedback** — Submit rating. Body: `{ "rating": 4, "comment": "optional" }`. One per user.

**GET /questions/{id}/feedback** — List all feedback.

---

## Answers

### POST /questions/{question_id}/answers

Create a draft answer for a published question.

**Body:** `{ "body": "string", "selected_option_id": "uuid (optional)" }`

### GET /questions/{question_id}/answers

List answers. **Query:** `status`, `skip`, `limit`

### GET /answers/{id}

Get answer with author info.

### PATCH /answers/{id}

Update a draft or revision-requested answer. **Body:** `{ "body": "string", "selected_option_id": "uuid" }`

### POST /answers/{id}/submit

Submit for review. Creates version 1 revision. Transitions: draft → submitted.

### POST /answers/{id}/revise

Revise an approved answer. Creates a new revision and resets status to submitted.

### Versions

**GET /answers/{id}/versions** — List all revisions.

**GET /answers/{id}/versions/{version}** — Get a specific revision.

**GET /answers/{id}/diff?from=1&to=2** — Unified diff between two versions.

### Collaborators

**POST /answers/{id}/collaborators** — Add collaborator. Body: `{ "user_id": "uuid" }`

**GET /answers/{id}/collaborators** — List collaborators.

**DELETE /answers/{id}/collaborators/{user_id}** — Remove collaborator.

---

## Reviews

### POST /reviews

Create a review assignment.

**Requires:** `reviewer` or `admin` role

**Body:** `{ "target_type": "question|answer", "target_id": "uuid" }`

### GET /reviews

List reviews. **Query:** `target_type`, `target_id`, `reviewer_id`

### GET /reviews/my-queue

Get the current user's pending reviews (verdict = pending).

### GET /reviews/{id}

Get review with comments.

### PATCH /reviews/{id}

Submit verdict.

**Body:** `{ "verdict": "approved|changes_requested|rejected", "comment": "optional" }`

When all reviews for an answer are resolved, the answer status is updated automatically based on verdict consensus.

### POST /reviews/{id}/comments

Add a comment. **Body:** `{ "body": "string", "parent_id": "uuid (optional for threading)" }`

---

## Service Accounts (Admin)

### POST /service-accounts

Create a service account. Returns the API key once — store it securely.

**Body:** `{ "display_name": "string", "model_id": "string (optional)", "system_version": "string (optional)" }`

### GET /service-accounts

List all service accounts.

### GET /service-accounts/{id}

Get a service account.

### PATCH /service-accounts/{id}

Update metadata. **Body:** `{ "display_name": "string", "model_id": "string", "system_version": "string" }`

### POST /service-accounts/{id}/rotate-key

Rotate the API key. Returns the new key once.

---

## AI Logs (Admin)

### GET /ai-logs

List AI interaction logs. **Query:** `service_user_id`, `endpoint`, `skip`, `limit`

### GET /ai-logs/export?format=json|csv

Export logs.

### GET /ai-logs/{id}

Get a single log entry.

### POST /ai-logs/{id}/feedback

Submit human feedback on an AI interaction. **Body:** `{ "rating": 1-5, "comment": "optional" }`

---

## Users

### GET /users/me

Get the current authenticated user.

### GET /users

List all users. **Requires:** admin. **Query:** `skip`, `limit`

### POST /users/{id}/roles

Assign a role. **Requires:** admin. **Body:** `{ "role_name": "admin|author|respondent|reviewer" }`

### DELETE /users/{id}/roles/{role_name}

Remove a role. **Requires:** admin.

---

## Health

### GET /health

**No auth required.**

**Response 200:** `{ "status": "ok" }`
