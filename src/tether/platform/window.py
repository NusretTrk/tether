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

from tether.platform.capabilities import CAPABILITIES, UnsupportedOnThisPlatform

log = logging.getLogger(__name__)

# Imported only where they exist. Everything below raises a clear error on
# other platforms instead of failing at import time and taking the whole
# bot down when the monitoring half would have worked fine.
if CAPABILITIES.window_control:
    from ctypes import windll

    import win32api
    import win32clipboard
    import win32com.client
    import win32con
    import win32gui
    import win32process
    import win32ui


def _require_windows(feature: str) -> None:
    if not CAPABILITIES.window_control:
        raise UnsupportedOnThisPlatform(feature)


def find_window_by_keyword(keyword: str) -> int | None:
    """Picks the largest-area match — emulator/tool windows often have a side
    toolbar that also matches the keyword; the real device screen is bigger."""
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
