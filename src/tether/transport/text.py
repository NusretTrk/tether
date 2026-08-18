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
from tether.transport import menus
from tether.transport.handlers import (
    cmd_menu, cmd_screen, cmd_sessions, cmd_status, cmd_stop, restricted,
)


@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.bot_data["state"]
    _t = make_translator(state.config.settings.language)
    text = update.message.text.strip()

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
    if text == _t("btn_stop"):
        await cmd_stop(update, context)
        return
    if text == _t("btn_sessions"):
        await cmd_sessions(update, context)
        return
    if text == _t("btn_menu"):
        await cmd_menu(update, context)
        return

    # 3. Message for the target app
    result = await asyncio.to_thread(state.target.stage_text, text)
    if not result.ok:
        reason_key = {
            "window_not_found": "claude_not_found",
            "focus_failed": "focus_failed",
        }.get(result.reason, "staged_send_failed")
        await update.message.reply_text(_t(reason_key))
        return

    if state.config.settings.confirm_before_send:
        state.staged_text = text
        await update.message.reply_text(
            _t("staged_message_prompt", text=text), reply_markup=menus.staged_message_keyboard(_t)
        )
        return

    ok = await asyncio.to_thread(state.target.press_enter)
    if not ok:
        await update.message.reply_text(_t("focus_failed"))
        return

    sent_msg = await update.message.reply_text("…")
    state.pending_send_text = text
    state.pending_send_message_id = sent_msg.message_id
    state.pending_send_since = time.monotonic()
