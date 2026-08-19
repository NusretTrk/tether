"""
Watches session Running/Idle transitions via the target's UIA-backed session
list and reports which sessions just finished. Synchronous/blocking (UIA) —
callers must run poll() in a worker thread, never on the asyncio loop.
"""
from __future__ import annotations


class ActivityWatcher:
    def __init__(self, target, ignore_substrings: list[str] | None = None):
        self._target = target
        self._last_state: dict[str, bool] = {}
        self._ignore = [s.lower() for s in (ignore_substrings or [])]

    def _is_ignored(self, name: str) -> bool:
        low = name.lower()
        return any(pattern in low for pattern in self._ignore)

    def poll(self) -> tuple[list[str], list[str]]:
        """Returns (started, finished) - names of sessions that just
        transitioned Idle -> Running, and Running -> Idle, respectively.

        A session's first observation only establishes its baseline state,
        it is never reported as "started" - otherwise every session already
        running when tether launches would get reported as just starting.

        Sessions matching an ignore pattern (see AppState construction,
        Settings.activity_ignore_substrings) are tracked for state but never
        reported - notably, the session tether is itself running inside of,
        which would otherwise report "finished"/"started" every time the
        controlling agent completes or starts a reply."""
        sessions = self._target.list_sessions()
        current = {s.name: s.running for s in sessions}
        started = [
            name for name, running in current.items()
            if self._last_state.get(name) is False
            and running is True
            and not self._is_ignored(name)
        ]
        finished = [
            name for name, running in current.items()
            if self._last_state.get(name) is True
            and running is False
            and not self._is_ignored(name)
        ]
        self._last_state = current
        return started, finished
