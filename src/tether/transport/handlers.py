"""Command handlers. Every target call (window/OCR/UIA — all blocking) goes
through asyncio.to_thread so the event loop is never stalled."""
from __future__ import annotations

import asyncio
import functools
import io

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from tether.i18n import make_translator
from tether.monitors.temps import get_cpu_temp, get_gpu_temp
from tether.transport import menus


def restricted(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.bot_data["state"]
        if update.effective_chat.id != state.config.secrets.chat_id:
            _t = make_translator(state.config.settings.language)
            if update.message:
                await update.message.reply_text(_t("unauthenticated_reply"))
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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logging.getLogger(__name__).error("Unhandled exception", exc_info=context.error)
    try:
        state = context.bot_data.get("state")
        if state:
            _t = make_translator(state.config.settings.language)
            await context.bot.send_message(state.config.secrets.chat_id, _t("error_generic", error=str(context.error)))
    except Exception:
        pass
