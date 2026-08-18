"""
Background jobs run on the PTB JobQueue. UIA-backed watchers (activity,
dialogs) do blocking COM calls and are always dispatched via
asyncio.to_thread — never called directly on the event loop.
"""
from __future__ import annotations

import logging
import time

from telegram.ext import ContextTypes

from tether.events import EventType
from tether.i18n import make_translator
from tether.sources.discovery import find_active_transcript
from tether.transport import menus
from tether.transport.formatting import truncate_with_notice
from tether.transport.streaming import make_streamer

log = logging.getLogger(__name__)

USAGE_LIMIT_KEYWORDS = (
    "usage limit reached",
    "reached your usage limit",
    "after your limit resets",
    "usage limit", "limit reached", "reached your limit", "rate limit",
    "resets at", "upgrade to continue", "message limit", "hit your limit",
    "try again later", "kullanım limiti", "limit doldu",
)

LIVE_IDLE_FINALIZE_SEC = 15
TRANSCRIPT_RECHECK_EVERY = 10  # re-run discovery every N polls, not every poll


def _tool_summary(tool_name: str | None, tool_input: dict | None) -> str:
    if not tool_input:
        return tool_name or "tool"
    # short, single-line best-effort summary of the most relevant argument
    for key in ("command", "description", "path", "file_path", "pattern", "query"):
        if key in tool_input:
            val = str(tool_input[key])
            return f"{tool_name}({val[:80]})"
    return f"{tool_name}(...)"


async def transcript_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.bot_data["state"]
    settings = state.config.settings
    _t = make_translator(settings.language)

    state.transcript_poll_count += 1
    if state.tailer is None or state.transcript_poll_count % TRANSCRIPT_RECHECK_EVERY == 0:
        active = find_active_transcript()
        if active and active != state.tailer_path:
            from tether.sources.transcript import TranscriptTailer
            log.info("switching tailed transcript to %s", active)
            state.tailer = TranscriptTailer(active, from_start=False)
            state.tailer_path = active

    if state.tailer is None:
        return

    chat_id = state.config.secrets.chat_id

    # Ground-truth send confirmation: if a message was sent and hasn't been
    # confirmed within 10s, tell the user rather than staying silent — the
    # old bot's failure mode ("I texted this" with nothing actually landing)
    # is exactly what this replaces.
    if state.pending_send_text is not None and time.monotonic() - state.pending_send_since > 10:
        if state.pending_send_message_id:
            try:
                await context.bot.edit_message_text(
                    _t("staged_send_failed"), chat_id=chat_id, message_id=state.pending_send_message_id,
                )
            except Exception:
                pass
        state.pending_send_text = None
        state.pending_send_message_id = None
        state.pending_send_kind = "text"

    events = state.tailer.poll()
    if not events:
        if state.live_streamer is not None and time.monotonic() - state.last_event_time > LIVE_IDLE_FINALIZE_SEC:
            await state.live_streamer.finish()
            state.live_streamer = None
            state.live_buffer = ""
        return

    mode = settings.output_mode

    for event in events:
        state.last_event_time = time.monotonic()

        # Fed regardless of output_mode — usage_limit_job runs on its own,
        # slower cadence and drains this; poll() is a consuming read, so it
        # must only ever be called from this one job, never from two places.
        if event.type in (EventType.ASSISTANT_TEXT, EventType.SYSTEM):
            state.usage_limit_buffer.append(event)

        # Match tool calls to their results so a call that never comes back
        # can be spotted (agent blocked on a prompt, or a long-running job).
        if event.type == EventType.TOOL_CALL and event.tool_id:
            state.pending_tool_calls[event.tool_id] = (time.monotonic(), event.tool_name or "tool")
        elif event.type == EventType.TOOL_RESULT and event.tool_id:
            state.pending_tool_calls.pop(event.tool_id, None)
            state.stall_notified.discard(event.tool_id)

        text_confirmed = (
            event.type == EventType.USER_TEXT
            and state.pending_send_kind == "text"
            and state.pending_send_text is not None
            and event.text.strip() == state.pending_send_text.strip()
        )
        image_confirmed = (
            event.type == EventType.IMAGE
            and state.pending_send_kind == "image"
            and state.pending_send_message_id is not None
        )
        if text_confirmed or image_confirmed:
            if state.pending_send_message_id:
                try:
                    await context.bot.edit_message_text(
                        _t("staged_sent"), chat_id=chat_id, message_id=state.pending_send_message_id,
                    )
                except Exception:
                    pass
            state.pending_send_text = None
            state.pending_send_message_id = None
            state.pending_send_kind = "text"

        if mode == "quiet":
            continue

        if mode == "summary":
            if event.type == EventType.ASSISTANT_TEXT and event.text.strip():
                await context.bot.send_message(chat_id, event.text[:4000])
            continue

        if mode == "verbose":
            if event.type == EventType.THINKING and event.text.strip():
                await context.bot.send_message(chat_id, f"🤔 {truncate_with_notice(event.text, 1000, '…')}")
            elif event.type == EventType.TOOL_CALL:
                await context.bot.send_message(chat_id, f"🔧 {_tool_summary(event.tool_name, event.tool_input)}")
            elif event.type == EventType.TOOL_RESULT:
                icon = "❌" if event.is_error else "→"
                await context.bot.send_message(chat_id, f"{icon} {truncate_with_notice(event.text, 1500, '…')}")
            elif event.type == EventType.ASSISTANT_TEXT and event.text.strip():
                await context.bot.send_message(chat_id, event.text[:4000])
            continue

        # live: accumulate into one rolling edited message
        if mode == "live":
            line = None
            if event.type == EventType.THINKING and event.text.strip():
                line = f"🤔 {truncate_with_notice(event.text, 300, '…')}"
            elif event.type == EventType.TOOL_CALL:
                line = f"🔧 {_tool_summary(event.tool_name, event.tool_input)}"
            elif event.type == EventType.TOOL_RESULT:
                icon = "❌" if event.is_error else "→"
                line = f"{icon} {truncate_with_notice(event.text, 300, '…')}"
            elif event.type == EventType.ASSISTANT_TEXT and event.text.strip():
                line = event.text
            if line is None:
                continue

            if state.live_streamer is None:
                state.live_streamer = make_streamer(context.bot, chat_id, settings.stream_edit_throttle_sec)
                await state.live_streamer.start()
                state.live_buffer = ""
            state.live_buffer = (state.live_buffer + "\n\n" + line).strip()
            await state.live_streamer.push(state.live_buffer)


async def usage_limit_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scans recent transcript text for usage-limit phrasing — reading from
    the transcript instead of screen OCR means this works regardless of
    scroll position or which panel is focused."""
    state = context.bot_data["state"]
    settings = state.config.settings
    _t = make_translator(settings.language)

    events, state.usage_limit_buffer = state.usage_limit_buffer, []

    hit = any(any(k in e.text.lower() for k in USAGE_LIMIT_KEYWORDS) for e in events)

    if hit:
        state.usage_limit_streak += 1
    else:
        state.usage_limit_streak = 0
        state.usage_limit_alerted = False

    if state.usage_limit_streak >= settings.usage_limit_confirm_streak and not state.usage_limit_alerted:
        minutes = (settings.usage_limit_check_interval_sec * state.usage_limit_streak) // 60
        await context.bot.send_message(
            state.config.secrets.chat_id,
            _t("usage_limit_alert", minutes=minutes, streak=state.usage_limit_streak),
        )
        state.usage_limit_alerted = True


async def temp_monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from tether.monitors.temps import get_cpu_temp, get_gpu_temp

    state = context.bot_data["state"]
    settings = state.config.settings
    _t = make_translator(settings.language)
    chat_id = state.config.secrets.chat_id

    cpu = get_cpu_temp()
    gpu, fan = get_gpu_temp()
    cpu_str = f"{cpu}°C" if cpu is not None else _t("temp_unavailable")
    gpu_str = f"{gpu}°C" if gpu is not None else _t("temp_unavailable")
    fan_str = fan or _t("temp_unavailable")
    report = _t("temp_report", cpu=cpu_str, gpu=gpu_str, fan=fan_str)

    if (cpu is not None and cpu >= settings.temp_emergency_c) or (gpu is not None and gpu >= settings.temp_emergency_c):
        now = time.monotonic()
        if now - state.last_temp_alarm > 300:
            await context.bot.send_message(chat_id, _t("temp_emergency", threshold=settings.temp_emergency_c, report=report))
            state.last_temp_alarm = now

    state.temp_history.append(report)
    if len(state.temp_history) >= settings.temp_report_every_n_checks:
        await context.bot.send_message(chat_id, "\n\n".join(state.temp_history))
        state.temp_history.clear()


async def activity_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    state = context.bot_data["state"]
    settings = state.config.settings
    if not settings.activity_watch_enabled:
        return
    _t = make_translator(settings.language)
    finished = await asyncio.to_thread(state.activity_watcher.poll)
    for name in finished:
        await context.bot.send_message(state.config.secrets.chat_id, _t("activity_done", name=name))


async def dialog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    state = context.bot_data["state"]
    settings = state.config.settings
    if not settings.dialog_watch_enabled:
        return
    _t = make_translator(settings.language)
    dialogs = await asyncio.to_thread(state.dialog_watcher.poll)
    for d in dialogs:
        buttons = ", ".join(d.buttons) if d.buttons else "-"
        await context.bot.send_message(state.config.secrets.chat_id, _t("dialog_alert", name=d.name, buttons=buttons))


STALL_NOTIFY_AFTER_SEC = 90


async def stall_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Notifies when a tool call has been outstanding for a while.

    Agent tools that need permission block on an on-screen prompt, and
    nothing further is written to the transcript until it is answered. From
    the outside that is indistinguishable from a slow command, so this
    reports either case and attaches a keypad - the point is that you can
    actually respond instead of finding out hours later that it stalled.
    """
    state = context.bot_data["state"]
    settings = state.config.settings
    if not settings.stall_watch_enabled:
        return
    _t = make_translator(settings.language)
    now = time.monotonic()

    for tool_id, (seen_at, tool_name) in list(state.pending_tool_calls.items()):
        if tool_id in state.stall_notified:
            continue
        waited = now - seen_at
        if waited < STALL_NOTIFY_AFTER_SEC:
            continue
        state.stall_notified.add(tool_id)
        await context.bot.send_message(
            state.config.secrets.chat_id,
            _t("prompt_detected", text=f"{tool_name} - no result after {int(waited)}s"),
            reply_markup=menus.prompt_reply_keyboard(_t),
        )


async def app_health_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reports when Claude Desktop stops running, and optionally brings it
    back on its own.

    Auto-recovery is deliberately narrow. It only fires when the machine
    was idle through the whole detection window - a user who quit the app
    themselves is sitting right there and should not have it reappear - and
    it is capped so an app that crashes during startup cannot be restarted
    in a loop. Every decision, including the decision not to act, is
    reported. See monitors/recovery.py.
    """
    import asyncio
    import time as _time

    from tether.platform.presence import idle_seconds

    state = context.bot_data["state"]
    settings = state.config.settings
    if not settings.app_health_watch_enabled:
        return
    _t = make_translator(settings.language)
    chat_id = state.config.secrets.chat_id

    running = await asyncio.to_thread(state.target.is_app_running)

    # First run only establishes a baseline; nothing has "changed" yet.
    if state.app_was_running is None:
        state.app_was_running = running
        return

    if running and not state.app_was_running:
        state.app_down_notified = False
        state.recovery.reset()  # it came back; don't hold past failures against it
        await context.bot.send_message(chat_id, _t("app_back_up"))
        state.app_was_running = running
        return

    if state.app_was_running and not running:
        idle = await asyncio.to_thread(idle_seconds)
        now = _time.monotonic()
        recover, reason = state.recovery.should_recover(
            app_running=running,
            was_running=state.app_was_running,
            idle_seconds=idle,
            now=now,
        )

        if recover:
            state.recovery.record_attempt(now)
            attempt = state.recovery.attempts_in_window(now)
            await context.bot.send_message(
                chat_id,
                _t("app_auto_recovering", attempt=attempt, limit=settings.auto_recover_max_attempts),
            )
            ok, fail_reason = await asyncio.to_thread(state.target.restart_app)
            if ok:
                state.app_was_running = True
                state.app_down_notified = False
                await context.bot.send_message(chat_id, _t("app_auto_recovered"))
                return
            await context.bot.send_message(
                chat_id, _t("app_auto_recover_failed", reason=fail_reason)
            )
            state.app_down_notified = True
        elif not state.app_down_notified:
            state.app_down_notified = True
            # Say *why* it wasn't auto-restarted, so silence is never
            # ambiguous - "user_active" and "attempt_limit_reached" mean
            # very different things to whoever is reading the alert.
            note = _t(f"recover_skip_{reason}") if reason in (
                "user_active", "attempt_limit_reached", "cooling_down",
                "presence_unknown", "disabled",
            ) else ""
            message = _t("app_down")
            if note:
                message = message + "\n\n" + note
            await context.bot.send_message(
                chat_id,
                message,
                reply_markup=menus.app_down_keyboard(_t),
            )

    state.app_was_running = running


async def deferred_send_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a held message once the machine has actually gone idle.

    Without this, deferring would just mean "your message never arrives
    unless you notice the button" - the point is that walking away from the
    keyboard is enough for it to go through on its own.
    """
    import asyncio

    from tether.platform.presence import idle_seconds
    from tether.transport.text import deliver_deferred

    state = context.bot_data["state"]
    settings = state.config.settings

    if state.deferred_text is None and state.deferred_photo_bytes is None:
        return
    if settings.auto_send_after_idle_sec <= 0:
        return  # hold indefinitely; only the button sends

    idle = await asyncio.to_thread(idle_seconds)
    if idle is None or idle < settings.auto_send_after_idle_sec:
        return

    _t = make_translator(settings.language)
    ok, reason = await deliver_deferred(context, state, _t)
    chat_id = state.config.secrets.chat_id
    if ok:
        await context.bot.send_message(chat_id, _t("deferred_auto_sent"))
    else:
        await context.bot.send_message(chat_id, _t("error_generic", error=reason))
