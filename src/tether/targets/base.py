"""
Target interface — one implementation ships now (ClaudeDesktopTarget).
Cursor/VS Code/Antigravity (Phase 5, not built) are all Electron/Chromium
apps too, so the same window+UIA techniques apply; this protocol is the
seam that lets them drop in later without touching handler code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PasteResult:
    ok: bool
    reason: str = ""


@dataclass
class Session:
    name: str
    running: bool


@dataclass
class TargetStatus:
    model: str | None
    effort: str | None


@dataclass
class Dialog:
    name: str
    buttons: list[str]


class Target(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def focus(self) -> bool: ...

    def stage_text(self, text: str) -> PasteResult: ...
    def press_enter(self) -> bool: ...
    def clear_input(self) -> bool: ...
    def press_escape(self) -> bool: ...
    def click_stop_button(self) -> bool: ...

    def list_sessions(self) -> list[Session]: ...
    def switch_session(self, name: str) -> bool: ...

    def read_status(self) -> TargetStatus: ...
    def set_model(self, model: str) -> str | None: ...
    def set_effort(self, level: str) -> str | None: ...

    def detect_dialogs(self) -> list[Dialog]: ...

    def screenshot(self):  # -> PIL.Image.Image
        ...
