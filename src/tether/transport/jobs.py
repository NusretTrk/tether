"""
Background jobs run on the PTB JobQueue. UIA-backed watchers (activity,
dialogs) do blocking COM calls and are always dispatched via
asyncio.to_thread — never called directly on the event loop.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from telegram.ext import ContextTypes

from tether.events import EventType
from tether.i18n import make_translator
from tether.monitors.usage_limit import parse_reset_time
from tether.platform.capabilities import CAPABILITIES
from tether.sources.discovery import find_active_transcript
from tether.transport import menus
from tether.transport.formatting import normalize_for_comparison, truncate_with_notice
from tether.transport.streaming import make_streamer

log = logging.getLogger(__name__)

# Claude Desktop shipped its own "auto-continue after reset" checkbox on
# 2026-08-14 (in-app setting, resumes the session locally once the window
# resets). This doesn't make the code below redundant so much as narrower
# in scope: the native checkbox resumes the session but never tells you it
# did, and only exists for Desktop's own chat UI, not any other target this
# might drive later. Kept as-is - if the native feature (or the user, or
# anything else) resumes the session first, usage_limit_job already
# cancels this on its own the moment new real activity shows up (see the
# "resumed_on_own" branch below), so the two don't fight each other.
USAGE_LIMIT_CONTINUE_JOB_NAME = "usage_limit_continue"
USAGE_LIMIT_CONTINUE_TEXT = "Continue, you were interrupted by usage limit."

SHUTDOWN_WARNING_JOB_NAME = "shutdown_warning"

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
            and normalize_for_comparison(event.text) == normalize_for_comparison(state.pending_send_text)
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


def _cancel_scheduled_continue(context: ContextTypes.DEFAULT_TYPE, state) -> None:
    for job in context.job_queue.get_jobs_by_name(USAGE_LIMIT_CONTINUE_JOB_NAME):
        job.schedule_removal()
    state.usage_limit_continue_scheduled = False
    state.usage_limit_reset_at = None


async def usage_limit_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scans recent transcript text for usage-limit phrasing — reading from
    the transcript instead of screen OCR means this works regardless of
    scroll position or which panel is focused."""
    state = context.bot_data["state"]
    settings = state.config.settings
    _t = make_translator(settings.language)
    chat_id = state.config.secrets.chat_id

    events, state.usage_limit_buffer = state.usage_limit_buffer, []

    matching = [e for e in events if any(k in e.text.lower() for k in USAGE_LIMIT_KEYWORDS)]
    hit = bool(matching)

    if hit:
        state.usage_limit_streak += 1
        # Take the freshest parseable reading seen so far this streak —
        # Claude's message may only fully render across a couple of polls.
        for event in matching:
            parsed = parse_reset_time(event.text, datetime.now())
            if parsed is not None:
                state.usage_limit_reset_at = parsed
    else:
        if state.usage_limit_continue_scheduled:
            # New real activity before the scheduled continue fired — the
            # session resumed on its own (limit lifted early, or the user
            # continued it themselves). The scheduled message would now be
            # redundant at best, confusing at worst, so drop it.
            _cancel_scheduled_continue(context, state)
            await context.bot.send_message(chat_id, _t("usage_limit_resumed_on_own"))
        state.usage_limit_streak = 0
        state.usage_limit_alerted = False
        state.usage_limit_reset_at = None

    if state.usage_limit_streak >= settings.usage_limit_confirm_streak and not state.usage_limit_alerted:
        state.usage_limit_alerted = True
        reset_at = state.usage_limit_reset_at

        can_schedule = (
            settings.usage_limit_continue_enabled
            and reset_at is not None
            and CAPABILITIES.window_control
            and state.usage_limit_continue.can_schedule(time.monotonic())
        )
        if can_schedule:
            delay = (reset_at - datetime.now()).total_seconds() + settings.usage_limit_continue_delay_sec
            context.job_queue.run_once(usage_limit_continue_job, when=max(delay, 1), name=USAGE_LIMIT_CONTINUE_JOB_NAME)
            state.usage_limit_continue_scheduled = True
            state.usage_limit_continue.record_attempt(time.monotonic())
            await context.bot.send_message(
                chat_id,
                _t("usage_limit_alert_continuing", reset_time=reset_at.strftime("%H:%M"),
                   delay=settings.usage_limit_continue_delay_sec),
            )
        elif settings.usage_limit_continue_enabled and reset_at is None:
            await context.bot.send_message(chat_id, _t("usage_limit_alert_no_reset_time"))
        else:
            await context.bot.send_message(
                chat_id, _t("usage_limit_alert", streak=state.usage_limit_streak),
            )


async def usage_limit_continue_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fires once, settings.usage_limit_continue_delay_sec after the parsed
    reset time. Reuses the same staged-send path every other outbound
    message goes through (including the presence check), so it never steals
    focus from someone who came back to the keyboard right at reset time —
    it defers exactly like a normal remote message would."""
    import asyncio

    from tether.platform.presence import is_user_active

    state = context.bot_data["state"]
    settings = state.config.settings
    _t = make_translator(settings.language)
    chat_id = state.config.secrets.chat_id

    state.usage_limit_continue_scheduled = False
    state.usage_limit_reset_at = None

    threshold = settings.defer_when_user_active_sec
    if await asyncio.to_thread(is_user_active, threshold):
        state.deferred_text = USAGE_LIMIT_CONTINUE_TEXT
        state.deferred_photo_bytes = None
        state.deferred_caption = ""
        await context.bot.send_message(chat_id, _t("usage_limit_continue_deferred"))
        return

    result = await asyncio.to_thread(state.target.stage_text, USAGE_LIMIT_CONTINUE_TEXT)
    if not result.ok:
        await context.bot.send_message(chat_id, _t("usage_limit_continue_failed", error=result.reason))
        return

    ok = await asyncio.to_thread(state.target.press_enter)
    if not ok:
        await context.bot.send_message(chat_id, _t("usage_limit_continue_failed", error="focus_failed"))
        return

    state.pending_send_text = USAGE_LIMIT_CONTINUE_TEXT
    state.pending_send_kind = "text"
    state.pending_send_since = time.monotonic()
    state.usage_limit_streak = 0
    state.usage_limit_alerted = False

    await context.bot.send_message(chat_id, _t("usage_limit_continuing"))


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
    # app_health_job already confirmed Claude Desktop isn't running - there
    # are no sessions to list, so this UIA poll would just be a wasted
    # round-trip every 3s. `is False` specifically (not falsy): None means
    # "not checked yet", which must NOT be treated as "confirmed down".
    if state.app_was_running is False:
        return
    _t = make_translator(settings.language)
    started, finished = await asyncio.to_thread(state.activity_watcher.poll)
    for name in started:
        await context.bot.send_message(state.config.secrets.chat_id, _t("activity_started", name=name))
    for name in finished:
        await context.bot.send_message(state.config.secrets.chat_id, _t("activity_done", name=name))


async def dialog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    state = context.bot_data["state"]
    settings = state.config.settings
    if not settings.dialog_watch_enabled:
        return
    # Same reasoning as activity_job - no window means no dialogs to find.
    if state.app_was_running is False:
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


async def shutdown_warning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-shot heads-up sent shortly before a /shutdown countdown actually
    fires, so it's never a surprise even if the confirming message got
    missed. Scheduled by the shutdown:confirm callback, cancelled by
    /shutdown cancel."""
    state = context.bot_data["state"]
    _t = make_translator(state.config.settings.language)
    await context.bot.send_message(state.config.secrets.chat_id, _t("shutdown_warning"))


async def miniapp_link_expire_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes the /miniapp link message a few minutes after it was sent -
    it contains a live bearer credential in plain text, no different from
    a password, so it shouldn't sit around in chat history indefinitely.
    Best-effort: if the user already deleted it themselves, or forwarded
    it and this copy is gone some other way, delete_message just raises
    and is swallowed - the credential's real revocation is
    state.web_token_hash, not this message's presence."""
    state = context.bot_data["state"]
    message_id = context.job.data
    try:
        await context.bot.delete_message(state.config.secrets.chat_id, message_id)
    except Exception:
        pass


TARGET_TRANSCRIPT_RECHECK_EVERY = 10  # re-run discovery every N polls, matching transcript_job


async def target_transcript_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tails whatever /target-selected app's own transcript, when the
    active profile has a known transcript_source configured - currently
    just "antigravity", which turned out to keep a local transcript.jsonl
    the same way Claude Code does (see sources/antigravity_events.py for
    where that was confirmed, not assumed). This is the actual mechanism
    behind "read {target}'s replies back": completely independent of
    transcript_job above, which always tails Claude's own transcript
    regardless of what /target currently points at - switching targets
    never affects the Claude relay, and this job is a no-op whenever no
    profile with a transcript_source is active.
    """
    state = context.bot_data["state"]
    settings = state.config.settings
    name = state.active_target_profile
    if not name:
        return
    profile = settings.keypad_profiles.get(name, {})
    source = profile.get("transcript_source")
    if source != "antigravity":
        return

    from tether.sources.antigravity_events import parse_antigravity_line
    from tether.sources.discovery import find_active_antigravity_transcript
    from tether.sources.transcript import TranscriptTailer

    state.target_transcript_poll_count += 1
    if state.target_tailer is None or state.target_transcript_poll_count % TARGET_TRANSCRIPT_RECHECK_EVERY == 0:
        active = find_active_antigravity_transcript()
        if active and active != state.target_tailer_path:
            log.info("switching tailed target transcript to %s", active)
            state.target_tailer = TranscriptTailer(active, from_start=False, parse_line=parse_antigravity_line)
            state.target_tailer_path = active

    if state.target_tailer is None:
        return

    events = state.target_tailer.poll()
    if not events:
        return

    mode = settings.output_mode
    if mode == "quiet":
        return

    chat_id = state.config.secrets.chat_id
    for event in events:
        if event.type == EventType.ASSISTANT_TEXT and event.text.strip():
            await context.bot.send_message(chat_id, f"[{name}] {truncate_with_notice(event.text, 4000, '…')}")
        elif mode in ("verbose", "live") and event.type == EventType.TOOL_RESULT:
            icon = "❌" if event.is_error else "→"
            summary = event.tool_name or "tool"
            await context.bot.send_message(
                chat_id, f"[{name}] {icon} {summary}: {truncate_with_notice(event.text, 1500, '…')}",
            )


async def state_snapshot_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodically dumps the in-flight state (deferred/staged/pending
    confirmations) to disk so a crash or watchdog restart doesn't silently
    drop it. See transport/persistence.py for what gets restored and why."""
    from tether.transport import persistence

    state = context.bot_data["state"]
    persistence.save(state)


async def mini_app_health_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Relaunches the ngrok tunnel if it died on its own since the last
    check - a no-op whenever the Mini App is off (state.ngrok_runner is
    None in that case). See miniapp/runner.py::ensure_running for the
    restart cap that keeps this from hammering ngrok's servers if the
    failure is persistent (bad auth, domain claimed elsewhere, offline)."""
    import asyncio

    state = context.bot_data["state"]
    if state.ngrok_runner is not None:
        await asyncio.to_thread(state.ngrok_runner.ensure_running)
