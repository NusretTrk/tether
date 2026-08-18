"""
Target implementation for Claude Desktop. Typing and the model/effort picker
stay pixel-driven (UIA doesn't reach the composer or main content — verified
live, see design spec §2.4); sessions and dialogs go through UIA instead of
OCR.

Model/effort control mechanics (all verified live against the running app
before being written here — see conversation history 2026-08-18):
  - Model dropdown: click the button, then click the matching option by text.
    The visible "1/2/3/4" numbers next to each option are NOT keyboard
    shortcuts — pressing the digit does nothing; a real click is required.
  - Effort slider: click the button to open the popover, then Tab twice
    (first Tab lands on the "?" help icon, second lands on the slider) —
    only then do Left/Right arrow keys step it one discrete level. Neither
    auto-focuses on open, and clicking the track at an arbitrary point was
    never verified safe, so this Tab-Tab-arrow sequence is the only path used.
"""
from __future__ import annotations

import logging
import time

import pyautogui
import pyperclip
import pytesseract
from PIL import Image

from tether.platform import uia
from tether.platform.capabilities import CAPABILITIES

if CAPABILITIES.accessibility:
    from _ctypes import COMError
else:
    class COMError(Exception):
        """Placeholder so except COMError is always valid, even where
        accessibility support (and the real COMError type) doesn't exist."""

if CAPABILITIES.window_control:
    import win32gui
from tether.platform.ocr import find_input_box_anchor, ocr_find_word, ocr_text
from tether.platform.window import capture_window, find_window_by_keyword, focus_window
from tether.targets.base import Dialog, PasteResult, Session, TargetStatus

log = logging.getLogger(__name__)

MODEL_NAMES = ("Fable", "Opus", "Sonnet", "Haiku")
EFFORT_LEVELS = ("Low", "Medium", "High", "Extra", "Max", "Ultracode")

INPUT_AREA_HEIGHT_PX = 120
INPUT_RIGHT_MARGIN_PX = 400


class ClaudeDesktopTarget:
    name = "claude-desktop"

    def __init__(self, window_keyword: str = "Claude"):
        self.window_keyword = window_keyword

    # ---- basics ----

    def _hwnd(self):
        if not CAPABILITIES.window_control:
            return None
        return find_window_by_keyword(self.window_keyword)

    def is_available(self) -> bool:
        if not CAPABILITIES.window_control:
            return False
        return self._hwnd() is not None

    def focus(self) -> bool:
        hwnd = self._hwnd()
        return bool(hwnd) and focus_window(hwnd)

    def screenshot(self) -> Image.Image | None:
        hwnd = self._hwnd()
        return capture_window(hwnd) if hwnd else None

    # ---- typing (pixel-driven) ----

    def stage_text(self, text: str) -> PasteResult:
        """Clicks into the input box and pastes, WITHOUT pressing Enter.
        Verified by an OCR before/after compare of the input area — not just
        "is it non-empty" (stale leftover text would pass that), but "did the
        content actually change". Delivery is confirmed separately by the
        caller via the transcript, which is ground truth; this only confirms
        the paste itself landed."""
        hwnd = self._hwnd()
        if not hwnd:
            return PasteResult(False, "window_not_found")
        pyperclip.copy(text)
        if not focus_window(hwnd):
            return PasteResult(False, "focus_failed")
        time.sleep(0.2)

        win_left, win_top, win_right, win_bottom = win32gui.GetWindowRect(hwnd)
        win_width = win_right - win_left
        anchor = find_input_box_anchor(capture_window(hwnd))
        if anchor:
            a_left, a_top, a_right, a_bottom = anchor
            click_x = win_left + a_left + 100
            click_y = win_top + (a_top + a_bottom) // 2
            crop_left = max(0, a_left - 20)
            crop_right = min(win_width, a_right + INPUT_RIGHT_MARGIN_PX)
        else:
            log.warning("find_input_box_anchor: placeholder not found, using fixed layout guess")
            click_x = win_left + win_width // 2
            click_y = win_bottom - INPUT_AREA_HEIGHT_PX // 2
            crop_left = int(win_width * 0.35)
            crop_right = int(win_width * 0.8)

        pyautogui.click(click_x, click_y)
        time.sleep(0.2)

        def _crop_input(img: Image.Image) -> Image.Image:
            h = img.height
            top = max(0, h - INPUT_AREA_HEIGHT_PX)
            return img.crop((crop_left, top, crop_right, h))

        before_text = ocr_text(_crop_input(capture_window(hwnd))).strip()
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        after_text = ocr_text(_crop_input(capture_window(hwnd))).strip()

        if not after_text or after_text == before_text:
            return PasteResult(False, "paste_not_detected")
        return PasteResult(True)

    def press_enter(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        time.sleep(0.15)
        pyautogui.press("enter")
        return True

    def clear_input(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("delete")
        return True

    # Keys that can be sent to whatever prompt is on screen. Agent tools put
    # up numbered choices ("1. yes  2. no  3. always"), y/n confirmations,
    # and free dialogs; without a way to answer these remotely you are stuck
    # watching a blocked session you cannot unblock.
    ALLOWED_KEYS = {
        "1", "2", "3", "4", "5", "y", "n", "a",
        "enter", "escape", "tab", "space", "backspace",
        "up", "down", "left", "right",
    }

    def send_key(self, key: str) -> bool:
        """Sends a single keystroke to the focused target window.
        `key` may also be 'shift+tab' for mode cycling."""
        key = key.lower().strip()

        # Validate before touching the window. Focusing first would let a
        # rejected key still yank focus away from whatever the user is doing.
        is_chord = key == "shift+tab"
        if not is_chord and key not in self.ALLOWED_KEYS:
            log.warning("refusing to send unrecognised key %r", key)
            return False

        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        time.sleep(0.15)

        if is_chord:
            pyautogui.hotkey("shift", "tab")
        else:
            pyautogui.press(key)
        return True

    def press_escape(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        pyautogui.press("escape")
        return True

    def click_stop_button(self) -> bool:
        """Looks for an on-screen 'Stop' button via OCR and clicks it — no
        confirmed keyboard shortcut exists. Falls back to Esc if not visible."""
        hwnd = self._hwnd()
        if not hwnd:
            return False
        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        pos = ocr_find_word(capture_window(hwnd), "Stop")
        if not focus_window(hwnd):
            return False
        time.sleep(0.15)
        if pos:
            pyautogui.click(left + pos[0], top + pos[1])
            return True
        pyautogui.press("escape")
        return False

    # ---- sessions (UIA) ----
    # All three UIA entry points below route through uia.run_on_uia_thread —
    # see the comment there for why (COM apartment marshaling across
    # asyncio.to_thread's general pool threads).

    def list_sessions(self) -> list[Session]:
        if not CAPABILITIES.accessibility:
            return []

        def _work():
            win = uia.find_root_window(self.window_keyword)
            if not win:
                return []
            uia.warm_up(win)
            named = uia.collect_named_controls(win)
            return [Session(name=n, running=r) for n, r in uia.parse_sessions(named)]
        try:
            return uia.run_on_uia_thread(_work)
        except COMError:
            # A live tree changing mid-walk is expected, not a fault worth
            # surfacing — the next poll a few seconds later just tries again.
            log.debug("list_sessions: transient COM error, skipping this poll")
            return []

    def switch_session(self, name: str) -> bool:
        if not CAPABILITIES.accessibility:
            return False

        def _work():
            win = uia.find_root_window(self.window_keyword)
            if not win:
                return False
            uia.warm_up(win)
            for label in (f"Running {name}", f"Idle {name}"):
                control = uia.find_control_by_name(win, label, control_type="ButtonControl")
                if control:
                    try:
                        control.Click(simulateMove=False)
                        return True
                    except Exception as e:
                        log.warning("session switch click failed: %s", e)
                        return False
            return False
        try:
            return uia.run_on_uia_thread(_work)
        except COMError:
            log.debug("switch_session: transient COM error")
            return False

    # ---- dialogs (UIA) ----

    def detect_dialogs(self) -> list[Dialog]:
        if not CAPABILITIES.accessibility:
            return []

        def _work():
            win = uia.find_root_window(self.window_keyword)
            if not win:
                return []
            uia.warm_up(win)
            named = uia.collect_named_controls(win)
            return [Dialog(name=n, buttons=b) for n, b in uia.detect_dialogs(named)]
        try:
            return uia.run_on_uia_thread(_work)
        except COMError:
            log.debug("detect_dialogs: transient COM error, skipping this poll")
            return []

    # ---- model / effort (pixel-driven, verified live) ----

    def _find_model_effort_buttons(self, hwnd):
        img = capture_window(hwnd)
        h = img.height
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        tokens = []
        for i, word in enumerate(data["text"]):
            word = word.strip()
            if not word or not any(c.isalpha() for c in word):
                continue
            if data["top"][i] < h - 50:
                continue
            l, t, ww, hh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            tokens.append((l, t, l + ww, t + hh))
        if len(tokens) < 2:
            return None
        tokens.sort(key=lambda tok: tok[0])
        model_tok, effort_tok = tokens[-2], tokens[-1]

        def center(tok):
            l, t, r, b = tok
            return (l + r) // 2, (t + b) // 2

        return center(model_tok), center(effort_tok)

    def _status_bar_words(self, hwnd) -> list[str]:
        img = capture_window(hwnd)
        h = img.height
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        return [w.strip() for i, w in enumerate(data["text"]) if w.strip() and data["top"][i] >= h - 50]

    def read_status(self) -> TargetStatus:
        hwnd = self._hwnd()
        if not hwnd:
            return TargetStatus(model=None, effort=None)
        text = " ".join(self._status_bar_words(hwnd)).lower()
        model = next((n for n in MODEL_NAMES if n.lower() in text), None)
        effort = next((lvl for lvl in EFFORT_LEVELS if lvl.lower() in text), None)
        return TargetStatus(model=model, effort=effort)

    def set_model(self, model: str) -> str | None:
        match = next((n for n in MODEL_NAMES if n.lower().startswith(model.lower())), None)
        if not match:
            return None
        hwnd = self._hwnd()
        if not hwnd:
            return None
        buttons = self._find_model_effort_buttons(hwnd)
        if not buttons:
            return None
        model_btn, _ = buttons
        if not focus_window(hwnd):
            return None
        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        pyautogui.click(left + model_btn[0], top + model_btn[1])
        time.sleep(0.4)

        img = capture_window(hwnd)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        pos = None
        for i, word in enumerate(data["text"]):
            if word.strip().lower() != match.lower():
                continue
            wx, wy = data["left"][i], data["top"][i]
            if abs(wx - model_btn[0]) < 250 and (model_btn[1] - 300) < wy < (model_btn[1] - 5):
                pos = (wx + data["width"][i] // 2, wy + data["height"][i] // 2)
                break

        if not pos:
            pyautogui.press("escape")
            return None
        pyautogui.click(left + pos[0], top + pos[1])
        time.sleep(0.3)
        return match

    def set_effort(self, level: str) -> str | None:
        match = next((lvl for lvl in EFFORT_LEVELS if lvl.lower().startswith(level.lower())), None)
        if not match:
            return None
        hwnd = self._hwnd()
        if not hwnd:
            return None
        current = self.read_status().effort
        if current is None:
            return None
        buttons = self._find_model_effort_buttons(hwnd)
        if not buttons:
            return None
        _, effort_btn = buttons
        if not focus_window(hwnd):
            return None
        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        pyautogui.click(left + effort_btn[0], top + effort_btn[1])
        time.sleep(0.4)
        pyautogui.press("tab")
        time.sleep(0.1)
        pyautogui.press("tab")
        time.sleep(0.1)

        delta = EFFORT_LEVELS.index(match) - EFFORT_LEVELS.index(current)
        key = "right" if delta > 0 else "left"
        for _ in range(abs(delta)):
            pyautogui.press(key)
            time.sleep(0.15)

        time.sleep(0.2)
        pyautogui.press("escape")
        time.sleep(0.2)

        result = self.read_status().effort
        return result if result == match else None
