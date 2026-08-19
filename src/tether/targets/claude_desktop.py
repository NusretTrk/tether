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

from tether.platform import process, uia
from tether.platform.capabilities import CAPABILITIES

if CAPABILITIES.accessibility:
    from _ctypes import COMError
else:
    class COMError(Exception):
        """Placeholder so except COMError is always valid, even where
        accessibility support (and the real COMError type) doesn't exist."""

from tether.platform.ocr import find_input_box_anchor, ocr_find_word, ocr_text
from tether.platform.window import (
    capture_window, find_window_by_keyword, focus_window, get_window_rect,
    preserve_clipboard, set_clipboard_image,
)
from tether.targets.base import Dialog, PasteResult, Session, TargetStatus

log = logging.getLogger(__name__)

MODEL_NAMES = ("Fable", "Opus", "Sonnet", "Haiku")
EFFORT_LEVELS = ("Low", "Medium", "High", "Extra", "Max", "Ultracode")

INPUT_AREA_HEIGHT_PX = 120
INPUT_RIGHT_MARGIN_PX = 400


class ClaudeDesktopTarget:
    name = "claude-desktop"

    # Claude Desktop runs as many Electron processes all named claude.exe,
    # and the bundled Claude Code CLI is *also* claude.exe under a different
    # path. Filtering on this path fragment targets the desktop app without
    # touching the CLI - verified live: 11 desktop processes, 1 CLI, no
    # overlap. A name-based kill would have taken out both.
    DEFAULT_APP_PATH_FILTER = "WindowsApps"

    def __init__(
        self,
        window_keyword: str = "Claude",
        app_path_filter: str = "",
        launch_command: str = "",
        preserve_user_clipboard: bool = True,
    ):
        self.window_keyword = window_keyword
        self.app_path_filter = app_path_filter or self.DEFAULT_APP_PATH_FILTER
        self.launch_command = launch_command
        self.preserve_user_clipboard = preserve_user_clipboard

    # ---- app lifecycle ----

    def list_app_processes(self) -> list:
        return process.list_processes(name_contains="claude", path_contains=self.app_path_filter)

    def is_app_running(self) -> bool:
        return bool(self.list_app_processes())

    def resolve_launch_command(self) -> str | None:
        """Configured command wins; otherwise discover the Store app's
        AppUserModelID at runtime, since the package family name contains a
        per-install hash and differs between machines."""
        if self.launch_command:
            return self.launch_command
        return process.find_appx_launch_command("Claude")

    def stop_app(self, timeout: float = 20.0) -> tuple[int, bool]:
        """Kills the desktop app and waits for every handle to release.
        Returns (processes signalled, all actually exited)."""
        procs = self.list_app_processes()
        if not procs:
            return (0, True)
        return process.kill_all(procs, timeout=timeout)

    def launch_app(self) -> bool:
        cmd = self.resolve_launch_command()
        if not cmd:
            log.warning("no launch command available for Claude Desktop")
            return False
        return process.launch(cmd)

    def wait_for_window(self, timeout: float = 60.0, poll: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._hwnd():
                return True
            time.sleep(poll)
        return False

    def restart_app(self, stop_timeout: float = 20.0, start_timeout: float = 60.0) -> tuple[bool, str]:
        """Stop, wait for handles to actually release, then start again.

        The waiting is the point. Relaunching while the old processes still
        hold file handles is what produces "Another program is currently
        using this file" - the exact error that motivated this. Returns
        (ok, reason) so the caller can report which step failed rather than
        just succeeding or not."""
        _, all_gone = self.stop_app(timeout=stop_timeout)
        if not all_gone:
            return (False, "processes_still_running")
        if not self.launch_app():
            return (False, "launch_failed")
        if not self.wait_for_window(timeout=start_timeout):
            return (False, "window_never_appeared")
        return (True, "ok")

    # ---- basics ----

    def _hwnd(self):
        if not CAPABILITIES.window_control:
            return None
        # app_path_filter already exists for process-killing (Claude
        # Desktop and the separate Claude Code CLI share the same
        # claude.exe name) - threading it into window-finding too closes
        # a real bug: a browser tab with "Claude" in its title can
        # otherwise outrank the real app purely on window area, silently
        # becoming the target for every click/paste/OCR call that follows.
        return find_window_by_keyword(self.window_keyword, path_contains=self.app_path_filter)

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
        with preserve_clipboard(self.preserve_user_clipboard):
            return self._stage_text_inner(hwnd, text)

    def _stage_text_inner(self, hwnd, text: str) -> PasteResult:
        pyperclip.copy(text)
        if not focus_window(hwnd):
            return PasteResult(False, "focus_failed")
        time.sleep(0.2)

        win_left, win_top, win_right, win_bottom = get_window_rect(hwnd)
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

    def stage_photo(self, image_bytes: bytes, caption: str = "") -> PasteResult:
        """Same click-and-paste mechanism as stage_text, but puts an image
        on the clipboard instead of text — this is how Claude Desktop
        receives a pasted screenshot normally, so a photo forwarded from
        Telegram lands the same way. Verified by comparing pixel content of
        the input area before/after (OCR doesn't apply to an image), rather
        than the before/after text compare stage_text uses.

        If `caption` is given, it's pasted right after the image lands —
        the image becomes an attachment chip and the cursor stays in the
        text area, so a second paste continues typing after it rather than
        replacing it. This is what makes "photo with a caption" arrive as
        one message instead of needing two separate sends."""
        hwnd = self._hwnd()
        if not hwnd:
            return PasteResult(False, "window_not_found")
        with preserve_clipboard(self.preserve_user_clipboard):
            return self._stage_photo_inner(hwnd, image_bytes, caption)

    def _stage_photo_inner(self, hwnd, image_bytes: bytes, caption: str) -> PasteResult:
        if not set_clipboard_image(image_bytes):
            return PasteResult(False, "clipboard_failed")
        if not focus_window(hwnd):
            return PasteResult(False, "focus_failed")
        time.sleep(0.2)

        win_left, win_top, win_right, win_bottom = get_window_rect(hwnd)
        win_width = win_right - win_left
        anchor = find_input_box_anchor(capture_window(hwnd))
        if anchor:
            a_left, a_top, a_right, a_bottom = anchor
            click_x = win_left + a_left + 100
            click_y = win_top + (a_top + a_bottom) // 2
            crop_left = max(0, a_left - 20)
            crop_right = min(win_width, a_right + INPUT_RIGHT_MARGIN_PX)
        else:
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

        before = _crop_input(capture_window(hwnd)).tobytes()
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.6)  # image paste renders a thumbnail — give it longer than text
        after = _crop_input(capture_window(hwnd)).tobytes()

        if after == before:
            return PasteResult(False, "paste_not_detected")

        if caption:
            pyperclip.copy(caption)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)

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

    # Chords (modifier+base) beyond the single keys above — needed for
    # per-app keypad profiles (Cursor's accept/reject, terminal Ctrl+C,
    # save-as-Ctrl+S) without opening this up to anything typeable.
    # "alt" is deliberately not a safe modifier at all, not even paired
    # with an allowlisted base key — alt+f4 closes the window, alt+tab
    # switches focus away from the target, alt+space opens the window
    # menu, alt+enter toggles fullscreen in many apps. A per-key blocklist
    # for "alt" would be a losing game; excluding the modifier is the
    # actual fix (caught by test_dangerous_combinations_rejected, which
    # found alt+f4 slipping through the first version of this).
    SAFE_CHORD_MODIFIERS = {"ctrl", "shift"}
    SAFE_CHORD_BASE_KEYS = ALLOWED_KEYS | {
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
        "delete", "home", "end", "pageup", "pagedown", "insert",
        "c", "v", "x", "z", "s", "d", "w", "p", "f", "r", "o", "n", "k", "l", "b", "i", "u",
    }

    @classmethod
    def is_valid_key_spec(cls, spec: str) -> bool:
        """A single key from ALLOWED_KEYS, or a '+'-joined chord of one or
        more SAFE_CHORD_MODIFIERS followed by one SAFE_CHORD_BASE_KEYS."""
        spec = spec.lower().strip()
        if not spec:
            return False
        parts = spec.split("+")
        if len(parts) == 1:
            return parts[0] in cls.ALLOWED_KEYS
        *mods, base = parts
        if not mods or not base:
            return False
        return all(m in cls.SAFE_CHORD_MODIFIERS for m in mods) and base in cls.SAFE_CHORD_BASE_KEYS

    def send_key(self, key: str, window_keyword: str | None = None) -> bool:
        """Sends a keystroke or chord to the focused target window.
        `window_keyword` lets a keypad profile target a different app
        (Cursor, a terminal) than whatever this instance's own
        window_keyword is bound to — the mechanism here is generic window
        focus + keystroke, nothing Claude-specific about it."""
        key = key.lower().strip()

        # Validate before touching the window. Focusing first would let a
        # rejected key still yank focus away from whatever the user is doing.
        if not self.is_valid_key_spec(key):
            log.warning("refusing to send unrecognised/unsafe key %r", key)
            return False

        if window_keyword:
            hwnd = find_window_by_keyword(window_keyword) if CAPABILITIES.window_control else None
        else:
            hwnd = self._hwnd()
        if not hwnd or not focus_window(hwnd):
            return False
        time.sleep(0.15)

        parts = key.split("+")
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
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
        left, top, _, _ = get_window_rect(hwnd)
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
        left, top, _, _ = get_window_rect(hwnd)
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
        left, top, _, _ = get_window_rect(hwnd)
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
