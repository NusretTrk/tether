"""
Generic text target for any window - Cursor, Antigravity, a terminal,
anything with one obvious input area, selected via /target.

Unlike ClaudeDesktopTarget, this does NOT try to OCR-locate a composer box
- that anchor-finding is tuned to Claude Desktop's exact placeholder text
and layout. Instead it optionally clicks a fixed point (input_click, a
window-relative percentage from keypad_profiles) before pasting, then
falls back to "trust whatever already has focus" if no click point is
configured.

That fallback is a real, disclosed limitation, confirmed live rather than
assumed against both Antigravity and Cursor. Antigravity needed
input_click from the first try - focusing the window alone never put
keyboard focus in its Agent chat panel. Cursor was worse in a subtler
way: a fresh window happened to already have its chat focused and a
blind paste worked, but that was leftover state, not a guarantee - after
clicking into Cursor's own terminal for an unrelated check, the exact
same blind-paste code sent the next message straight into the terminal
instead, where it ran as a shell command. So "let the fallback ride" is
only really safe for something that's the sole input in its window (a
dedicated terminal app); anything with more than one panel should get an
input_click configured, not just multi-panel apps where it "seems" needed.
"""
from __future__ import annotations

import time

import pyautogui
import pyperclip

from tether.platform.window import (
    capture_window, find_window_by_keyword, focus_window, get_window_rect,
    preserve_clipboard, set_clipboard_image,
)
from tether.targets.base import PasteResult


class GenericTarget:
    name = "generic"

    def __init__(self, window_keyword: str, preserve_user_clipboard: bool = True, input_click: tuple[float, float] | None = None):
        self.window_keyword = window_keyword
        self.preserve_user_clipboard = preserve_user_clipboard
        self.input_click = input_click  # (x_pct, y_pct) of window width/height, or None

    def _hwnd(self):
        return find_window_by_keyword(self.window_keyword)

    def _click_input(self, hwnd) -> None:
        if self.input_click is None:
            return
        left, top, right, bottom = get_window_rect(hwnd)
        x_pct, y_pct = self.input_click
        x = left + int((right - left) * x_pct)
        y = top + int((bottom - top) * y_pct)
        pyautogui.click(x, y)
        time.sleep(0.15)

    def is_available(self) -> bool:
        return self._hwnd() is not None

    def focus(self) -> bool:
        hwnd = self._hwnd()
        return bool(hwnd) and focus_window(hwnd)

    def stage_text(self, text: str) -> PasteResult:
        hwnd = self._hwnd()
        if not hwnd:
            return PasteResult(False, "window_not_found")
        with preserve_clipboard(self.preserve_user_clipboard):
            pyperclip.copy(text)
            if not focus_window(hwnd):
                return PasteResult(False, "focus_failed")
            time.sleep(0.2)
            self._click_input(hwnd)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)
        return PasteResult(True)

    def stage_photo(self, image_bytes: bytes, caption: str = "") -> PasteResult:
        hwnd = self._hwnd()
        if not hwnd:
            return PasteResult(False, "window_not_found")
        if not focus_window(hwnd):
            return PasteResult(False, "focus_failed")
        if not set_clipboard_image(image_bytes):
            return PasteResult(False, "clipboard_failed")
        time.sleep(0.2)
        self._click_input(hwnd)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        if caption:
            with preserve_clipboard(self.preserve_user_clipboard):
                pyperclip.copy(caption)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
        return PasteResult(True)

    def press_enter(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        self._click_input(hwnd)
        pyautogui.press("enter")
        return True

    def clear_input(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        self._click_input(hwnd)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("delete")
        return True

    def press_escape(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        pyautogui.press("escape")
        return True

    def screenshot(self):
        hwnd = self._hwnd()
        return capture_window(hwnd) if hwnd else None
