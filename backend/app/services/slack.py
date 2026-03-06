"""Slack notification service — fire-and-forget, never blocks the main API.

All public functions catch exceptions internally so Slack outages or
misconfiguration never affect platform operations.
"""
import asyncio
import logging
from functools import lru_cache

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


async def _send_message(channel: str, text: str) -> None:
    """Post a message to a Slack channel. Fire-and-forget."""
    try:
        client = _get_client()
        await client.chat_postMessage(channel=channel, text=text)
    except Exception:
        logger.exception("Failed to send Slack message to %s", channel)


def _channel() -> str:
    return settings.SLACK_DEFAULT_CHANNEL


# --- Public notification functions ---
# Each runs in a fire-and-forget task so the caller never waits.


async def notify_question_published(
    question_title: str,
    question_id: str,
    publisher_name: str,
) -> None:
    """Notify channel when a question is published and open for answers."""
    if not _is_enabled() or not _channel():
        return
    text = (
        f":clipboard: *New question published* by {publisher_name}\n"
        f"*{question_title}*\n"
        f"Question ID: `{question_id}`"
    )
    await _send_message(_channel(), text)


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
    text = (
        f":x: *Question rejected* — {mention}\n"
        f"*{question_title}*\n"
        f"Question ID: `{question_id}`"
    )
    if comment:
        text += f"\nReason: {comment}"
    await _send_message(_channel(), text)


async def notify_answer_submitted(
    question_title: str,
    answer_id: str,
    author_name: str,
) -> None:
    """Notify channel when an answer is submitted for review."""
    if not _is_enabled() or not _channel():
        return
    text = (
        f":pencil: *Answer submitted* by {author_name}\n"
        f"For question: *{question_title}*\n"
        f"Answer ID: `{answer_id}`"
    )
    await _send_message(_channel(), text)


async def notify_review_verdict(
    question_title: str,
    answer_id: str,
    verdict: str,
    reviewer_name: str,
    author_email: str | None,
    author_name: str,
    comment: str | None = None,
) -> None:
    """Notify when a review verdict is submitted."""
    if not _is_enabled() or not _channel():
        return
    mention = await _mention_or_name(author_email, author_name)
    emoji_map = {
        "approved": ":white_check_mark:",
        "changes_requested": ":memo:",
        "rejected": ":no_entry:",
    }
    emoji = emoji_map.get(verdict, ":speech_balloon:")
    text = (
        f"{emoji} *Review: {verdict.replace('_', ' ')}* by {reviewer_name}\n"
        f"For answer `{answer_id}` on *{question_title}* — {mention}\n"
    )
    if comment:
        text += f"Comment: {comment}"
    await _send_message(_channel(), text)


async def notify_answer_approved(
    question_title: str,
    answer_id: str,
    author_email: str | None,
    author_name: str,
) -> None:
    """Notify when an answer reaches approved status (review threshold met)."""
    if not _is_enabled() or not _channel():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = (
        f":tada: *Answer approved!* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"Answer ID: `{answer_id}`"
    )
    await _send_message(_channel(), text)


async def notify_revision_requested(
    question_title: str,
    answer_id: str,
    author_email: str | None,
    author_name: str,
) -> None:
    """Notify the answer author when changes are requested."""
    if not _is_enabled() or not _channel():
        return
    mention = await _mention_or_name(author_email, author_name)
    text = (
        f":arrows_counterclockwise: *Revision requested* — {mention}\n"
        f"For question: *{question_title}*\n"
        f"Answer ID: `{answer_id}` — please revise and resubmit."
    )
    await _send_message(_channel(), text)
