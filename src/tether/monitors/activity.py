"""
Watches session Running/Idle transitions via the target's UIA-backed session
list and reports which sessions just finished. Synchronous/blocking (UIA) —
callers must run poll() in a worker thread, never on the asyncio loop.
"""
from __future__ import annotations


class ActivityWatcher:
    def __init__(self, target):
        self._target = target
        self._last_state: dict[str, bool] = {}

    def poll(self) -> list[str]:
        """Returns names of sessions that just transitioned Running -> Idle."""
        sessions = self._target.list_sessions()
        current = {s.name: s.running for s in sessions}
        finished = [
            name for name, running in current.items()
            if self._last_state.get(name) is True and running is False
        ]
        self._last_state = current
        return finished
