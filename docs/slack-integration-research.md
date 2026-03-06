# Slack Integration Research

**Date**: March 6, 2026
**Status**: Complete
**Scope**: Implementation approach for Slack notifications in the Knowledge Elicitation Platform

## Executive Summary

This document summarizes research into Slack API integration approaches for the Knowledge Elicitation Platform. The recommended approach is to use **Slack Bot Tokens with the Web API** for sending rich notifications directly from the backend (not through the worker service), with user lookup via email for @mentions.

## 1. Slack API Approach: Bot Tokens vs Webhooks vs Incoming Webhooks

### Decision: Use Slack Bot Tokens + Web API

**Why Bot Tokens**:
- Bidirectional capability: can both send AND receive messages (needed for future interactive features like reply threads, reactions, slash commands)
- User lookup capability: can use `users.lookupByEmail` to find Slack user IDs for @mentions
- Message editing/deletion: can modify/delete posted messages (useful for status updates)
- Rich formatting: full Block Kit support for interactive elements

**Why NOT Incoming Webhooks**:
- Incoming webhooks are **one-way only**: can only send, never receive
- No user lookup: cannot @mention specific users by email
- Cannot edit/delete messages
- Less flexible for future enhancements

**Why NOT Events API**:
- Events API is for receiving events FROM Slack (message posted, user joined, etc.)
- Not needed for outbound notifications
- Would add unnecessary complexity

### Recommended Architecture

```
Knowledge Elicitation Platform (Backend)
    ↓
Slack Web API (chat.postMessage)
    ↓
Slack Workspace
    ↓ (user reads notification in channel)
```

The backend directly calls Slack Web API methods. No webhook receivers needed.

---

## 2. User Mapping: Email → Slack User ID

### Decision: Use `users.lookupByEmail` + Optional Caching

**How it works**:
1. Platform user has an email address (from Google OAuth or dev login)
2. When sending a notification, look up the Slack user ID using `users.lookupByEmail`
3. Use the Slack user ID to @mention them in the message: `<@USER_ID>`

**API Details**:
- **Method**: `users.lookupByEmail` (GET)
- **Required Scope**: `users:read.email`
- **Rate Limit**: Tier 3 (50+ requests per minute)
- **Error Handling**: Returns `users_not_found` if user not in Slack

**Success Response Example**:
```json
{
  "ok": true,
  "user": {
    "id": "U012ABC123",
    "name": "spengler",
    "real_name": "Egon Spengler",
    "profile": {
      "email": "spengler@ghostbusters.example.com",
      "display_name": "spengler"
    }
  }
}
```

### Caching Strategy (Optional)

**Recommendation**: Don't cache initially; call `users.lookupByEmail` every time.

**Reasons**:
- Rate limit is generous (50+ per minute)
- Email → Slack ID mapping is stable (doesn't change)
- Cache invalidation is simple (only invalidate on user deletion)
- Keeps implementation simpler for MVP

**If caching later becomes needed**:
- Add optional `slack_user_id` field to the `User` model
- Store it on first lookup
- Cache expires when user modifies email
- Cost: one schema migration

### Handling Missing Users

If a user doesn't have a Slack account or isn't in the workspace:
1. **Option A** (recommended): Don't mention them; include a note: "Notification sent to #channel (user not in Slack)"
2. **Option B**: Send to the channel without @mention
3. **Option C**: Skip notification entirely

Recommendation: **Option A** — always send the notification but gracefully handle missing mentions.

---

## 3. Required Scopes and Admin Setup Steps

### Bot Token Scopes Required

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to channels and DMs |
| `chat:write.public` | Post messages in public channels |
| `users:read.email` | Look up users by email address |
| `users:read` | Read user info (required by `users:read.email`) |

**Rationale**: Minimal set needed for sending rich notifications and mentioning users.

### Step-by-Step Setup Guide for Workspace Admin

#### Step 1: Create the Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Give it a name: e.g., "Knowledge Elicitation Bot"
5. Select your workspace
6. Click **"Create App"**

#### Step 2: Configure OAuth Scopes

1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Click **"Add an OAuth Scope"** and add:
   - `chat:write`
   - `chat:write.public`
   - `users:read.email`
   - `users:read`

#### Step 3: Install App to Workspace

1. Scroll to top of the same page, click **"Install to Workspace"**
2. Review permissions and click **"Allow"**
3. **SAVE the Bot Token** (starts with `xoxb-`) — this goes in the environment variable

#### Step 4: Configure Environment Variable

In your deployment, set:
```
SLACK_BOT_TOKEN=xoxb-your-token-here
```

Or for docker-compose development:
```bash
# In .env file
SLACK_BOT_TOKEN=xoxb-your-token-here
```

#### Step 5: (Optional) Enable Event Subscriptions for Future Features

If you want to handle incoming messages (slash commands, reactions, etc.) later:

1. In app settings, go to **"Event Subscriptions"**
2. Turn it **"On"**
3. Set Request URL to your backend webhook endpoint: `https://your-domain/api/v1/slack/events`
4. Slack will send a challenge request — verify and respond with the challenge value
5. Subscribe to desired events (e.g., `app_mention`, `message.channels`)

**Note**: For MVP, skip this step — only needed for interactive features.

---

## 4. Notification Events Matrix

### Which State Transitions Should Trigger Notifications?

**Recommended initial events** (MVP):

| Event | Trigger | Notify | Channel | Details |
|-------|---------|--------|---------|---------|
| **Question Published** | Question: `draft → proposed → published` | Question author + reviewers | `#questions` (or dedicated channel) | New question ready for answering |
| **Answer Submitted** | Answer: `draft → submitted` | Question author + reviewers | `#answers` or thread | New answer ready for review |
| **Review Submitted** | Review: verdict added | Answer author | DM or thread | Review result (approved/revision/rejected) |
| **Revision Requested** | Answer: `approved → submitted` | Reviewers | `#answers` | Author revised their answer |

### Design Considerations

**Channel-based vs DM**:
- **Channel-based** (recommended): Public record, team awareness, easier to implement
- **DM**: More private, but breaks team awareness
- **Thread replies**: Adds context but requires tracking message IDs

**Notification Format**:
- Include direct link to the object in the platform
- Include relevant metadata (author, deadline, etc.)
- Use Block Kit for rich formatting with buttons/links

---

## 5. Architecture Decision: Worker vs Direct Backend Call

### Decision: Send Notifications Directly from Backend (NOT via Worker)

**Reasons**:

1. **Speed**: Slack API calls are fast (<1s typically), vs LLM tasks (5-30s)
2. **Latency Sensitivity**: Users expect immediate notification after state change
3. **Failure Tolerance**: If Slack is down, we still want the question/answer to succeed
4. **Existing Pattern**: Backend already has `worker_client.py` showing fire-and-forget pattern
5. **Simpler Error Handling**: No task tracking needed; just log failures silently

### Recommended Architecture

```
Backend Handler (routes/services)
    └─ (on state change)
       └─ Call slack_client.send_notification()
          └─ Try/except wrapped, logs failure, doesn't block

Slack Client (services/slack_client.py)
    ├─ User lookup (users.lookupByEmail)
    ├─ Message formatting (Block Kit)
    └─ Chat posting (chat.postMessage)
```

### Why NOT the Worker

- Worker is designed for **long-running, async tasks** (LLM generation, embeddings)
- Slack notifications are **synchronous, fast operations**
- Would add unnecessary latency and complexity
- Fire-and-forget pattern is simpler to implement in backend

**Future**: If you later add async webhooks or streaming notifications, THEN consider routing through worker.

---

## 6. Message Formatting: Block Kit vs mrkdwn

### Decision: Use Block Kit for Rich Formatting

**Block Kit advantages**:
- Rich visual hierarchy (sections, dividers, buttons)
- Interactive elements (links, buttons for deep linking)
- Consistent formatting across workspace
- Better mobile experience
- Metadata display (author, timestamps, approval status)

**mrkdwn advantages**:
- Simpler, fewer lines of code
- Faster to parse/render
- Sufficient for basic formatted text

### Recommended Block Kit Structure

```
┌─────────────────────────────────────┐
│ Question Published                  │  ← Header (mrkdwn)
├─────────────────────────────────────┤
│ *Title*: "What is knowledge?"       │  ← Key fields (context)
│ *Author*: @john.doe                 │
│ *Category*: Philosophy              │
├─────────────────────────────────────┤
│ [View in Platform]  [Reply Thread]  │  ← Buttons/links
└─────────────────────────────────────┘
```

### Example Block Kit Payload (simplified)

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "New Question Published"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "*Title*\nWhat is knowledge elicitation?"
        },
        {
          "type": "mrkdwn",
          "text": "*Author*\n<@U012ABC123>"
        }
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "<https://platform.example.com/questions/123|View in Platform>"
      }
    }
  ]
}
```

---

## 7. Concerns and Mitigations

### A. Rate Limiting

**Slack Rate Limits**:
- `chat.postMessage`: 1 message per second per channel (burst tolerance ~1-2)
- `users.lookupByEmail`: 50+ per minute (Tier 3)

**Mitigation**:
- ✅ Our notification volume is low (typically 1-10 per minute platform-wide)
- ✅ Never batch notifications to same channel in rapid succession
- ✅ If rate limited (HTTP 429), read `Retry-After` header and retry later
- ✅ Implement exponential backoff for retries

**Implementation**:
```python
# In slack_client.py
try:
    resp = await client.post("chat.postMessage", json=payload)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 10))
        logger.warning(f"Slack rate limited, retrying after {retry_after}s")
        await asyncio.sleep(retry_after)
        # retry...
except Exception:
    logger.exception("Failed to post Slack message")
    # Don't raise; let the original operation (create question, etc.) succeed
```

### B. Token Security

**Risk**: Leak of `SLACK_BOT_TOKEN` would allow unauthorized Slack access.

**Mitigations**:
- Store token as environment variable only (never in code)
- Rotate token if leaked (easy: new token in Slack admin)
- Don't log token in error messages
- Use secrets management in production (AWS Secrets Manager, Vault, etc.)

### C. Service Downtime Handling

**If Slack is down**:
- Backend catches exceptions and logs silently (doesn't block main operation)
- User's action (publish question, submit answer) still succeeds
- Notification is simply lost or retried later
- Admin should monitor logs for Slack service errors

**If backend loses connectivity to Slack**:
- Same as above — fail silently, log, main operation succeeds

### D. User Not Found

**If email doesn't exist in Slack**:
- `users.lookupByEmail` returns `{"ok": false, "error": "users_not_found"}`
- Recommendation: Send message without @mention, include note
- Log a warning so admin knows the user isn't in Slack

### E. Channel Configuration

**Risk**: Hardcoding a channel name that doesn't exist.

**Mitigation**:
- Allow channel name to be configured per notification type
- Validate channel exists at startup (optional)
- Fall back to a default channel if specific channel doesn't exist
- Make it easy to change via environment variables

**Example**:
```
SLACK_QUESTIONS_CHANNEL=#general
SLACK_ANSWERS_CHANNEL=#general
SLACK_REVIEWS_CHANNEL=#general
```

---

## 8. Implementation Checklist

### Phase 1: Setup (Admin)
- [ ] Create Slack app in workspace
- [ ] Add OAuth scopes: `chat:write`, `users:read.email`, `users:read`
- [ ] Install app to workspace
- [ ] Get bot token `xoxb-...`
- [ ] Set `SLACK_BOT_TOKEN` environment variable

### Phase 2: Backend Implementation
- [ ] Add `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_*` to `app/config.py`
- [ ] Create `app/services/slack_client.py` with methods:
  - `lookup_user_by_email(email)` → Slack user ID or None
  - `format_notification(type, data)` → Block Kit JSON
  - `send_notification(channel, blocks)` → fire-and-forget
- [ ] Add notification triggers in service layer:
  - `services/question.py` — on publish
  - `services/answer.py` — on submit
  - `services/review.py` — on verdict
- [ ] Add environment configuration for channels

### Phase 3: Testing
- [ ] Unit tests for `slack_client.py` (mock httpx)
- [ ] Integration tests in test harness (real workspace)
- [ ] Manual testing in dev workspace

### Phase 4: Documentation
- [ ] Document setup steps for admins
- [ ] Document notification types and format
- [ ] Add troubleshooting guide

---

## 9. Implementation Details Reference

### Slack Client Pattern (from research)

Based on existing `worker_client.py` pattern:

```python
# app/services/slack_client.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return bool(settings.SLACK_BOT_TOKEN)


async def _post(endpoint: str, payload: dict) -> dict | None:
    """Fire-and-forget POST to Slack Web API."""
    if not _is_enabled():
        return None

    url = f"https://slack.com/api/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"Slack error: {data.get('error')}")
            return data
    except Exception:
        logger.exception(f"Slack call failed: POST {endpoint}")
        return None


async def lookup_user_by_email(email: str) -> str | None:
    """Get Slack user ID from email. Returns None if not found."""
    result = await _post("users.lookupByEmail", {"email": email})
    if result and result.get("ok"):
        return result["user"]["id"]
    return None


async def send_notification(channel: str, blocks: list) -> bool:
    """Send notification to channel. Returns success status."""
    result = await _post("chat.postMessage", {
        "channel": channel,
        "blocks": blocks
    })
    return bool(result and result.get("ok"))
```

### Integration Pattern in Services

```python
# app/services/question.py

async def publish(question_id: UUID, db: AsyncSession) -> Question:
    # ... existing publish logic ...
    question = await db.get(Question, question_id)

    # Fire-and-forget Slack notification
    asyncio.create_task(_send_slack_question_published(question))

    return question


async def _send_slack_question_published(question: Question) -> None:
    """Background task: send Slack notification (never blocks)."""
    try:
        # Build Block Kit message
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Question Published"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{question.title}*"}},
            # ... more blocks ...
        ]

        await slack_client.send_notification(
            channel=settings.SLACK_QUESTIONS_CHANNEL,
            blocks=blocks
        )
    except Exception:
        # Already logged inside slack_client; nothing to do
        pass
```

---

## 10. Summary and Recommendations

### Recommended Approach

1. **Use Slack Bot Token + Web API** for sending notifications directly from backend
2. **Use `users.lookupByEmail`** to find users for @mentions (no caching initially)
3. **Send from backend** (not through worker) — faster, simpler
4. **Use Block Kit** for rich, consistent formatting
5. **Fire-and-forget pattern** — log failures, don't block main operations
6. **Start with public channels** — team awareness, simpler implementation

### Why This Approach

- ✅ Fast: Slack API calls <1s, no LLM latency
- ✅ Simple: No new services, uses existing backend patterns
- ✅ Reliable: Fire-and-forget doesn't block platform operations
- ✅ Future-proof: Can add interactive features (buttons, slash commands) later
- ✅ User-friendly: Real-time notifications with @mentions

### Next Steps (for backend engineer)

See **Implementation Checklist** above. Key deliverables:
1. `app/services/slack_client.py` — HTTP client wrapper
2. Update `app/config.py` — environment variables
3. Add notification calls to `services/question.py`, `services/answer.py`, `services/review.py`
4. Tests in `tests/test_slack_integration.py`

---

## References

- [Slack Web API Methods](https://docs.slack.dev/reference/methods)
- [users.lookupByEmail](https://docs.slack.dev/reference/methods/users.lookupByEmail/)
- [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage)
- [Block Kit Overview](https://docs.slack.dev/block-kit)
- [Rate Limits](https://docs.slack.dev/apis/web-api/rate-limits/)
- [OAuth & Permissions Setup](https://docs.slack.dev/authentication/installing-with-oauth/)
