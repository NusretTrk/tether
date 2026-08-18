"""
Watches for popups/dialogs/banners (e.g. "sign in again") via the target's
UIA-backed detector and reports newly-appeared ones. Synchronous/blocking
(UIA) — callers must run poll() in a worker thread.

Safety: this module only detects and reports. It never clicks anything.
Any future auto-click of a dialog button must go through an explicit,
reviewed allowlist — see design spec §7.4. Authentication prompts must never
be auto-actioned.
"""
from __future__ import annotations

from tether.targets.base import Dialog


class DialogWatcher:
    def __init__(self, target):
        self._target = target
        self._seen: set[str] = set()

    def poll(self) -> list[Dialog]:
        dialogs = self._target.detect_dialogs()
        new = [d for d in dialogs if d.name not in self._seen]
        self._seen = {d.name for d in dialogs}
        return new
