"""Slack notification service — fire-and-forget, never blocks the main API.

All public functions catch exceptions internally so Slack outages or
misconfiguration never affect platform operations.

Thread lifecycle: When a question is published, a Slack thread is created.
All subsequent events for that question post as replies in that thread.
"""
import logging
import re

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from app.config import settings
from app.templates.slack import (
    fmt_answer_approved,
    fmt_answer_submitted,
    fmt_changes_requested_dm,
    fmt_question_closed,
    fmt_question_published,
    fmt_question_rejected,
    fmt_respondent_assigned,
    fmt_respondent_assigned_thread,
    fmt_review_verdict,
    fmt_reviewer_assigned_dm,
    fmt_revision_requested,
)

logger = logging.getLogger(__name__)

# In-memory cache for email → Slack user ID lookups
_slack_user_cache: dict[str, str | None] = {}

_MRKDWN_MAX_LEN = 2000


def _md_to_mrkdwn(text: str) -> str:
    """Convert markdown to Slack mrkdwn format.

    Handles: bold, headings, links, bullets, and HTML tag stripping.
    Code spans and fenced code blocks are left as-is (Slack supports backticks).
    Truncates to 2000 chars.
    """
    # Protect fenced code blocks from other transforms
    code_blocks: list[str] = []

    def _stash_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\s\S]*?```", _stash_code_block, text)

    # Protect inline code spans
    code_spans: list[str] = []

    def _stash_code_span(m: re.Match) -> str:
        code_spans.append(m.group(0))
        return f"\x00CODESPAN{len(code_spans) - 1}\x00"

    text = re.sub(r"`[^`]+`", _stash_code_span, text)

    # Links: [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)

    # Headings: # heading → *heading* (must be at line start)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Bullets: - item → • item
    text = re.sub(r"^- ", "• ", text, flags=re.MULTILINE)

    # Strip HTML tags but preserve Slack special syntax:
    # <@U123>, <#C123>, <!here>, <url|text>
    text = re.sub(r"<(?![@#!])(?![^>]*\|)[^>]*>", "", text)

    # Restore code blocks and spans
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)
    for i, span in enumerate(code_spans):
        text = text.replace(f"\x00CODESPAN{i}\x00", span)

    # Truncate
    if len(text) > _MRKDWN_MAX_LEN:
        text = text[: _MRKDWN_MAX_LEN - 3] + "..."

    return text


def _is_enabled() -> bool:
    return bool(settings.SLACK_BOT_TOKEN)


def _get_client() -> AsyncWebClient:
    return AsyncWebClient(token=settings.SLACK_BOT_TOKEN)


async def _lookup_slack_user(email: str) -> str | None:
    """Look up a Slack user ID by email. Returns None on failure.

    Results are cached in-memory for the process lifetime.
    """
    if email in _slack_user_cache:
        return _slack_user_cache[email]

    try:
        client = _get_client()
        resp = await client.users_lookupByEmail(email=email)
        user_id = resp["user"]["id"]
        _slack_user_cache[email] = user_id
        return user_id
    except SlackApiError as e:
        if e.response.get("error") == "users_not_found":
            _slack_user_cache[email] = None
            logger.debug("No Slack user found for email %s", email)
        else:
            logger.warning("Slack user lookup failed for %s: %s", email, e)
        return None
    except Exception:
        logger.exception("Slack user lookup failed for %s", email)
        return None


def _format_mention(slack_user_id: str) -> str:
    return f"<@{slack_user_id}>"


async def _mention_or_name(email: str | None, display_name: str) -> str:
    """Try to @mention by email lookup, fall back to display name."""
    if email:
        slack_id = await _lookup_slack_user(email)
        if slack_id:
            return _format_mention(slack_id)
    return display_name


async def _post_message(channel: str, text: str, thread_ts: str | None = None) -> str | None:
    """Post a message. Returns the message ts, or None on failure."""
    try:
        client = _get_client()
        resp = await client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)
        return resp.get("ts")
    except Exception:
        logger.exception("Failed to send Slack message to %s", channel)
        return None


async def _send_message(channel: str, text: str) -> None:
    """Post a message to a Slack channel. Fire-and-forget. (backward compat)"""
    await _post_message(channel, text)


def _channel() -> str:
    return settings.SLACK_DEFAULT_CHANNEL


def _question_link(question_id: str, text: str = "View question") -> str:
    return f"<{settings.FRONTEND_URL}/questions/{question_id}|{text}>"


def _answer_link(answer_id: str, text: str = "View answer") -> str:
    return f"<{settings.FRONTEND_URL}/answers/{answer_id}|{text}>"


# --- Public notification functions ---
# Each runs in a fire-and-forget task so the caller never waits.


async def _send_dm(slack_user_id: str, text: str) -> None:
    """Open a DM conversation and post a message. Fire-and-forget."""
    try:
        client = _get_client()
        resp = await client.conversations_open(users=slack_user_id)
        dm_channel = resp["channel"]["id"]
        await client.chat_postMessage(channel=dm_channel, text=text)
    except Exception:
        logger.exception("Failed to send DM to Slack user %s", slack_user_id)


async def notify_respondent_assigned(
    question_title: str,
    question_id: str,
    respondent_email: str | None,
    respondent_name: str,
    assigner_name: str,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """DM the respondent and optionally post a thread mention when assigned."""
    if not _is_enabled():
        return
    # Send DM to the respondent
    if respondent_email:
        slack_user_id = await _lookup_slack_user(respondent_email)
        if slack_user_id:
            text = fmt_respondent_assigned(
                respondent_name=respondent_name,
                assigner_name=assigner_name,
                question_title=question_title,
                question_link=_question_link(question_id),
            )
            await _send_dm(slack_user_id, text)
    # Post thread reply if the question has a Slack thread
    if slack_channel and slack_thread_ts:
        mention = await _mention_or_name(respondent_email, respondent_name)
        thread_text = fmt_respondent_assigned_thread(
            respondent_mention=mention,
            assigner_name=assigner_name,
        )
        await _post_message(slack_channel, thread_text, thread_ts=slack_thread_ts)


async def notify_changes_requested_dm(
    question_title: str,
    question_id: str,
    answer_id: str,
    author_email: str | None,
    author_name: str,
    reviewer_name: str,
    comment: str | None = None,
) -> None:
    """DM the answer author when changes are requested."""
    if not _is_enabled() or not author_email:
        return
    slack_user_id = await _lookup_slack_user(author_email)
    if not slack_user_id:
        return
    text = fmt_changes_requested_dm(
        reviewer_name=reviewer_name,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
        comment=_md_to_mrkdwn(comment) if comment else None,
    )
    await _send_dm(slack_user_id, text)


async def notify_reviewer_assigned_dm(
    question_title: str,
    answer_id: str,
    reviewer_email: str | None,
    reviewer_name: str,
    assigner_name: str,
) -> None:
    """DM the reviewer when they are assigned to review an answer."""
    if not _is_enabled() or not reviewer_email:
        return
    slack_user_id = await _lookup_slack_user(reviewer_email)
    if not slack_user_id:
        return
    text = fmt_reviewer_assigned_dm(
        reviewer_name=reviewer_name,
        assigner_name=assigner_name,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
    )
    await _send_dm(slack_user_id, text)


async def notify_question_published(
    question_title: str,
    question_id: str,
    question_body: str,
    publisher_name: str,
) -> tuple[str | None, str | None]:
    """Notify channel when a question is published. Creates a thread.

    Returns (thread_ts, channel) so the caller can store them on the Question.
    """
    if not _is_enabled() or not _channel():
        return (None, None)

    channel = _channel()
    text = fmt_question_published(
        publisher_name=publisher_name,
        question_title=question_title,
        question_link=_question_link(question_id),
    )
    thread_ts = await _post_message(channel, text)
    if not thread_ts:
        logger.warning("Failed to create Slack thread for question %s — no thread_ts returned", question_id)
        return (None, None)
    logger.info("Created Slack thread %s in %s for question %s", thread_ts, channel, question_id)

    # Post the question body as the first reply in the thread
    body_preview = _md_to_mrkdwn(question_body)
    await _post_message(channel, body_preview, thread_ts=thread_ts)

    return (thread_ts, channel)


async def notify_thread_update(
    slack_channel: str,
    slack_thread_ts: str,
    text: str,
) -> None:
    """Post a status update as a reply in an existing question thread."""
    if not _is_enabled():
        return
    await _post_message(slack_channel, text, thread_ts=slack_thread_ts)


async def notify_question_rejected(
    question_title: str,
    question_id: str,
    author_email: str | None,
    author_name: str,
    comment: str | None = None,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify the question author when their question is rejected."""
    if not _is_enabled():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = fmt_question_rejected(
        mention=mention,
        question_title=question_title,
        question_link=_question_link(question_id),
        comment=comment,
    )
    if slack_channel and slack_thread_ts:
        await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
    elif _channel():
        await _send_message(_channel(), text)


async def notify_answer_submitted(
    question_title: str,
    question_id: str,
    answer_id: str,
    author_name: str,
    answer_body: str | None = None,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify channel when an answer is submitted for review.

    If the question has a thread, posts as a reply. Otherwise posts to the default channel.
    When answer_body is provided and we're in a thread, posts the body as a follow-up reply.
    """
    if not _is_enabled():
        return
    text = fmt_answer_submitted(
        author_name=author_name,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
    )
    if slack_channel and slack_thread_ts:
        msg_ts = await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
        # Post the answer body as a follow-up reply in the thread
        if answer_body and msg_ts:
            body_preview = _md_to_mrkdwn(answer_body)
            await _post_message(slack_channel, body_preview, thread_ts=slack_thread_ts)
    elif _channel():
        await _send_message(_channel(), text)


async def notify_review_verdict(
    question_title: str,
    answer_id: str,
    verdict: str,
    reviewer_name: str,
    author_email: str | None,
    author_name: str,
    comment: str | None = None,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify when a review verdict is submitted."""
    if not _is_enabled():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = fmt_review_verdict(
        verdict=verdict,
        reviewer_name=reviewer_name,
        mention=mention,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
        comment=_md_to_mrkdwn(comment) if comment else None,
    )
    if slack_channel and slack_thread_ts:
        await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
    elif _channel():
        await _send_message(_channel(), text)


async def notify_answer_approved(
    question_title: str,
    answer_id: str,
    author_email: str | None,
    author_name: str,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify when an answer reaches approved status (review threshold met)."""
    if not _is_enabled():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = fmt_answer_approved(
        mention=mention,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
    )
    if slack_channel and slack_thread_ts:
        await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
    elif _channel():
        await _send_message(_channel(), text)


async def notify_revision_requested(
    question_title: str,
    answer_id: str,
    author_email: str | None,
    author_name: str,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify the answer author when changes are requested."""
    if not _is_enabled():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = fmt_revision_requested(
        mention=mention,
        question_title=question_title,
        answer_link=_answer_link(answer_id),
    )
    if slack_channel and slack_thread_ts:
        await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
    elif _channel():
        await _send_message(_channel(), text)


async def notify_question_closed(
    slack_channel: str,
    slack_thread_ts: str,
    question_title: str,
    question_id: str,
) -> None:
    """Post a closure message to a question's thread."""
    if not _is_enabled():
        return
    text = fmt_question_closed(
        question_title=question_title,
        question_link=_question_link(question_id),
    )
    await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
