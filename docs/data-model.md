# Data Model

## Entity Relationship Overview

```
User ──┬── Role (many-to-many via user_roles)
       │
       ├── Question (created_by, confirmed_by)
       │     ├── AnswerOption (created_by)
       │     └── QuestionQualityFeedback (user)
       │
       ├── Answer (author, question)
       │     ├── AnswerRevision (created_by)
       │     └── AnswerCollaborator (user, granted_by)
       │
       ├── Review (reviewer, assigned_by → question or answer)
       │     └── ReviewComment (author, parent → self)
       │
       └── AIInteractionLog (service_user, feedback_by)
```

## Users and Roles

### User

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| user_type | enum | `human` or `service` |
| external_id | string | Google OAuth ID (unique, nullable) |
| display_name | string | |
| email | string | Unique, nullable |
| is_active | boolean | Default true |
| avatar_url | string | Nullable |
| model_id | string | For service accounts (e.g. `claude-sonnet-4-6`) |
| system_version | string | For service accounts |
| api_key_hash | string | SHA256 hash of API key |

### Role

Four fixed roles: `admin`, `author`, `respondent`, `reviewer`.

The `permissions` JSONB field is reserved for future fine-grained permission control.

### Role Capabilities

| Action | admin | author | respondent | reviewer |
|--------|-------|--------|------------|----------|
| Create questions | yes | yes | - | - |
| Answer questions | yes | yes | yes | - |
| Review content | yes | - | - | yes |
| Manage users/roles | yes | - | - | - |
| Manage service accounts | yes | - | - | - |
| View AI logs | yes | - | - | - |
| Publish/close questions | yes | - | - | - |

## Questions

### Question

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| title | string(500) | |
| body | text | |
| category | string(255) | Indexed, nullable |
| status | enum | See state machine below |
| confirmation | enum | `pending`, `confirmed`, `rejected`, `revised` |
| review_policy | JSONB | Review configuration (see below) |
| show_suggestions | boolean | Show answer options to respondents |
| quality_score | float | Average of feedback ratings |
| embedding | vector(1536) | pgvector embedding, nullable (generated when `EMBEDDING_MODEL` is set) |
| created_by_id | UUID | FK → users |
| confirmed_by_id | UUID | FK → users, nullable |

### Question State Machine

```
DRAFT ──[submit]──▶ PROPOSED ──[start-review]──▶ IN_REVIEW ──[publish]──▶ PUBLISHED ──[close]──▶ CLOSED ──[archive]──▶ ARCHIVED
                                                     │
                                                     └──[reject]──▶ DRAFT
```

- **submit**: author or admin, moves to proposed
- **start-review**: admin only
- **publish**: admin only, sets default review_policy if absent
- **reject**: admin only, returns to draft for rework
- **close/archive**: admin only

### Review Policy

```json
{
  "min_approvals": 1,
  "auto_assign": false,
  "allow_self_review": false,
  "require_comment_on_reject": true
}
```

The optional field `auto_assign_count` (default: 1) controls how many reviewers are auto-assigned when `auto_assign` is true.

### AnswerOption

Pre-defined answer choices for a question. Each has a `body` and `display_order`. Created by the question author or via AI scaffolding (which replaces all existing options with up to 4 maximally distinct choices).

### QuestionQualityFeedback

Per-user rating and optional comment. Unique constraint on (question_id, user_id) — one feedback per user per question.

## Answers

### Answer

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| question_id | UUID | FK → questions |
| author_id | UUID | FK → users |
| body | text | |
| selected_option_id | UUID | FK → answer_options, nullable |
| status | enum | See state machine below |
| current_version | integer | Incremented on each revision |
| embedding | vector(1536) | pgvector embedding, nullable (generated when `EMBEDDING_MODEL` is set) |

### Answer State Machine

```
DRAFT ──[submit]──▶ SUBMITTED ──[review starts]──▶ UNDER_REVIEW
                        ▲                              │
                        │                    ┌─────────┴─────────┐
                        │                    ▼                   ▼
                   REVISION_REQUESTED      APPROVED          REJECTED
                                             │
                                             └──[revise]──▶ SUBMITTED
```

- **submit**: author, creates version 1 revision
- **review verdict**: reviewer sets `approved`, `changes_requested`, or `rejected`
- **resolution logic**: if any `changes_requested` → revision_requested; if any `rejected` → rejected; if approvals ≥ min_approvals → approved
- **revise**: author/collaborator/admin can revise approved answers, which resets to submitted

### AnswerRevision

Immutable snapshot of an answer at a point in time.

| Field | Type | Notes |
|-------|------|-------|
| answer_id | UUID | FK → answers |
| version | integer | Sequential version number |
| body | text | Content at this version |
| trigger | enum | See triggers below |
| content_hash | string | SHA-256 of normalized content (duplicate detection) |
| previous_status | string | Answer status before this revision |
| created_by_id | UUID | FK → users |

**Revision triggers:**

| Trigger | When |
|---------|------|
| `initial_submit` | First submission (version 1) |
| `revision_after_review` | Resubmission after review feedback |
| `post_approval_update` | Revision of an already-approved answer |

Unique constraint on (answer_id, version).

### AnswerCollaborator

Grants a user edit access to an answer. The answer author or admin can manage collaborators. Unique constraint on (answer_id, user_id).

## Reviews

### Review

| Field | Type | Notes |
|-------|------|-------|
| target_type | enum | `question` or `answer` |
| target_id | UUID | Polymorphic FK |
| reviewer_id | UUID | FK → users |
| assigned_by_id | UUID | FK → users, nullable |
| verdict | enum | `pending`, `approved`, `changes_requested`, `rejected` |
| comment | text | Nullable |
| answer_version | integer | Nullable — which answer version this review applies to |

Indexed on (target_type, target_id).

### ReviewComment

Threaded comments on a review. Self-referencing `parent_id` enables nesting.

## AI Interaction Log

Automatically populated by the AI logging middleware for all write operations from service accounts.

| Field | Type | Notes |
|-------|------|-------|
| service_user_id | UUID | FK → users |
| model_id | string | Copied from service account at request time |
| endpoint | string | `POST /api/v1/questions`, etc. |
| request_body | JSONB | Full request payload |
| response_status | integer | HTTP status code |
| latency_ms | integer | Request duration |
| token_usage | JSONB | Reserved for token tracking |
| created_entity_type | string | Nullable — type of entity created (question, answer, etc.) |
| created_entity_id | UUID | Nullable — ID of the created entity |
| feedback_rating | integer | Human rating (1-5) |
| feedback_comment | text | Human feedback |
| feedback_by_id | UUID | FK → users |
| feedback_at | datetime | Nullable — when feedback was provided |
