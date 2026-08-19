"""
Lets the ngrok authtoken and static domain be set from inside a Telegram
chat instead of requiring a manual .env/config.yaml edit - useful since
the Mini App can't be used to configure itself before it's reachable in
the first place (chicken-and-egg: its own settings screen needs the
tunnel already running).

Security posture, since this is the one place a real secret gets typed
into the chat itself:
  - Reaching any of this at all already requires passing @restricted
    (chat_id + BOT_PASSWORD/unlocked, same as everything else) - this
    module adds NO new entry point beyond what the rest of the bot
    already gates identically.
  - The pasted token is captured, then the bot attempts to DELETE that
    message immediately - best-effort (Telegram allows a bot to delete
    incoming messages in a private chat), reported honestly either way,
    never assumed to have worked.
  - Never echoed back in full - only a masked form (first/last 4 chars)
    appears in any confirmation message.
  - Never logged - nothing here calls log.info/warning with the raw
    value; the one warning that can fire is about the DELETE call
    failing, which never includes the token itself.
  - Requires an explicit Save/Cancel confirmation before anything is
    written to disk - a captured value sits in memory only
    (state.staged_ngrok_token) until confirmed.
  - The capture window times out (PENDING_INPUT_TIMEOUT_SEC) so a stray
    later message can't accidentally be swallowed as "the token" if the
    flow gets abandoned mid-way.
  - Written to .env via config.set_env_var's atomic temp-file-then-rename,
    and the write is verified by reading the file back before reporting
    success - never just assumed.
"""
from __future__ import annotations

import logging
import re
import time

from tether.transport import menus

log = logging.getLogger(__name__)

PENDING_INPUT_TIMEOUT_SEC = 120
MAX_TOKEN_LENGTH = 200
_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _normalize_domain(raw: str) -> str:
    value = raw.strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    return value.rstrip("/")


async def start_token_capture(bot, chat_id: int, state, _t) -> None:
    state.pending_ngrok_domain_since = None  # only one capture active at a time
    state.pending_ngrok_token_since = time.monotonic()
    await bot.send_message(chat_id, _t("ngrok_token_prompt", seconds=PENDING_INPUT_TIMEOUT_SEC))


async def start_domain_capture(bot, chat_id: int, state, _t) -> None:
    state.pending_ngrok_token_since = None
    state.pending_ngrok_domain_since = time.monotonic()
    await bot.send_message(chat_id, _t("ngrok_domain_prompt", seconds=PENDING_INPUT_TIMEOUT_SEC))


async def _maybe_capture(update, context, state, _t) -> bool:
    """Returns True if this message was consumed as pending ngrok setup
    input (token or domain) - callers must stop processing it as
    anything else (a plain chat message, a keypad shortcut, text for the
    target app) the moment this returns True, whether or not the value
    turned out to be valid."""
    now = time.monotonic()
    chat_id = update.effective_chat.id
    raw_text = update.message.text or ""

    # getattr, not direct access: plenty of test doubles for `state`
    # predate these fields (see handlers.py::restricted for the same
    # pattern) - "not present" and "not currently waiting" mean the same
    # thing here.
    token_since = getattr(state, "pending_ngrok_token_since", None)
    if token_since is not None:
        state.pending_ngrok_token_since = None
        if now - token_since > PENDING_INPUT_TIMEOUT_SEC:
            await context.bot.send_message(chat_id, _t("ngrok_input_timed_out"))
            return True
        await _capture_token(update, context, state, _t, raw_text)
        return True

    domain_since = getattr(state, "pending_ngrok_domain_since", None)
    if domain_since is not None:
        state.pending_ngrok_domain_since = None
        if now - domain_since > PENDING_INPUT_TIMEOUT_SEC:
            await context.bot.send_message(chat_id, _t("ngrok_input_timed_out"))
            return True
        await _capture_domain(update, context, state, _t, raw_text)
        return True

    return False


async def _delete_best_effort(update, context) -> bool:
    try:
        await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
        return True
    except Exception:
        log.warning("mini app setup: could not delete a message from the chat", exc_info=True)
        return False


async def _capture_token(update, context, state, _t, raw_text: str) -> None:
    chat_id = update.effective_chat.id
    value = raw_text.strip()
    deleted = await _delete_best_effort(update, context)

    if not value or " " in value or "\n" in value or "\t" in value or len(value) > MAX_TOKEN_LENGTH:
        await context.bot.send_message(chat_id, _t("ngrok_token_invalid"))
        return

    state.staged_ngrok_token = value
    text = _t("ngrok_token_captured", masked=_mask(value))
    if not deleted:
        text += "\n\n" + _t("ngrok_delete_failed")
    await context.bot.send_message(chat_id, text, reply_markup=menus.ngrok_confirm_menu(_t, "token"))


async def _capture_domain(update, context, state, _t, raw_text: str) -> None:
    chat_id = update.effective_chat.id
    value = _normalize_domain(raw_text)
    # Not a secret, but still deleted for a tidy chat and consistent
    # behavior with the token flow - failing to delete it is not the
    # security-relevant case, so no special note if it doesn't work.
    await _delete_best_effort(update, context)

    if not value or not _DOMAIN_RE.match(value) or len(value) > 253:
        await context.bot.send_message(chat_id, _t("ngrok_domain_invalid"))
        return

    state.staged_ngrok_domain = value
    await context.bot.send_message(
        chat_id, _t("ngrok_domain_captured", domain=value), reply_markup=menus.ngrok_confirm_menu(_t, "domain"),
    )
