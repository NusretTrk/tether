"""
A photo sent with a caption must land as one message — image and text
together — not require two separate sends. stage_photo pastes the image
first (becomes an attachment chip), then pastes the caption right after
without re-clicking, since focus stays in the composer.
"""
import io

import pytest

from tether.platform.capabilities import CAPABILITIES

pytestmark = pytest.mark.skipif(not CAPABILITIES.window_control, reason="Windows-only paste mechanism")


def _make_test_image_bytes():
    from PIL import Image
    img = Image.new("RGB", (4, 4), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_caption_triggers_a_second_clipboard_paste(monkeypatch):
    from tether.targets import claude_desktop as cd

    hotkey_calls = []
    monkeypatch.setattr(cd.pyautogui, "hotkey", lambda *a, **k: hotkey_calls.append(a))
    monkeypatch.setattr(cd.pyautogui, "click", lambda *a, **k: None)
    monkeypatch.setattr(cd.pyautogui, "press", lambda *a, **k: None)

    copied = []
    monkeypatch.setattr(cd.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr(cd, "set_clipboard_image", lambda b: True)
    monkeypatch.setattr(cd, "find_input_box_anchor", lambda img: None)

    # before/after pixel compare must differ so the image-paste is "detected"
    calls = {"n": 0}
    class FakeImg:
        def __init__(self, n):
            self.n = n
            self.height = 100
        def crop(self, box):
            return self
        def tobytes(self):
            calls["n"] += 1
            return bytes([calls["n"] % 256])  # different every call

    monkeypatch.setattr(cd, "capture_window", lambda hwnd: FakeImg(calls["n"]))
    monkeypatch.setattr(cd, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(cd, "find_window_by_keyword", lambda kw, path_contains=None: 12345)
    monkeypatch.setattr(cd, "get_window_rect", lambda hwnd: (0, 0, 800, 600))

    target = cd.ClaudeDesktopTarget("Claude")
    result = target.stage_photo(_make_test_image_bytes(), caption="hello world")

    assert result.ok
    assert "hello world" in copied, "caption was never put on the clipboard"
    assert len(hotkey_calls) == 2, f"expected 2 pastes (image, then caption), got {len(hotkey_calls)}"


def test_no_caption_means_a_single_paste(monkeypatch):
    from tether.targets import claude_desktop as cd

    hotkey_calls = []
    monkeypatch.setattr(cd.pyautogui, "hotkey", lambda *a, **k: hotkey_calls.append(a))
    monkeypatch.setattr(cd.pyautogui, "click", lambda *a, **k: None)
    monkeypatch.setattr(cd.pyperclip, "copy", lambda text: None)
    monkeypatch.setattr(cd, "set_clipboard_image", lambda b: True)
    monkeypatch.setattr(cd, "find_input_box_anchor", lambda img: None)

    calls = {"n": 0}
    class FakeImg:
        height = 100
        def crop(self, box):
            return self
        def tobytes(self):
            calls["n"] += 1
            return bytes([calls["n"] % 256])

    monkeypatch.setattr(cd, "capture_window", lambda hwnd: FakeImg())
    monkeypatch.setattr(cd, "focus_window", lambda hwnd: True)
    monkeypatch.setattr(cd, "find_window_by_keyword", lambda kw, path_contains=None: 12345)
    monkeypatch.setattr(cd, "get_window_rect", lambda hwnd: (0, 0, 800, 600))

    target = cd.ClaudeDesktopTarget("Claude")
    result = target.stage_photo(_make_test_image_bytes())

    assert result.ok
    assert len(hotkey_calls) == 1, "no caption given, should only paste the image once"
