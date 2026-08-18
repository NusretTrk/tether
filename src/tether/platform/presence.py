"""
Is the user physically at the machine right now?

Everything that types into a window has to steal foreground focus first.
If that happens while someone is mid-sentence in another app, their
keystrokes land in the wrong place and the paste may land in the wrong
place too. Checking idle time first means a remote message can wait a few
seconds instead of fighting the person sitting at the keyboard.

GetLastInputInfo reports time since the last keyboard or mouse input
across the whole session, which is exactly the signal wanted here.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from tether.platform.capabilities import CAPABILITIES

log = logging.getLogger(__name__)


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


if CAPABILITIES.window_control:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def idle_seconds() -> float | None:
    """Seconds since the last keyboard/mouse input, or None if it can't be
    determined (non-Windows, or the call failed)."""
    if not CAPABILITIES.window_control:
        return None
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    # Both are tick counts from the same clock, so wraparound cancels out.
    return max(0.0, (_kernel32.GetTickCount() - info.dwTime) / 1000.0)


def is_user_active(threshold_sec: float) -> bool:
    """True if there was input within the last `threshold_sec`.

    A threshold of 0 disables the check entirely. When idle time can't be
    read, returns False - failing toward "go ahead and type" keeps the bot
    usable rather than silently refusing to do anything on a platform where
    this isn't implemented.
    """
    if threshold_sec <= 0:
        return False
    idle = idle_seconds()
    if idle is None:
        return False
    return idle < threshold_sec
