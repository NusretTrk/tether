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

        if (
            event.type == EventType.USER_TEXT
            and state.pending_send_text is not None
            and event.text.strip() == state.pending_send_text.strip()
        ):
            if state.pending_send_message_id:
                try:
                    await context.bot.edit_message_text(
                        _t("staged_sent"), chat_id=chat_id, message_id=state.pending_send_message_id,
                    )
                except Exception:
                    pass
            state.pending_send_text = None
            state.pending_send_message_id = None

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
