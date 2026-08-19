"""
What this machine can actually do.

Reading a Claude Code session works anywhere, because it comes from a
transcript file on disk. Driving the app - typing, switching sessions,
reading dialogs - needs OS specific window control, and only the Windows
implementation exists today.

Rather than crash on import on a Mac, the platform modules check here and
degrade: monitoring, streaming, notifications and the MCP tools all work,
and the control features report clearly that they are unavailable instead
of raising an ImportError from somewhere deep in the stack.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


@dataclass(frozen=True)
class Capabilities:
    window_control: bool     # focus, type, screenshot a window
    accessibility: bool      # session list, dialog detection
    hardware_temps: bool     # CPU temperature
    shell: bool              # /cmd
    # Scheduling/cancelling a shutdown of the local machine without admin.
    # `shutdown /s /t N` works as a normal user on Windows; macOS/Linux
    # equivalents typically need root, so this stays False there until
    # that's actually verified rather than assumed to work.
    power_control: bool

    @property
    def any_control(self) -> bool:
        return self.window_control or self.accessibility


def detect() -> Capabilities:
    if IS_WINDOWS:
        return Capabilities(
            window_control=True,
            accessibility=True,
            hardware_temps=True,
            shell=True,
            power_control=True,
        )
    # Basic window control (find/focus/type/screenshot) is implemented for
    # macOS (osascript/System Events) and Linux (xdotool, X11 only) - see
    # platform/window_macos.py and window_linux.py. UNVERIFIED: built
    # against documented syntax, never run on a real Mac/Linux machine.
    #
    # Session list / dialog detection / model & effort reading go through
    # UIA on Windows, which has no macOS (Accessibility API) or Linux
    # (AT-SPI) port here yet - accessibility stays honestly False rather
    # than a guess at API surface nobody has verified.
    return Capabilities(
        window_control=True,
        accessibility=False,
        hardware_temps=False,
        shell=True,
        power_control=False,
    )


CAPABILITIES = detect()


def platform_name() -> str:
    if IS_WINDOWS:
        return "Windows"
    if IS_MACOS:
        return "macOS"
    if IS_LINUX:
        return "Linux"
    return sys.platform


class UnsupportedOnThisPlatform(RuntimeError):
    """Raised when a control feature is used on an OS that lacks it."""

    def __init__(self, feature: str):
        super().__init__(
            f"{feature} is only implemented on Windows. "
            f"Running on {platform_name()}: monitoring, streaming and "
            f"notifications work, but controlling the app does not."
        )
