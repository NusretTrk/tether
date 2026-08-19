"""
macOS window find/focus/capture, via `osascript` (AppleScript) — the same
mechanism a person would use to script the Finder or automate an app, so it
needs Accessibility permission granted to the terminal/process running
tether, same as any macOS automation tool.

UNVERIFIED: written against documented AppleScript/System Events syntax,
never run against a real Claude Desktop window on macOS. The window-find/
focus/rect primitives here are the load-bearing ones for basic remote
control (stage_text, press_enter, screenshots); the pixel-OCR-driven
model/effort picker in targets/claude_desktop.py was tuned against the
Windows build's exact layout and may not line up on macOS even once these
primitives work — expect that to need real adjustment, not just testing.
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import time

import pyautogui
from PIL import Image

from tether.platform.capabilities import CAPABILITIES, UnsupportedOnThisPlatform

log = logging.getLogger(__name__)


def _require_macos(feature: str) -> None:
    if not CAPABILITIES.window_control:
        raise UnsupportedOnThisPlatform(feature)


def _osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"osascript exited {result.returncode}")
    return result.stdout.strip()


def find_window_by_keyword(keyword: str, path_contains: str | None = None) -> str | None:
    """Returns the owning process name of the first window whose title
    contains keyword, or None. That process name is the "handle" every
    other function here takes — macOS automation addresses apps/windows by
    name, not by an opaque numeric id the way Win32/X11 do.

    `path_contains` is accepted for signature compatibility with the
    Windows implementation (which uses it to reject a title match whose
    owning process lives somewhere unexpected — e.g. a browser tab
    outranking the real app purely by title) but not applied here yet:
    doing this properly needs real Mac hardware to verify against, which
    this project doesn't have (see the module-level "unverified" note)."""
    _require_macos("Finding a window")
    safe_keyword = keyword.replace('"', "")
    script = f'''
    tell application "System Events"
        repeat with p in (every process whose background only is false)
            try
                repeat with w in (every window of p)
                    if (name of w as text) contains "{safe_keyword}" then
                        return name of p
                    end if
                end repeat
            end try
        end repeat
    end tell
    return ""
    '''
    try:
        name = _osascript(script)
    except RuntimeError as e:
        log.warning("find_window_by_keyword (macOS) failed: %s", e)
        return None
    return name or None


def get_window_rect(handle: str) -> tuple[int, int, int, int]:
    """(left, top, right, bottom), screen pixels."""
    _require_macos("Getting window rect")
    safe_handle = handle.replace('"', "")
    script = f'''
    tell application "System Events"
        tell process "{safe_handle}"
            set {{px, py}} to position of window 1
            set {{w, h}} to size of window 1
            return (px as text) & "," & (py as text) & "," & (w as text) & "," & (h as text)
        end tell
    end tell
    '''
    out = _osascript(script)
    px, py, w, h = (int(float(v)) for v in out.split(","))
    return (px, py, px + w, py + h)


def focus_window(handle: str, retries: int = 4) -> bool:
    _require_macos("Focusing a window")
    for _ in range(retries):
        try:
            _osascript(f'tell application "{handle}" to activate')
        except RuntimeError as e:
            log.warning("focus_window (macOS) failed: %s", e)
        time.sleep(0.15)
        try:
            frontmost = _osascript(
                'tell application "System Events" to get name of first process whose frontmost is true'
            )
        except RuntimeError:
            frontmost = ""
        if frontmost == handle:
            return True
    log.error("focus_window (macOS): could not confirm frontmost for %r", handle)
    return False


def capture_window(handle: str) -> Image.Image:
    """No PrintWindow equivalent used here (unlike the Windows path) — this
    is a screen-region grab of the window's current bounds, so an
    overlapping window in front of it will show up in the capture. A real
    per-window capture would need CGWindowListCreateImage via pyobjc/Quartz;
    left as a follow-up rather than an untestable ObjC bridging guess."""
    _require_macos("Capturing a window")
    left, top, right, bottom = get_window_rect(handle)
    return pyautogui.screenshot(region=(left, top, right - left, bottom - top))


def set_clipboard_image(image_bytes: bytes) -> bool:
    """`set the clipboard to (read ... as «class PNGf»)` is the standard
    AppleScript idiom for putting an image (not raw bytes) on the
    clipboard, which is what a real Cmd+V paste of a picture expects."""
    _require_macos("Setting clipboard image")
    path = None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f, "PNG")
            path = f.name
        _osascript(f'set the clipboard to (read (POSIX file "{path}") as «class PNGf»)')
        return True
    except Exception as e:
        log.warning("set_clipboard_image (macOS) failed: %s", e)
        return False
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
