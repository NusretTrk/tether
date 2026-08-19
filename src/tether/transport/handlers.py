"""Command handlers. Every target call (window/OCR/UIA — all blocking) goes
through asyncio.to_thread so the event loop is never stalled."""
from __future__ import annotations

import asyncio
import functools
import hmac
import html
import io
import logging
import time

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from tether.i18n import make_translator
from tether.monitors.temps import get_cpu_temp, get_gpu_temp
from tether.platform.capabilities import CAPABILITIES
from tether.transport import menus


def _fmt_minutes(minutes: float) -> str:
    return str(int(minutes)) if minutes == int(minutes) else f"{minutes:g}"


def _project_root(state):
    """Directory of whatever Claude Code session tether is currently
    tailing - read straight from the transcript's own `cwd` field rather
    than trying to reverse the lossy filename-mangled slug it's stored
    under. None if there's no active transcript yet, or it doesn't carry
    a cwd (very old/malformed file)."""
    from tether.sources.discovery import find_active_transcript
    from tether.sources.files import read_project_cwd
    transcript = find_active_transcript()
    if transcript is None:
        return None
    return read_project_cwd(transcript)


# Commands that must reach their handler even while locked - otherwise
# there's no way to unlock at all, and /start would look broken.
_UNLOCK_EXEMPT_PREFIXES = ("/start", "/unlock", "/help")


def _is_unlock_exempt(update: Update) -> bool:
    text = getattr(getattr(update, "message", None), "text", None) or ""
    return text.startswith(_UNLOCK_EXEMPT_PREFIXES)


async def _reply_locked(update: Update, _t) -> None:
    if getattr(update, "message", None) is not None:
        await update.message.reply_text(_t("bot_locked"))
    elif getattr(update, "callback_query", None) is not None:
        await update.callback_query.answer(_t("bot_locked"), show_alert=True)


def restricted(handler):
    """Drops anything not from the configured chat id.

    Deliberately silent: replying would confirm to a stranger that the bot
    is live and configured, and would let anyone trigger unlimited outbound
    messages by spamming it (burning the account's rate limit, or worse).
    Unauthorized attempts are logged locally instead.

    If BOT_PASSWORD is set, an already-authorized-but-locked chat is also
    stopped here (only after the chat-id check - only a verified chat
    should ever be told the bot exists at all). Locked replies openly
    rather than staying silent, since the sender is already the real
    owner as far as Telegram is concerned; the password is a second
    factor against their Telegram account itself being compromised, not
    a second layer of "hide that this bot exists"."""
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
        # getattr, not direct access: plenty of test doubles for `state`
        # predate this field and don't set it, and treating "not present"
        # the same as "not configured" is the correct behavior anyway.
        password = getattr(state.config.secrets, "bot_password", None)
        if password and not getattr(state, "unlocked", False) and not _is_unlock_exempt(update):
            _t = make_translator(state.config.settings.language)
            await _reply_locked(update, _t)
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
async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Second factor on top of the chat-id gate - see restricted()'s
    docstring for why chat-id alone isn't enough. Attempts are capped
    (monitors/lockout.py) so a compromised Telegram account can't just
    brute-force a weak password."""
    state, _t = _ctx(context)
    password = state.config.secrets.bot_password
    if not password:
        await update.message.reply_text(_t("unlock_not_needed"))
        return

    now = time.monotonic()
    if state.unlock_lockout.is_locked_out(now):
        await update.message.reply_text(_t("unlock_locked_out"))
        return

    given = " ".join(context.args)
    if not hmac.compare_digest(given, password):
        state.unlock_lockout.record_failure(now)
        await update.message.reply_text(_t("unlock_wrong_password"))
        return

    state.unlock_lockout.reset()
    state.unlocked = True
    await update.message.reply_text(_t("unlock_success"))


@restricted
async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    if not state.config.secrets.bot_password:
        await update.message.reply_text(_t("unlock_not_needed"))
        return
    state.unlocked = False
    await update.message.reply_text(_t("locked_now"))


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
async def cmd_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists recently-modified files (default: .md) in the active project,
    as tap-to-fetch buttons - for grabbing something the agent just wrote
    without needing to know its exact path."""
    from tether.sources.files import list_recent_files

    state, _t = _ctx(context)
    root = _project_root(state)
    if root is None:
        await update.message.reply_text(_t("files_no_project"))
        return

    settings = state.config.settings
    files = await asyncio.to_thread(
        list_recent_files, root, tuple(settings.remote_file_extensions), settings.remote_file_list_limit,
    )
    if not files:
        await update.message.reply_text(_t("files_none_found"))
        return

    state.recent_files = files
    await update.message.reply_text(_t("files_title"), reply_markup=menus.recent_files_menu(root, files))


@restricted
async def cmd_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/file <path> - fetches one specific file by path, relative to the
    active project's directory (or absolute, as long as it still resolves
    inside it). See sources/files.py::resolve_safe_path for the actual
    security boundary this relies on."""
    from tether.sources.files import resolve_safe_path

    state, _t = _ctx(context)
    if not context.args:
        await update.message.reply_text(_t("file_usage"))
        return

    root = _project_root(state)
    if root is None:
        await update.message.reply_text(_t("files_no_project"))
        return

    requested = " ".join(context.args)
    resolved = await asyncio.to_thread(resolve_safe_path, root, requested)
    if resolved is None:
        await update.message.reply_text(_t("file_not_found"))
        return

    max_bytes = state.config.settings.remote_file_max_bytes
    if resolved.stat().st_size > max_bytes:
        await update.message.reply_text(_t("file_too_large", max_mb=max_bytes // 1_000_000))
        return

    await context.bot.send_document(
        state.config.secrets.chat_id, InputFile(resolved.open("rb"), filename=resolved.name),
    )


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
    state, _t = _ctx(context)
    profiles = state.config.settings.keypad_profiles
    arg = context.args[0] if context.args else None

    if arg is None:
        if profiles:
            await update.message.reply_text(
                _t("keypad_profile_pick"), reply_markup=menus.profile_list_menu(_t, list(profiles.keys()))
            )
        else:
            await update.message.reply_text(
                _t("keypad_title"), reply_markup=menus.keypad_menu(_t, state.config.settings.custom_keys)
            )
        return

    profile = profiles.get(arg)
    if not profile:
        await update.message.reply_text(_t("keypad_profile_unknown", name=arg, options=", ".join(profiles) or "-"))
        return
    await update.message.reply_text(
        _t("keypad_profile_title", name=arg), reply_markup=menus.profile_keypad_menu(_t, arg, profile.get("keys", {}))
    )


@restricted
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart Claude Desktop. Confirmed rather than immediate: it ends any
    live session, which includes the agent issuing the command if one is
    driving the bot."""
    state, _t = _ctx(context)
    running = await asyncio.to_thread(state.target.is_app_running)
    count = len(await asyncio.to_thread(state.target.list_app_processes))
    await update.message.reply_text(
        _t("app_restart_prompt", count=count) if running else _t("app_restart_prompt_stopped"),
        reply_markup=menus.restart_confirm_keyboard(_t),
    )


@restricted
async def cmd_shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shutdown <minutes> or /shutdown cancel. Always confirmed before
    actually scheduling - unlike a restart this ends the whole machine, not
    just Claude's session."""
    state, _t = _ctx(context)
    if not CAPABILITIES.power_control:
        await update.message.reply_text(_t("shutdown_unsupported"))
        return
    if not context.args:
        await update.message.reply_text(_t("shutdown_usage"))
        return

    arg = context.args[0].lower()
    if arg == "cancel":
        from tether.platform.power import cancel_shutdown
        from tether.transport.jobs import SHUTDOWN_WARNING_JOB_NAME
        ok = await asyncio.to_thread(cancel_shutdown)
        for job in context.job_queue.get_jobs_by_name(SHUTDOWN_WARNING_JOB_NAME):
            job.schedule_removal()
        await update.message.reply_text(_t("shutdown_cancelled") if ok else _t("shutdown_cancel_failed"))
        return

    try:
        minutes = float(arg)
    except ValueError:
        await update.message.reply_text(_t("shutdown_usage"))
        return
    if minutes <= 0:
        await update.message.reply_text(_t("shutdown_usage"))
        return

    state.pending_shutdown_minutes = minutes
    await update.message.reply_text(
        _t("shutdown_confirm_prompt", minutes=_fmt_minutes(minutes)),
        reply_markup=menus.shutdown_confirm_keyboard(_t),
    )


@restricted
async def cmd_launch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state, _t = _ctx(context)
    if await asyncio.to_thread(state.target.is_app_running):
        await update.message.reply_text(_t("app_already_running"))
        return
    ok = await asyncio.to_thread(state.target.launch_app)
    if not ok:
        await update.message.reply_text(_t("app_launch_failed"))
        return
    appeared = await asyncio.to_thread(state.target.wait_for_window, 60.0)
    await update.message.reply_text(_t("app_started") if appeared else _t("app_started_no_window"))


@restricted
async def cmd_window(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/window <claude|avd> <title keyword> - which window each target
    points at is a guess at a title substring; when it's wrong (a renamed
    emulator, a different app entirely) there was no way to fix it short of
    editing config.yaml by hand and restarting."""
    state, _t = _ctx(context)
    if len(context.args) < 2:
        await update.message.reply_text(_t("window_usage"))
        return
    which, keyword = context.args[0].lower(), " ".join(context.args[1:])
    if which not in ("claude", "avd"):
        await update.message.reply_text(_t("window_usage"))
        return
    if which == "claude":
        state.config.settings.claude_window_keyword = keyword
    else:
        state.config.settings.avd_window_keyword = keyword
    state.config.settings.save()
    await update.message.reply_text(_t("window_set", which=which, keyword=keyword))


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
