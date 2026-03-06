"""Slack notification service — fire-and-forget, never blocks the main API.

All public functions catch exceptions internally so Slack outages or
misconfiguration never affect platform operations.

Thread lifecycle: When a question is published, a Slack thread is created.
All subsequent events for that question post as replies in that thread.
"""
import logging

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache for email → Slack user ID lookups
_slack_user_cache: dict[str, str | None] = {}


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
    link = _question_link(question_id)
    text = (
        f":clipboard: *New question published* by {publisher_name}\n"
        f"*{question_title}*\n"
        f"{link}"
    )
    thread_ts = await _post_message(channel, text)
    if not thread_ts:
        return (None, None)

    # Post the question body as the first reply in the thread
    body_preview = question_body[:2000] if len(question_body) > 2000 else question_body
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
) -> None:
    """Notify the question author when their question is rejected."""
    if not _is_enabled() or not _channel():
        return
    mention = await _mention_or_name(author_email, author_name)
    link = _question_link(question_id)
    text = (
        f":x: *Question rejected* — {mention}\n"
        f"*{question_title}*\n"
        f"{link}"
    )
    if comment:
        text += f"\nReason: {comment}"
    await _send_message(_channel(), text)


async def notify_answer_submitted(
    question_title: str,
    question_id: str,
    answer_id: str,
    author_name: str,
    slack_channel: str | None = None,
    slack_thread_ts: str | None = None,
) -> None:
    """Notify channel when an answer is submitted for review.

    If the question has a thread, posts as a reply. Otherwise posts to the default channel.
    """
    if not _is_enabled():
        return
    link = _answer_link(answer_id)
    text = (
        f":pencil: *Answer submitted* by {author_name}\n"
        f"For question: *{question_title}*\n"
        f"{link}"
    )
    if slack_channel and slack_thread_ts:
        await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
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
    emoji_map = {
        "approved": ":white_check_mark:",
        "changes_requested": ":memo:",
        "rejected": ":no_entry:",
    }
    emoji = emoji_map.get(verdict, ":speech_balloon:")
    link = _answer_link(answer_id)
    text = (
        f"{emoji} *Review: {verdict.replace('_', ' ')}* by {reviewer_name}\n"
        f"For {link} on *{question_title}* — {mention}\n"
    )
    if comment:
        text += f"Comment: {comment}"
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
    link = _answer_link(answer_id)
    text = (
        f":tada: *Answer approved!* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"{link}"
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
    link = _answer_link(answer_id)
    text = (
        f":arrows_counterclockwise: *Revision requested* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"{link} — please revise and resubmit."
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
    link = _question_link(question_id)
    text = (
        f":lock: *Question closed* — *{question_title}*\n"
        f"{link}\n"
        f"This question is no longer accepting new answers."
    )
    await _post_message(slack_channel, text, thread_ts=slack_thread_ts)
