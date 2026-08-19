"""Scheduling/cancelling a shutdown of the local machine.

Windows lets a normal (non-admin) user schedule its own shutdown via the
`shutdown` command - unlike Task Scheduler, which needs elevation. Gated by
CAPABILITIES.power_control so callers get a clear error on platforms where
this hasn't been verified, rather than a command that silently no-ops.
"""
from __future__ import annotations

import subprocess

from tether.platform.capabilities import CAPABILITIES, UnsupportedOnThisPlatform


def schedule_shutdown(seconds: int) -> bool:
    if not CAPABILITIES.power_control:
        raise UnsupportedOnThisPlatform("Shutdown scheduling")
    result = subprocess.run(
        ["shutdown", "/s", "/f", "/t", str(int(seconds))],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def cancel_shutdown() -> bool:
    if not CAPABILITIES.power_control:
        raise UnsupportedOnThisPlatform("Shutdown scheduling")
    result = subprocess.run(
        ["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0
