"""
Caps repeated /unlock guesses against BOT_PASSWORD. Pure decision object,
same shape as RecoveryDecider/ContinueDecider - the thing worth capping
here is a compromised Telegram account rapid-firing password guesses, which
is exactly the scenario the password exists to slow down in the first
place, so the cap itself needs to be right.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LockoutPolicy:
    max_attempts: int = 5
    window_sec: int = 300


@dataclass
class LockoutDecider:
    policy: LockoutPolicy
    failure_times: list[float] = field(default_factory=list)

    def is_locked_out(self, now: float) -> bool:
        """Prunes the window as a side effect, same as the other deciders,
        so callers never see stale failures."""
        self.failure_times = [t for t in self.failure_times if now - t < self.policy.window_sec]
        return len(self.failure_times) >= self.policy.max_attempts

    def record_failure(self, now: float) -> None:
        self.failure_times.append(now)

    def reset(self) -> None:
        self.failure_times = []
