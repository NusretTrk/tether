"""
Streams growing text to a single Telegram message via throttled edits.

Bot API 10.1 added sendRichMessageDraft specifically for streaming partial AI
replies, but python-telegram-bot 22.8 (latest as of writing) only supports
API 10.0 and doesn't expose it. This is the seam: RichDraftStreamer can be
added later and selected by has_rich_message_draft() with no other code
changes, once the library catches up.
"""
from __future__ import annotations

import logging
import time
from typing import Protocol

from telegram import Bot
from telegram.error import BadRequest

from tether.transport.formatting import TELEGRAM_MAX_LEN

log = logging.getLogger(__name__)


class Streamer(Protocol):
    async def start(self) -> None: ...
    async def push(self, full_text: str) -> None: ...
    async def finish(self, full_text: str | None = None) -> None: ...


class ThrottledEditStreamer:
    """Buffers text and edits one Telegram message no more often than
    `throttle_sec`. When the buffer outgrows one message, the current
    message is left as-is and a new one is started to continue in."""

    def __init__(self, bot: Bot, chat_id: int, throttle_sec: float = 2.5):
        self._bot = bot
        self._chat_id = chat_id
        self._throttle_sec = throttle_sec
        self._message = None
        self._last_edit = 0.0
        self._buffer = ""
        self._sent_len = 0  # length of buffer already committed to a previous message

    async def start(self) -> None:
        self._message = await self._bot.send_message(self._chat_id, "…")
        self._last_edit = time.monotonic()

    async def push(self, full_text: str) -> None:
        self._buffer = full_text
        now = time.monotonic()
        if now - self._last_edit >= self._throttle_sec:
            await self._flush()

    async def finish(self, full_text: str | None = None) -> None:
        if full_text is not None:
            self._buffer = full_text
        await self._flush(force=True)

    async def _flush(self, force: bool = False) -> None:
        if self._message is None:
            return
        visible = self._buffer[self._sent_len:]
        if not visible and not force:
            return

        if len(visible) > TELEGRAM_MAX_LEN - 32:
            # current message is full — leave it, roll over into a new one
            self._sent_len += len(visible)
            self._message = await self._bot.send_message(self._chat_id, "…")
            visible = ""

        text = visible or "…"
        try:
            await self._message.edit_text(text[:TELEGRAM_MAX_LEN])
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                log.warning("stream edit failed: %s", e)
        self._last_edit = time.monotonic()


def has_rich_message_draft(bot: Bot) -> bool:
    """Feature-detects sendRichMessageDraft support. Always False today —
    kept as the single switch point for when the library adds it."""
    return hasattr(bot, "send_rich_message_draft")


def make_streamer(bot: Bot, chat_id: int, throttle_sec: float = 2.5) -> Streamer:
    if has_rich_message_draft(bot):
        # Future: return RichDraftStreamer(bot, chat_id)
        pass
    return ThrottledEditStreamer(bot, chat_id, throttle_sec)
