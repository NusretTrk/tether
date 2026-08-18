"""Only ClaudeDesktopTarget ships today. Phase 5 (not built) adds Cursor,
VS Code, and Antigravity adapters here behind the same Target protocol."""
from __future__ import annotations

from tether.targets.claude_desktop import ClaudeDesktopTarget

_ACTIVE: ClaudeDesktopTarget | None = None


def get_target(window_keyword: str = "Claude") -> ClaudeDesktopTarget:
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = ClaudeDesktopTarget(window_keyword)
    return _ACTIVE
