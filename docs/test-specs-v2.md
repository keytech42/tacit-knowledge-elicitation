# Test Specifications v2 — Plans A, B, C, D

Test specifications for the four parallel feature plans.

---

## Plan A: Slack Thread Lifecycle

### New Functionality
- `slack_thread_ts` column on `questions` table
- `FRONTEND_URL` config setting
- `notify_question_published()` creates a Slack thread (main message + body reply), stores `thread_ts`
- All Slack messages replace `Question ID: {uuid}` with clickable links
- `notify_state_change()` posts to question's thread on state changes

### Unit Tests — `test_slack_threads.py`

#### Thread Creation
1. **`test_notify_published_creates_thread`** — `notify_question_published` calls `chat_postMessage` twice: once for the main message (returns `thread_ts`), once as a reply with the question body. Verify `thread_ts` parameter on second call.
2. **`test_notify_published_stores_thread_ts`** — After `notify_question_published`, the question's `slack_thread_ts` column is updated with the returned `ts` value.
3. **`test_notify_published_no_op_when_disabled`** — When `SLACK_BOT_TOKEN` is empty, no `chat_postMessage` calls are made, no `slack_thread_ts` written.

#### Link Formatting
4. **`test_message_contains_clickable_link`** — Verify the published notification message contains `<{frontend_url}/questions/{id}|View question>` instead of `Question ID: {uuid}`.
5. **`test_link_formatting_with_no_frontend_url`** — When `FRONTEND_URL` is empty, falls back to `Question ID: {uuid}`.
6. **`test_all_notification_types_use_links`** — Verify that `notify_answer_submitted`, `notify_review_verdict`, etc. all use the clickable link format when `FRONTEND_URL` is set.

#### State Change Thread Replies
7. **`test_state_change_posts_to_thread`** — `notify_state_change` calls `chat_postMessage` with `thread_ts` matching the question's stored `slack_thread_ts`.
8. **`test_state_change_no_op_when_no_thread`** — If question has no `slack_thread_ts`, `notify_state_change` is a no-op (no exception, no Slack call).
9. **`test_state_change_message_content`** — Verify the thread reply includes the new state and actor name.

#### Integration Tests (Route-level)
10. **`test_publish_route_stores_thread_ts`** — Publishing a question via `POST /questions/{id}/publish` results in `slack_thread_ts` being set on the question record.
11. **`test_close_route_triggers_thread_reply`** — Closing a published question triggers `notify_state_change` with the question's `slack_thread_ts`.
12. **`test_archive_route_triggers_thread_reply`** — Archiving triggers a thread reply.
13. **`test_reject_route_triggers_thread_reply`** — Rejecting (in_review -> draft) triggers a thread reply if the question has a `slack_thread_ts`.

### Edge Cases
- Thread creation fails (Slack API error) — question still publishes successfully
- `slack_thread_ts` is None for questions published before the feature was added

---

## Plan B: Targeted Slack Notifications & DMs

### New Functionality
- `_send_dm()` using `conversations.open` + `chat.postMessage`
- DM on respondent assignment (depends on Plan C)
- DM on `changes_requested` review verdict

### Unit Tests — `test_slack_dm.py`

#### DM Infrastructure
1. **`test_send_dm_opens_conversation_and_posts`** — `_send_dm` calls `conversations.open` with the Slack user ID, then `chat.postMessage` to the returned channel.
2. **`test_send_dm_handles_conversation_open_error`** — If `conversations.open` fails, no message is sent, no exception propagates.
3. **`test_send_dm_handles_post_error`** — If `chat.postMessage` fails after opening conversation, no exception propagates.
4. **`test_send_dm_skips_when_no_slack_user`** — If email lookup returns None, no DM is attempted.
5. **`test_send_dm_skips_when_disabled`** — When Slack is disabled, DM is a no-op.

#### Assignment DMs
6. **`test_notify_respondent_assigned_sends_dm`** — When a respondent is assigned, a DM is sent containing the question title and a link.
7. **`test_notify_respondent_assigned_no_dm_when_no_email`** — If the respondent has no email, DM is skipped (no error).
8. **`test_notify_respondent_assigned_message_content`** — DM includes question title, link, and assigner name.

#### Changes Requested DMs
9. **`test_changes_requested_sends_dm_to_respondent`** — When review verdict is `changes_requested`, a DM is sent to the answer author.
10. **`test_changes_requested_dm_includes_reviewer_comment`** — The DM includes the reviewer's comment text.
11. **`test_changes_requested_dm_no_op_when_no_email`** — Gracefully skips DM when author has no email.

#### Integration Tests
12. **`test_assign_respondent_route_triggers_dm`** — `POST /questions/{id}/assign-respondent` triggers the DM function.
13. **`test_review_changes_requested_triggers_dm`** — Submitting a `changes_requested` verdict via `PATCH /reviews/{id}` triggers the DM function.

### Edge Cases
- User exists in platform but not in Slack workspace
- Rate limiting on `conversations.open`
- DM to deactivated Slack user

---

## Plan C: Respondent Assignment

### New Functionality
- `assigned_respondent_id` FK on `questions` table
- `POST /questions/{id}/assign-respondent` endpoint (admin-only)
- `QuestionResponse` schema includes `assigned_respondent` field
- Frontend: "Assign" button

### Tests — `test_respondent_assignment.py`

#### Endpoint: Assign Respondent
1. **`test_assign_respondent_success`** — Admin can assign a respondent user to a published question. Returns 200 with `assigned_respondent` populated.
2. **`test_assign_respondent_replaces_previous`** — Assigning a new respondent replaces the previous assignment.
3. **`test_assign_respondent_requires_admin`** — Non-admin users receive 403.
4. **`test_assign_respondent_author_forbidden`** — Author role alone cannot assign.
5. **`test_assign_respondent_respondent_forbidden`** — Respondent role alone cannot assign.
6. **`test_assign_respondent_question_not_found`** — Returns 404 for nonexistent question ID.
7. **`test_assign_respondent_user_not_found`** — Returns 404 if the target user_id does not exist.
8. **`test_assign_respondent_non_respondent_user`** — Assigning a user without the respondent role should return 400/409 (or succeed — depends on business decision; test documents behavior).

#### Schema Validation
9. **`test_question_response_includes_assigned_respondent`** — `GET /questions/{id}` response includes `assigned_respondent` field (null when unassigned, UserResponse when assigned).
10. **`test_question_list_includes_assigned_respondent`** — `GET /questions` list response includes the field.

#### State Constraints
11. **`test_assign_to_draft_question`** — Assignment to a non-published question (draft, proposed, in_review) — verify behavior (likely returns 409).
12. **`test_assign_to_closed_question`** — Verify behavior for closed/archived questions.
13. **`test_unassign_respondent`** — Assign with `null` user_id unassigns (or separate endpoint).

### Edge Cases
- Assign the question's own author as respondent
- Assign the same respondent twice (idempotent)
- Question state changes after assignment (close, archive)

---

## Plan D: Markdown Rendering

### Scope
Frontend-only changes (React component). No backend tests needed.

### Manual/Visual Test Checklist
1. Question body renders markdown (headings, bold, italic, links, code blocks)
2. Answer body renders markdown
3. Review comments render markdown
4. AI review comments render markdown
5. GFM tables render correctly
6. Escaped `\n` in AI review strings are converted to actual newlines before rendering
7. XSS: embedded `<script>` tags are sanitized
8. Empty content renders without errors
9. Very long content with many headings renders without performance issues

---

## Cross-Plan Integration Tests

### A + C: Thread lifecycle with assignment
- Assigning a respondent to a question with a Slack thread should NOT post to the thread (assignment is not a state change)

### A + B: Thread + DMs
- Publishing a question creates a thread AND if a respondent is pre-assigned, sends a DM

### B + C: Assignment triggers DM
- The full flow: admin assigns respondent via endpoint -> DM is sent with question link

### Full E2E: A + B + C
- Publish question (creates thread) -> Assign respondent (sends DM) -> Respondent submits answer (thread reply + channel notification) -> Review with changes_requested (thread reply + DM to respondent)
