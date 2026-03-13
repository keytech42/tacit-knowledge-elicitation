---
description: Rules for backend service layer
globs: backend/app/services/**
---

# Backend Services

## Layer Rules

- Services contain domain logic: state transitions, permission checks, validation.
- Accept `AsyncSession` and model instances as arguments.
- **Never import FastAPI types** (Request, Response, Depends, etc.).
- Routes call services — services never call routes.

## State Machines

Questions and answers follow strict state machines. Always use service functions for transitions — never set status directly.

- Question: `draft → proposed → in_review → published → closed → archived` (reject: `in_review → draft`)
- Answer: `draft → submitted → under_review → approved/revision_requested/rejected` (revise: `approved → submitted`)

## Event Publishing Order

**Commit before publishing events.** `flush()` is not visible to other sessions under READ COMMITTED.

```python
# RIGHT — commit first, then publish
await db.flush()
await db.commit()
publish_event(channel, {"type": "status_changed", ...})
await slack.notify(...)
```

The `get_db` dependency auto-commits after the handler returns. Calling `commit()` mid-handler is safe.

## Worker Integration

- `worker_client.py` — fire-and-forget HTTP calls (try/except wrapped, never blocks API)
- `embeddings.py` — optional, guarded by `EMBEDDING_MODEL`
- `recommendation.py` — pgvector cosine similarity or LLM-based (controlled by `RECOMMENDATION_STRATEGY`)
