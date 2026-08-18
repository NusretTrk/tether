"""Shared mutable state for the running bot, stored at bot_data["state"]."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from tether.config import Config
from tether.events import Event
from tether.monitors.activity import ActivityWatcher
from tether.monitors.dialogs import DialogWatcher
from tether.sources.transcript import TranscriptTailer
from tether.targets.claude_desktop import ClaudeDesktopTarget


@dataclass
class AppState:
    config: Config
    target: ClaudeDesktopTarget
    activity_watcher: ActivityWatcher
    dialog_watcher: DialogWatcher

    tailer: TranscriptTailer | None = None
    tailer_path: Path | None = None
    transcript_poll_count: int = 0
    last_event_time: float = field(default_factory=time.monotonic)

    live_streamer: object | None = None
    live_buffer: str = ""

    usage_limit_buffer: list[Event] = field(default_factory=list)
    usage_limit_streak: int = 0
    usage_limit_alerted: bool = False

    # error signature -> monotonic time last forwarded to Telegram,
    # so a repeating fault doesn't flood the chat (see error_handler).
    error_notify_times: dict[str, float] = field(default_factory=dict)

    # tool_use id -> (monotonic time seen, tool name). A call still sitting
    # here after a while means the agent is either blocked on a permission
    # prompt or running something long; either way worth surfacing.
    pending_tool_calls: dict[str, tuple[float, str]] = field(default_factory=dict)
    stall_notified: set[str] = field(default_factory=set)

    temp_history: list[str] = field(default_factory=list)
    last_temp_alarm: float = 0.0

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
        target = ClaudeDesktopTarget(config.settings.claude_window_keyword)
        return AppState(
            config=config,
            target=target,
            activity_watcher=ActivityWatcher(target, config.settings.activity_ignore_substrings),
            dialog_watcher=DialogWatcher(target),
        )
