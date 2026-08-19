"""
Window find/focus/capture. Ported from the original bot.py — this logic was
already fixed against real bugs (largest-area match, foreground-focus
verification with fallbacks, PrintWindow buffer capture) and is unchanged
here, just relocated.
"""
from __future__ import annotations

import logging
import time
import pyautogui
from PIL import Image

from tether.platform.capabilities import CAPABILITIES, IS_WINDOWS, UnsupportedOnThisPlatform

log = logging.getLogger(__name__)

# Imported only where they exist. Everything below raises a clear error on
# other platforms instead of failing at import time and taking the whole
# bot down when the monitoring half would have worked fine.
if IS_WINDOWS and CAPABILITIES.window_control:
    from ctypes import windll

    import win32api
    import win32clipboard
    import win32com.client
    import win32con
    import win32gui
    import win32process
    import win32ui


def _require_windows(feature: str) -> None:
    # Every function below this point is Windows-specific by construction
    # (raw win32 calls) — gated on IS_WINDOWS, not just window_control,
    # because window_control is also True on macOS/Linux once their own
    # implementations exist. Those platforms get their real
    # find_window_by_keyword/focus_window/etc. from the dispatch at the
    # bottom of this file, which overrides the names defined here.
    if not (IS_WINDOWS and CAPABILITIES.window_control):
        raise UnsupportedOnThisPlatform(feature)


def find_window_by_keyword(keyword: str, path_contains: str | None = None) -> int | None:
    """Picks the largest-area match — emulator/tool windows often have a side
    toolbar that also matches the keyword; the real device screen is bigger.

    `path_contains`, when given, also requires the winning window's OWNING
    PROCESS's executable path to contain that substring. Without this, any
    window whose TITLE merely contains the keyword can win purely on
    screen area — a maximized browser tab titled "Claude - talk to..." (or
    a folder, a doc page, anything with "Cursor"/"Antigravity" in its
    title) can outrank the real app and become the target for every
    click/paste/OCR call that follows, with no error raised anywhere: the
    window is real, it's just the wrong one. This is exactly the problem
    process.py's own path-based filtering already solved for killing
    processes (Claude Desktop and the separate Claude Code CLI share the
    same claude.exe name) - window-finding needed the same protection and
    never had it.

    If path_contains eliminates every title match (e.g. the app is
    installed somewhere the configured filter doesn't expect), falls back
    to the unfiltered result rather than reporting "not found" for a
    window that title-matched fine before - this can only ever narrow
    results when it has positive evidence, never break a setup that
    worked under title-matching alone."""
    _require_windows("Finding a window")
    matches: list[int] = []

    def _enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title and keyword.lower() in title.lower():
            matches.append(hwnd)

    win32gui.EnumWindows(_enum_handler, None)
    if not matches:
        return None

    if path_contains:
        from tether.platform import process
        filtered = []
        for hwnd in matches:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            path = process.path_for_pid(pid)
            if path and path_contains.lower() in path.lower():
                filtered.append(hwnd)
        if filtered:
            matches = filtered

    def _area(hwnd):
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (right - left) * (bottom - top)

    return max(matches, key=_area)


def focus_window(hwnd, retries: int = 4) -> bool:
    """Bring window to foreground AND verify it actually landed there.
    SetForegroundWindow can fail silently (Windows blocks background processes
    from stealing focus) — every caller must check the return value and abort
    rather than send input on a False."""
    _require_windows("Focusing a window")
    for _ in range(retries):
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        try:
            win32com.client.Dispatch("WScript.Shell").SendKeys("%")
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
            cur_thread = win32api.GetCurrentThreadId()
            win32process.AttachThreadInput(cur_thread, fg_thread, True)
            win32process.AttachThreadInput(cur_thread, target_thread, True)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32process.AttachThreadInput(cur_thread, fg_thread, False)
            win32process.AttachThreadInput(cur_thread, target_thread, False)
        except Exception as e:
            log.warning("focus_window AttachThreadInput failed: %s", e)
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        time.sleep(0.15)

    log.error("focus_window: could not confirm foreground for hwnd=%s", hwnd)
    return False


def get_window_rect(hwnd) -> tuple[int, int, int, int]:
    """(left, top, right, bottom), screen pixels."""
    _require_windows("Getting window rect")
    return win32gui.GetWindowRect(hwnd)


def _get_clipboard_text() -> str | None:
    """Current clipboard text, or None if the clipboard holds something
    else (or nothing)."""
    try:
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return None
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def _set_clipboard_text(text: str) -> bool:
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            return True
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return False


class preserve_clipboard:
    """Restores the user's clipboard text after a paste.

    Pasting into the target app means putting our content on the clipboard,
    which silently destroys whatever the person at the keyboard had copied.
    They notice when their next Ctrl+V produces a message they sent from
    their phone half an hour ago.

    Only text is preserved. Restoring arbitrary clipboard formats means
    enumerating and round-tripping every one of them, including
    application-private formats that don't survive it - reliably worse than
    doing nothing. Text covers the overwhelmingly common case; if the
    clipboard held an image or a file list, it is left as our content and
    that limitation is documented rather than half-handled.

    Windows only for now - macOS/Linux paste still works without this, it
    just won't restore whatever the user had copied beforehand. Text
    clipboard preservation there would need a per-platform get/set (NSPasteboard
    via pyobjc, or xclip) rather than the win32clipboard calls this uses.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and IS_WINDOWS and CAPABILITIES.window_control
        self._saved: str | None = None

    def __enter__(self):
        if self.enabled:
            self._saved = _get_clipboard_text()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.enabled and self._saved is not None:
            # Best effort - a failure here must not mask an exception from
            # the block itself.
            try:
                _set_clipboard_text(self._saved)
            except Exception as e:
                log.debug("could not restore clipboard: %s", e)
        return False


def set_clipboard_image(image_bytes: bytes) -> bool:
    """Puts image bytes on the Windows clipboard as CF_DIB, the format a
    plain Ctrl+V paste expects — this is how a screenshot copied normally
    ends up pasteable anywhere, images sent from Telegram use the same
    path. BMP-without-its-14-byte-file-header is a valid CF_DIB payload,
    the standard trick for this on Windows."""
    _require_windows("Setting clipboard image")
    import io
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "BMP")
        dib = buf.getvalue()[14:]
        buf.close()
    except Exception as e:
        log.warning("set_clipboard_image: could not decode/convert image: %s", e)
        return False

    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        log.warning("set_clipboard_image: clipboard write failed: %s", e)
        return False


def capture_window(hwnd) -> Image.Image:
    """Grab window's own buffer via PrintWindow — correct even if another
    window overlaps it on screen."""
    _require_windows("Capturing a window")
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        pyautogui.sleep(0.2)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)

    windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)  # PW_RENDERFULLCONTENT

    info = bitmap.GetInfo()
    bits = bitmap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    return img


# ---------------------------------------------------------------------
# Non-Windows dispatch. Everything above this point is the original,
# unchanged Windows implementation (raises via _require_windows if somehow
# called on another OS). On macOS/Linux, once CAPABILITIES.window_control
# is true, these imports override the names above with the real
# implementations — see window_macos.py / window_linux.py for the
# unverified AppleScript/xdotool mechanics and their known limitations.
# ---------------------------------------------------------------------
if not IS_WINDOWS and CAPABILITIES.window_control:
    from tether.platform.capabilities import IS_LINUX, IS_MACOS

    if IS_MACOS:
        from tether.platform.window_macos import (  # noqa: F401,F811
            capture_window, find_window_by_keyword, focus_window,
            get_window_rect, set_clipboard_image,
        )
    elif IS_LINUX:
        from tether.platform.window_linux import (  # noqa: F401,F811
            capture_window, find_window_by_keyword, focus_window,
            get_window_rect, set_clipboard_image,
        )
