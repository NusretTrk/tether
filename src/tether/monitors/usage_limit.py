"""Pure parsing + attempt-capping logic for the usage-limit continuer.

No I/O here — see monitors/recovery.py for why this shape (a plain
function plus a small decider object holding only its own state) is worth
keeping instead of folding the logic into the job that calls it: every
branch is testable without a running bot, a real clock, or a real
transcript.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_AT_TIME_RE = re.compile(r"resets?\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
_IN_DURATION_ANCHOR_RE = re.compile(r"resets?\s+in\s+(.{0,30})", re.IGNORECASE)
_HOURS_RE = re.compile(r"(\d+)\s*h(?:ours?)?", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(\d+)\s*m(?:in(?:ute)?s?)?", re.IGNORECASE)


def parse_reset_time(text: str, now: datetime) -> datetime | None:
    """Best-effort extraction of when a usage limit resets, from whatever
    exact wording Claude used ("resets at 3pm", "resets at 15:30", "resets
    in 2 hours 15 minutes"). Returns None on anything unrecognized —
    callers must treat that as "unknown", never guess "now" or "soon"."""
    low = text.lower()

    m = _AT_TIME_RE.search(low)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        meridiem = m.group(3)
        if hour > 23 or minute > 59 or (hour > 12 and meridiem):
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    anchor = _IN_DURATION_ANCHOR_RE.search(low)
    if anchor:
        span = anchor.group(1)
        hm = _HOURS_RE.search(span)
        mm = _MINUTES_RE.search(span)
        hours = int(hm.group(1)) if hm else 0
        minutes = int(mm.group(1)) if mm else 0
        if hours or minutes:
            return now + timedelta(hours=hours, minutes=minutes)

    return None


@dataclass(frozen=True)
class ContinuePolicy:
    enabled: bool = True
    post_reset_delay_sec: int = 60
    max_attempts: int = 3
    # Generous window - this only caps a pathological loop (a misparsed
    # reset time, or the limit getting hit again immediately after
    # continuing), not normal once-a-day usage.
    attempt_window_sec: int = 21600


@dataclass
class ContinueDecider:
    """Tracks how many auto-continues have fired recently so a bad reset-time
    parse can't turn into an infinite retry loop. Mirrors RecoveryDecider's
    shape on purpose - same problem (cap a rare automatic action), same
    fix (prune a rolling window, count, cap)."""
    policy: ContinuePolicy
    attempt_times: list[float] = field(default_factory=list)

    def can_schedule(self, now: float) -> bool:
        if not self.policy.enabled:
            return False
        self.attempt_times = [t for t in self.attempt_times if now - t < self.policy.attempt_window_sec]
        return len(self.attempt_times) < self.policy.max_attempts

    def record_attempt(self, now: float) -> None:
        self.attempt_times.append(now)
