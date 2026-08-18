"""
Deciding whether to restart a crashed app on its own.

The naive version - "app is gone, start it" - has two failure modes that
are both worse than staying down:

  1. A restart loop. If the app crashes during startup, restarting it
     forever burns CPU, spams notifications, and buries the real problem.
  2. Fighting the user. Someone who deliberately closed the app does not
     want it reappearing. From the outside, "user quit it" and "it crashed"
     look identical - the process is simply gone either way.

The second one is solved with idle time. If nobody has touched the
keyboard or mouse for longer than the detection window, the user cannot
have been the one who closed it during that window, so it was a crash. If
they were active, assume they meant it and leave it alone. They are at the
machine and can see the problem.

The logic lives here as a pure decision function, separate from anything
that touches processes, so every branch is testable without crashing a
real application to reach it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class RecoveryPolicy:
    enabled: bool = True
    max_attempts: int = 3
    # Attempts older than this are forgiven, so an app that dies once a day
    # is recovered every time rather than exhausting the budget forever.
    attempt_window_sec: float = 1800.0
    # Minimum gap between attempts, so a fast crash loop cannot spin.
    cooldown_sec: float = 120.0
    # The machine must have been idle at least this long for the
    # disappearance to count as a crash rather than a deliberate quit.
    # Should be >= the health check interval, otherwise a user who quit the
    # app moments after their last keypress looks like a crash.
    require_idle_sec: float = 90.0


@dataclass
class RecoveryDecider:
    policy: RecoveryPolicy
    _attempts: list[float] = field(default_factory=list)

    def _recent_attempts(self, now: float) -> list[float]:
        cutoff = now - self.policy.attempt_window_sec
        return [t for t in self._attempts if t >= cutoff]

    def should_recover(
        self,
        *,
        app_running: bool,
        was_running: bool | None,
        idle_seconds: float | None,
        now: float,
    ) -> tuple[bool, str]:
        """Returns (recover, reason). The reason is reported either way so
        a decision not to act is visible rather than silent."""
        if not self.policy.enabled:
            return (False, "disabled")
        if app_running:
            return (False, "still_running")
        if was_running is not True:
            # Either the first check since startup, or it was already down
            # and has been reported once. Not a fresh transition.
            return (False, "no_transition")

        if idle_seconds is None:
            # Can't tell whether the user is present, so can't tell a crash
            # from a deliberate quit. Report instead of guessing.
            return (False, "presence_unknown")
        if idle_seconds < self.policy.require_idle_sec:
            return (False, "user_active")

        recent = self._recent_attempts(now)
        if len(recent) >= self.policy.max_attempts:
            return (False, "attempt_limit_reached")
        if recent and (now - max(recent)) < self.policy.cooldown_sec:
            return (False, "cooling_down")

        return (True, "ok")

    def record_attempt(self, now: float) -> None:
        self._attempts = self._recent_attempts(now) + [now]

    def attempts_in_window(self, now: float) -> int:
        return len(self._recent_attempts(now))

    def reset(self) -> None:
        """Called when the app comes back up under its own steam - a
        successful recovery shouldn't count against future ones."""
        self._attempts = []
