"""Command handlers. Every target call (window/OCR/UIA — all blocking) goes
through asyncio.to_thread so the event loop is never stalled."""
from __future__ import annotations

import asyncio
import functools
import html
import io
import logging
import time

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from tether.i18n import make_translator
from tether.monitors.temps import get_cpu_temp, get_gpu_temp
from tether.transport import menus


def restricted(handler):
    """Drops anything not from the configured chat id.

    Deliberately silent: replying would confirm to a stranger that the bot
    is live and configured, and would let anyone trigger unlimited outbound
    messages by spamming it (burning the account's rate limit, or worse).
    Unauthorized attempts are logged locally instead."""
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.bot_data["state"]
        chat = update.effective_chat
        if chat is None or chat.id != state.config.secrets.chat_id:
            logging.getLogger(__name__).warning(
                "ignored update from unauthorized chat id %s",
                chat.id if chat else "unknown",
            )
            return
        return await handler(update, context)
    return wrapper


def _ctx(context) -> tuple:
    state = context.bot_data["state"]
    return state, make_translator(state.config.settings.language)


@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    await update.message.reply_text(_t("start_welcome"), reply_markup=menus.main_reply_keyboard(_t))


@restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("help_text"))


@restricted
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("menu_title"), reply_markup=menus.main_menu(_t))


@restricted
async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    sessions = await asyncio.to_thread(state.target.list_sessions)
    if not sessions:
        await update.message.reply_text(_t("sessions_none"))
        return
    await update.message.reply_text(_t("sessions_title"), reply_markup=menus.session_menu(_t, sessions))


async def _send_screenshot(update_or_query, context: ContextTypes.DEFAULT_TYPE, window_keyword: str, label: str, send):
    state, _t = _ctx(context)
    from tether.platform.window import find_window_by_keyword, capture_window
    hwnd = await asyncio.to_thread(find_window_by_keyword, window_keyword)
    if not hwnd:
        await send(_t("window_not_found", window=window_keyword))
        return
    img = await asyncio.to_thread(capture_window, hwnd)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await context.bot.send_photo(state.config.secrets.chat_id, InputFile(buf, filename=f"{label}.png"), caption=_t("screenshot_caption", window=window_keyword))


@restricted
async def cmd_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    keyword = " ".join(context.args) or state.config.settings.claude_window_keyword
    await _send_screenshot(update, context, keyword, "custom", update.message.reply_text)


@restricted
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    status = await asyncio.to_thread(state.target.read_status)
    cpu = get_cpu_temp()
    gpu, fan = get_gpu_temp()
    cpu_str = f"{cpu}°C" if cpu is not None else _t("temp_unavailable")
    gpu_str = f"{gpu}°C" if gpu is not None else _t("temp_unavailable")
    fan_str = fan or _t("temp_unavailable")
    temp_report = _t("temp_report", cpu=cpu_str, gpu=gpu_str, fan=fan_str)
    await update.message.reply_text(
        _t("model_status", model=status.model or "?", effort=status.effort or "?", usage=temp_report)
    )


@restricted
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    from tether.targets.claude_desktop import MODEL_NAMES
    target_name = " ".join(context.args).strip()
    if not target_name:
        status = await asyncio.to_thread(state.target.read_status)
        await update.message.reply_text(
            _t("model_status", model=status.model or "?", effort=status.effort or "?",
               usage=_t("model_usage", options="|".join(MODEL_NAMES).lower()))
        )
        return
    result = await asyncio.to_thread(state.target.set_model, target_name)
    if result:
        await update.message.reply_text(_t("model_set", model=result))
    else:
        await update.message.reply_text(_t("model_unknown", target=target_name, options=", ".join(MODEL_NAMES)))


@restricted
async def cmd_effort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    from tether.targets.claude_desktop import EFFORT_LEVELS
    target_level = " ".join(context.args).strip()
    if not target_level:
        await update.message.reply_text(_t("effort_usage", options="|".join(EFFORT_LEVELS).lower()))
        return
    result = await asyncio.to_thread(state.target.set_effort, target_level)
    if result:
        await update.message.reply_text(_t("effort_set", level=result))
    else:
        await update.message.reply_text(_t("effort_unknown", target=target_level, options=", ".join(EFFORT_LEVELS)))


@restricted
async def cmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    from tether.platform.shell import run_cmd
    command = " ".join(context.args)
    if not command:
        await update.message.reply_text(_t("cmd_usage"))
        return
    try:
        output = await run_cmd(command)
        if len(output) > 4000:
            output = output[:4000] + "\n...(truncated)"
        await update.message.reply_text(_t("cmd_output", output=output), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(_t("cmd_error", error=str(e)))


@restricted
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    ok = await asyncio.to_thread(state.target.clear_input)
    await update.message.reply_text(_t("clear_done") if ok else _t("focus_failed"))


@restricted
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    await asyncio.to_thread(state.target.click_stop_button)
    await update.message.reply_text(_t("stop_sent"))


@restricted
async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("kill_menu_title"), reply_markup=menus.kill_menu(_t))


@restricted
async def cmd_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("keypad_title"), reply_markup=menus.keypad_menu(_t))


@restricted
async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("language_prompt"), reply_markup=menus.language_menu(_t))


@restricted
async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, _t = _ctx(context)
    await update.message.reply_text(_t("mode_prompt"), reply_markup=menus.mode_menu(_t))


@restricted
async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "off"):
        state.config.settings.confirm_before_send = (arg == "on")
        state.config.settings.save()
        await update.message.reply_text(_t("confirm_set", state=_t("confirm_" + arg)))
        return
    current = "on" if state.config.settings.confirm_before_send else "off"
    await update.message.reply_text(_t("confirm_prompt", state=_t("confirm_" + current)), reply_markup=menus.confirm_menu(_t))


@restricted
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    from dataclasses import asdict
    lines = "\n".join(f"{k}: {v}" for k, v in asdict(state.config.settings).items())
    await update.message.reply_text(_t("settings_title", settings=lines), reply_markup=menus.settings_menu(_t))


ERROR_NOTIFY_COOLDOWN_SEC = 60


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logs everything, but notifies Telegram at most once per minute per
    distinct error.

    A repeating fault can fire many times a second (a COM initialization bug
    during development produced roughly 30 a minute). Forwarding each one
    would flood the chat and risk the bot being rate limited by Telegram,
    which would take out the notifications that actually matter."""
    log = logging.getLogger(__name__)
    log.error("Unhandled exception", exc_info=context.error)

    state = context.bot_data.get("state")
    if not state:
        return

    signature = f"{type(context.error).__name__}: {context.error}"
    now = time.monotonic()
    last_sent = state.error_notify_times.get(signature, 0.0)
    if now - last_sent < ERROR_NOTIFY_COOLDOWN_SEC:
        return
    state.error_notify_times[signature] = now

    # Keep the dict from growing without bound on a long-running process.
    if len(state.error_notify_times) > 50:
        cutoff = now - ERROR_NOTIFY_COOLDOWN_SEC
        state.error_notify_times = {
            k: v for k, v in state.error_notify_times.items() if v > cutoff
        }

    try:
        _t = make_translator(state.config.settings.language)
        await context.bot.send_message(
            state.config.secrets.chat_id,
            _t("error_generic", error=str(context.error)[:300]),
        )
    except Exception:
        log.exception("could not deliver error notification")
