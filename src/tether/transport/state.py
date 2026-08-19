"""Shared mutable state for the running bot, stored at bot_data["state"]."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tether.config import Config
from tether.events import Event
from tether.monitors.activity import ActivityWatcher
from tether.monitors.dialogs import DialogWatcher
from tether.monitors.lockout import LockoutDecider, LockoutPolicy
from tether.monitors.recovery import RecoveryDecider, RecoveryPolicy
from tether.monitors.usage_limit import ContinueDecider, ContinuePolicy
from tether.sources.transcript import TranscriptTailer
from tether.targets.claude_desktop import ClaudeDesktopTarget


@dataclass
class AppState:
    config: Config
    target: ClaudeDesktopTarget
    activity_watcher: ActivityWatcher
    dialog_watcher: DialogWatcher
    recovery: RecoveryDecider

    tailer: TranscriptTailer | None = None
    tailer_path: Path | None = None
    transcript_poll_count: int = 0
    last_event_time: float = field(default_factory=time.monotonic)

    live_streamer: object | None = None
    live_buffer: str = ""

    usage_limit_buffer: list[Event] = field(default_factory=list)
    usage_limit_streak: int = 0
    usage_limit_alerted: bool = False
    # Best reading of when the limit resets, from Claude's own message text.
    # Cleared once the scheduled continue fires or is cancelled.
    usage_limit_reset_at: datetime | None = None
    usage_limit_continue_scheduled: bool = False
    usage_limit_continue: ContinueDecider = field(default_factory=lambda: ContinueDecider(ContinuePolicy()))

    # Awaiting confirmation from the /shutdown <minutes> inline keyboard.
    # None once confirmed/cancelled - the actual countdown after that point
    # is tracked by Windows itself (`shutdown /a` to cancel), not here.
    pending_shutdown_minutes: float | None = None

    # Last /files listing, indexed by the inline keyboard's callback_data
    # (a full path doesn't fit in Telegram's 64-byte callback_data limit).
    recent_files: list[Path] = field(default_factory=list)

    # Only meaningful when config.secrets.bot_password is set. Always False
    # on a fresh process start - a restart re-locks, same as any other auth
    # session expiring rather than persisting silently.
    unlocked: bool = False
    unlock_lockout: LockoutDecider = field(default_factory=lambda: LockoutDecider(LockoutPolicy()))

    # error signature -> monotonic time last forwarded to Telegram,
    # so a repeating fault doesn't flood the chat (see error_handler).
    error_notify_times: dict[str, float] = field(default_factory=dict)

    # tool_use id -> (monotonic time seen, tool name). A call still sitting
    # here after a while means the agent is either blocked on a permission
    # prompt or running something long; either way worth surfacing.
    pending_tool_calls: dict[str, tuple[float, str]] = field(default_factory=dict)
    stall_notified: set[str] = field(default_factory=set)

    # None until the first health check runs, so startup doesn't report
    # a transition that didn't happen.
    app_was_running: bool | None = None
    app_down_notified: bool = False

    temp_history: list[str] = field(default_factory=list)
    last_temp_alarm: float = 0.0

    # Held because the user was at the keyboard when it arrived. Nothing
    # has touched the window yet - deferral happens before any focus
    # steal, which is the entire point.
    deferred_text: str | None = None
    deferred_photo_bytes: bytes | None = None
    deferred_caption: str = ""
    deferred_message_id: int | None = None

    staged_text: str | None = None
    staged_photo: bool = False
    active_ask_id: str | None = None

    # Set right after pressing Enter; cleared by transcript_job once the
    # matching USER_TEXT event is actually observed in the transcript — the
    # ground-truth confirmation that replaces the old screenshot-compare
    # heuristic. See transport/jobs.py and transport/text.py.
    pending_send_text: str | None = None
    pending_send_kind: str = "text"  # "text" or "image" — which event type confirms delivery
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0

    @staticmethod
    def build(config: Config) -> "AppState":
        target = ClaudeDesktopTarget(
            config.settings.claude_window_keyword,
            config.settings.claude_app_path_filter,
            config.settings.claude_launch_command,
            config.settings.preserve_user_clipboard,
        )
        return AppState(
            config=config,
            target=target,
            activity_watcher=ActivityWatcher(target, config.settings.activity_ignore_substrings),
            dialog_watcher=DialogWatcher(target),
            recovery=RecoveryDecider(RecoveryPolicy(
                enabled=config.settings.auto_recover_enabled,
                max_attempts=config.settings.auto_recover_max_attempts,
                attempt_window_sec=config.settings.auto_recover_attempt_window_sec,
                cooldown_sec=config.settings.auto_recover_cooldown_sec,
                require_idle_sec=config.settings.auto_recover_require_idle_sec,
            )),
            usage_limit_continue=ContinueDecider(ContinuePolicy(
                enabled=config.settings.usage_limit_continue_enabled,
                post_reset_delay_sec=config.settings.usage_limit_continue_delay_sec,
                max_attempts=config.settings.usage_limit_continue_max_attempts,
                attempt_window_sec=config.settings.usage_limit_continue_attempt_window_sec,
            )),
            unlock_lockout=LockoutDecider(LockoutPolicy(
                max_attempts=config.settings.unlock_max_attempts,
                window_sec=config.settings.unlock_attempt_window_sec,
            )),
        )
