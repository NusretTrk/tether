"""
GenericTarget is the fallback-path implementation used by /target for
anything that isn't Claude Desktop - no OCR-located input box, just focus
+ paste. These tests mock the underlying window primitives (already
covered by their own tests) to check GenericTarget wires them correctly:
window-not-found and focus-failed both refuse cleanly rather than pasting
into whatever happens to be focused.
"""
from tether.targets import generic as generic_mod
from tether.targets.generic import GenericTarget


def test_stage_text_fails_cleanly_when_window_not_found(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: None)
    t = GenericTarget("Cursor")
    result = t.stage_text("hello")
    assert not result.ok
    assert result.reason == "window_not_found"


def test_stage_text_fails_cleanly_when_focus_fails(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: False)
    monkeypatch.setattr(generic_mod.pyperclip, "copy", lambda text: None)
    t = GenericTarget("Cursor")
    result = t.stage_text("hello")
    assert not result.ok
    assert result.reason == "focus_failed"


def test_stage_text_pastes_after_focusing(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    copied = []
    monkeypatch.setattr(generic_mod.pyperclip, "copy", lambda text: copied.append(text))
    hotkeys = []
    monkeypatch.setattr(generic_mod.pyautogui, "hotkey", lambda *a: hotkeys.append(a))
    t = GenericTarget("Cursor")
    result = t.stage_text("hello world")
    assert result.ok
    assert copied == ["hello world"]
    assert ("ctrl", "v") in hotkeys


def test_press_enter_requires_window_and_focus(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: None)
    t = GenericTarget("Cursor")
    assert t.press_enter() is False


def test_press_enter_sends_enter_key(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    presses = []
    monkeypatch.setattr(generic_mod.pyautogui, "press", lambda key: presses.append(key))
    t = GenericTarget("Cursor")
    assert t.press_enter() is True
    assert presses == ["enter"]


def test_is_available_reflects_window_presence(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: None)
    assert GenericTarget("Cursor").is_available() is False
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    assert GenericTarget("Cursor").is_available() is True


def test_stage_photo_fails_cleanly_when_clipboard_set_fails(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(generic_mod, "set_clipboard_image", lambda b: False)
    t = GenericTarget("Cursor")
    result = t.stage_photo(b"fake-image-bytes")
    assert not result.ok
    assert result.reason == "clipboard_failed"


def test_stage_photo_pastes_caption_after_image(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(generic_mod, "set_clipboard_image", lambda b: True)
    copied = []
    monkeypatch.setattr(generic_mod.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr(generic_mod.pyautogui, "hotkey", lambda *a: None)
    t = GenericTarget("Cursor")
    result = t.stage_photo(b"fake-image-bytes", caption="see this")
    assert result.ok
    assert copied == ["see this"]


# --- input_click ---------------------------------------------------------
# Added after live-testing against a real open Antigravity window: focusing
# the window alone did NOT put keyboard focus in its Agent chat panel (a
# blind paste landed nowhere), but clicking the panel first fixed it
# completely. input_click is that click point, as a window-relative
# percentage so it survives the window being moved/resized.

def test_no_input_click_configured_never_clicks(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(generic_mod.pyperclip, "copy", lambda text: None)
    monkeypatch.setattr(generic_mod.pyautogui, "hotkey", lambda *a: None)
    clicks = []
    monkeypatch.setattr(generic_mod.pyautogui, "click", lambda x, y: clicks.append((x, y)))
    t = GenericTarget("Cursor")  # no input_click
    t.stage_text("hello")
    assert clicks == []


def test_input_click_converts_percentage_to_window_relative_coordinates(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(generic_mod, "get_window_rect", lambda hwnd: (100, 200, 1100, 1200))  # 1000x1000
    monkeypatch.setattr(generic_mod.pyperclip, "copy", lambda text: None)
    monkeypatch.setattr(generic_mod.pyautogui, "hotkey", lambda *a: None)
    clicks = []
    monkeypatch.setattr(generic_mod.pyautogui, "click", lambda x, y: clicks.append((x, y)))
    t = GenericTarget("Cursor", input_click=(0.9, 0.4))
    t.stage_text("hello")
    assert clicks == [(100 + 900, 200 + 400)]


def test_input_click_also_applies_to_press_enter(monkeypatch):
    monkeypatch.setattr(generic_mod, "find_window_by_keyword", lambda kw: 123)
    monkeypatch.setattr(generic_mod, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(generic_mod, "get_window_rect", lambda hwnd: (0, 0, 1000, 1000))
    monkeypatch.setattr(generic_mod.pyautogui, "press", lambda key: None)
    clicks = []
    monkeypatch.setattr(generic_mod.pyautogui, "click", lambda x, y: clicks.append((x, y)))
    t = GenericTarget("Cursor", input_click=(0.5, 0.5))
    t.press_enter()
    assert clicks == [(500, 500)]
