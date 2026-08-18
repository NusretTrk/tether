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

    temp_history: list[str] = field(default_factory=list)
    last_temp_alarm: float = 0.0

    staged_text: str | None = None
    active_ask_id: str | None = None

    # Set right after pressing Enter; cleared by transcript_job once the
    # matching USER_TEXT event is actually observed in the transcript — the
    # ground-truth confirmation that replaces the old screenshot-compare
    # heuristic. See transport/jobs.py and transport/text.py.
    pending_send_text: str | None = None
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0

    @staticmethod
    def build(config: Config) -> "AppState":
        target = ClaudeDesktopTarget(config.settings.claude_window_keyword)
        return AppState(
            config=config,
            target=target,
            activity_watcher=ActivityWatcher(target),
            dialog_watcher=DialogWatcher(target),
        )
