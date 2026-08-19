"""
Generic text target for any window - Cursor, Antigravity, a terminal,
anything with one obvious input area, selected via /target.

Unlike ClaudeDesktopTarget, this does NOT try to OCR-locate a composer box
- that anchor-finding is tuned to Claude Desktop's exact placeholder text
and layout, verified live against that one app. There's no way to verify
the equivalent for Cursor/Antigravity without having them open, so this
takes the honest, lower-fidelity approach instead: focus the window and
paste directly, trusting that whatever already has keyboard focus in that
app IS the input area. That holds for a terminal or a single-pane editor;
it does NOT hold for a multi-panel IDE where the wrong panel might be
focused, which is a real, known limitation - there is no before/after
verification here the way ClaudeDesktopTarget.stage_text has, because
there's no known place to look for one generically.
"""
from __future__ import annotations

import time

import pyautogui
import pyperclip

from tether.platform.window import (
    capture_window, find_window_by_keyword, focus_window, preserve_clipboard,
    set_clipboard_image,
)
from tether.targets.base import PasteResult


class GenericTarget:
    name = "generic"

    def __init__(self, window_keyword: str, preserve_user_clipboard: bool = True):
        self.window_keyword = window_keyword
        self.preserve_user_clipboard = preserve_user_clipboard

    def _hwnd(self):
        return find_window_by_keyword(self.window_keyword)

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
        pyautogui.press("enter")
        return True

    def clear_input(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
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
