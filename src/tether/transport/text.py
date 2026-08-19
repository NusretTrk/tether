"""
Plain-text message handler. Priority order per message:
  1. Is an MCP `ask()` call waiting for an answer? This message answers it.
  2. Does it match a persistent reply-keyboard button label? Route to that action.
  3. Otherwise: it's meant for the target app — stage it, then either hold
     for confirmation or send immediately per settings.confirm_before_send.
"""
from __future__ import annotations

import asyncio
import time

from telegram import Update
from telegram.ext import ContextTypes

from tether.i18n import make_translator
from tether.mcp import shared_state
from tether.platform.presence import idle_seconds, is_user_active
from tether.transport import menus
from tether.transport.handlers import (
    cmd_keys, cmd_menu, cmd_screen, cmd_sessions, cmd_status, cmd_stop, restricted, _send_screenshot,
)
from tether.transport.target_resolve import active_target

# The original bot treated a plain "1", "y", "Enter" etc typed as a message
# as a keypress shortcut, not literal chat text — sending "1" answered a
# numbered prompt instead of typing "1" into Claude. The rewrite dropped
# this (everything fell through to "type it into Claude"), which from the
# user's side looked exactly like "the keypad stopped working": typing a
# shortcut just put literal text in the chat instead of answering anything.
# Restored here, case-insensitive, matching the same allowlist /keys uses.
#
# Digits and a few English abbreviations always work regardless of language
# (nobody expects "1" or "tab" to be translated). Yes/No/Enter/Escape are
# localized on the physical keyboard though (key_yes is "j" in German, "s"
# in Spanish) — matching only the English literal would silently break the
# button in every language but English/Turkish, where they happen to
# coincide with "y"/"n". _localized_key_shortcuts() builds the real mapping
# per request from the active language's own catalogue.
TEXT_KEY_SHORTCUTS = {"1", "2", "3", "4", "5", "enter", "escape", "esc", "tab"}


def _localized_key_shortcuts(_t) -> dict[str, str]:
    """{localized button label, lowercased: actual key to send}, built from
    whatever language is active — so a German "j" or Spanish "s" button
    resolves to "y" the same way the English "y" button already does."""
    return {
        _t("key_yes").lower(): "y",
        _t("key_no").lower(): "n",
        _t("key_enter").lower(): "enter",
        _t("key_escape").lower(): "escape",
        _t("key_tab").lower(): "tab",
    }


@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.bot_data["state"]
    _t = make_translator(state.config.settings.language)
    text = update.message.text.strip()

    # 0. Pending ngrok token/domain capture? Checked before literally
    # anything else - a captured secret must never fall through to being
    # typed into the target app's composer or treated as a keypad
    # shortcut. See transport/ngrok_setup.py.
    from tether.transport import ngrok_setup
    if await ngrok_setup._maybe_capture(update, context, state, _t):
        return

    # 1. Pending agent question?
    pending = shared_state.read_pending()
    if pending is not None:
        shared_state.write_answer(pending["id"], text)
        shared_state.clear_pending(pending["id"])
        await update.message.reply_text(_t("staged_sent"))
        return

    # 2. Reply-keyboard buttons
    if text == _t("btn_status"):
        await cmd_status(update, context)
        return
    if text == _t("btn_screen"):
        await cmd_screen(update, context)
        return
    if text == _t("btn_screen_claude"):
        await _send_screenshot(update, context, state.config.settings.claude_window_keyword, "claude", update.message.reply_text)
        return
    if text == _t("btn_screen_avd"):
        await _send_screenshot(update, context, state.config.settings.avd_window_keyword, "avd", update.message.reply_text)
        return
    if text == _t("btn_stop"):
        await cmd_stop(update, context)
        return
    if text == _t("btn_sessions"):
        await cmd_sessions(update, context)
        return
    if text == _t("btn_keypad"):
        await cmd_keys(update, context)
        return
    if text == _t("btn_menu"):
        await cmd_menu(update, context)
        return

    # 2b. Bare keypress shortcuts ("1", "y", "Enter") — answer a prompt,
    # don't type the literal character into Claude's chat. Checks both the
    # language-agnostic set (digits, English abbreviations) and whatever
    # the current language's own Yes/No/Enter/Escape/Tab buttons say.
    low = text.lower().strip()
    localized = _localized_key_shortcuts(_t)
    key = None
    if low in TEXT_KEY_SHORTCUTS:
        key = "escape" if low == "esc" else low
    elif low in localized:
        key = localized[low]
    if key is not None:
        ok = await asyncio.to_thread(state.target.send_key, key)
        await update.message.reply_text(_t("key_sent", key_name=text) if ok else _t("key_failed"))
        return

    # 3. Message for the target app.
    async def notify(text, reply_markup=None):
        return await update.message.reply_text(text, reply_markup=reply_markup)

    await send_text_to_target(state, _t, text, notify)


async def send_text_to_target(state, _t, text: str, notify) -> str:
    """The actual "type this into the target app" flow: presence-deferral,
    staging, confirm_before_send, and ground-truth pending_send tracking.
    Factored out of handle_text so the Mini App's own /api/send endpoint
    (see miniapp/server.py) goes through the exact same behavior a real
    Telegram message would - not a second, easily-drifting copy of it.

    `notify(text, reply_markup=None) -> Awaitable[Message]` sends a new
    status message to the chat - handle_text binds it to
    update.message.reply_text, the Mini App binds it to
    context.bot.send_message(chat_id, ...), since there's no original
    message to reply to when the text came from the Mini App's own
    compose box.

    Returns a short status string: "deferred", "stage_failed", "staged",
    "focus_failed", "sent_pending_verification", or "sent_unverified" -
    used by the Mini App to react in its own UI without needing to also
    watch the Telegram chat.

    Presence is checked *before* staging, not after: staging focuses the
    window and types, so by the time it fails it has already interrupted
    whoever was at the keyboard.
    """
    threshold = state.config.settings.defer_when_user_active_sec
    if await asyncio.to_thread(is_user_active, threshold):
        idle = await asyncio.to_thread(idle_seconds)
        state.deferred_text = text
        state.deferred_photo_bytes = None
        state.deferred_caption = ""
        msg = await notify(
            _t("deferred_user_active", seconds=int(idle or 0)), menus.deferred_keyboard(_t),
        )
        state.deferred_message_id = msg.message_id
        return "deferred"

    target = active_target(state)
    result = await asyncio.to_thread(target.stage_text, text)
    if not result.ok:
        reason_key = {
            "window_not_found": "claude_not_found",
            "focus_failed": "focus_failed",
        }.get(result.reason, "staged_send_failed")
        await notify(_t(reason_key))
        return "stage_failed"

    if state.config.settings.confirm_before_send:
        state.staged_text = text
        await notify(_t("staged_message_prompt", text=text), menus.staged_message_keyboard(_t))
        return "staged"

    ok = await asyncio.to_thread(target.press_enter)
    if not ok:
        await notify(_t("focus_failed"))
        return "focus_failed"

    # Ground-truth confirmation (below) only works for Claude Desktop - it
    # watches the Claude transcript for a matching event, which a message
    # sent to a /target-selected app would never produce, so it would
    # falsely report "failed" after the 10s timeout for every other target.
    if target is state.target:
        sent_msg = await notify("…")
        state.pending_send_text = text
        state.pending_send_message_id = sent_msg.message_id
        state.pending_send_since = time.monotonic()
        return "sent_pending_verification"
    else:
        await notify(_t("staged_sent_unverified"))
        return "sent_unverified"


@restricted
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Photos sent from Telegram paste into Claude's input box the same way
    Ctrl+V pastes a screenshot — set the Windows clipboard to image data,
    click into the box, paste. Previously there was no handler at all for
    filters.PHOTO, so a sent photo was just silently dropped."""
    state = context.bot_data["state"]
    _t = make_translator(state.config.settings.language)

    photo = update.message.photo[-1]  # last = highest resolution
    caption = update.message.caption or ""
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())

    threshold = state.config.settings.defer_when_user_active_sec
    if await asyncio.to_thread(is_user_active, threshold):
        idle = await asyncio.to_thread(idle_seconds)
        state.deferred_text = None
        state.deferred_photo_bytes = image_bytes
        state.deferred_caption = caption
        msg = await update.message.reply_text(
            _t("deferred_user_active", seconds=int(idle or 0)),
            reply_markup=menus.deferred_keyboard(_t),
        )
        state.deferred_message_id = msg.message_id
        return

    target = active_target(state)
    result = await asyncio.to_thread(target.stage_photo, image_bytes, caption)
    if not result.ok:
        reason_key = {
            "window_not_found": "claude_not_found",
            "focus_failed": "focus_failed",
            "clipboard_failed": "photo_clipboard_failed",
        }.get(result.reason, "photo_paste_failed")
        await update.message.reply_text(_t(reason_key))
        return

    if state.config.settings.confirm_before_send:
        state.staged_text = None
        state.staged_photo = True
        prompt = _t("staged_photo_caption_prompt", text=caption) if caption else _t("staged_photo_prompt")
        await update.message.reply_text(prompt, reply_markup=menus.staged_message_keyboard(_t))
        return

    ok = await asyncio.to_thread(target.press_enter)
    if not ok:
        await update.message.reply_text(_t("focus_failed"))
        return

    if target is state.target:
        sent_msg = await update.message.reply_text("…")
        state.pending_send_text = None
        state.pending_send_kind = "image"
        state.pending_send_message_id = sent_msg.message_id
        state.pending_send_since = time.monotonic()
    else:
        await update.message.reply_text(_t("staged_sent_unverified"))


async def deliver_deferred(context, state, _t) -> tuple[bool, str]:
    """Sends whatever was held back. Shared by the Send-now button and the
    idle auto-send job so both behave identically. Returns (ok, reason)."""
    text = state.deferred_text
    photo = state.deferred_photo_bytes
    caption = state.deferred_caption

    if text is None and photo is None:
        return (False, "nothing_deferred")

    target = active_target(state)
    if photo is not None:
        result = await asyncio.to_thread(target.stage_photo, photo, caption)
    else:
        result = await asyncio.to_thread(target.stage_text, text)

    if not result.ok:
        return (False, result.reason)

    ok = await asyncio.to_thread(target.press_enter)
    if not ok:
        return (False, "focus_failed")

    # Same caveat as handle_text/handle_photo: ground-truth confirmation
    # only means anything for Claude Desktop, since it watches Claude's own
    # transcript for a matching event.
    if target is state.target:
        state.pending_send_text = None if photo is not None else text
        state.pending_send_kind = "image" if photo is not None else "text"
        state.pending_send_message_id = state.deferred_message_id
        state.pending_send_since = time.monotonic()

    state.deferred_text = None
    state.deferred_photo_bytes = None
    state.deferred_caption = ""
    state.deferred_message_id = None
    return (True, "ok")
