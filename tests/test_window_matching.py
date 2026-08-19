"""
find_window_by_keyword's largest-area title match had a real, confirmed-
live bug: any window whose TITLE merely contains the keyword competes on
screen area alone, so a maximized browser tab titled "Claude - talk to
Claude" (or "Cursor"/"Antigravity" showing up in a webpage title, a
folder name, anything) can outrank the real app and silently become the
target for every click/paste/OCR call that follows. path_contains closes
this by also requiring the winning window's OWNING PROCESS path to match
- exercised here directly against the real function, mocking only the
thin win32gui/win32process/psapi calls it makes.
"""
import pytest

pytest.importorskip("win32gui", reason="Windows-only")

import win32gui
import win32process

from tether.platform import process as process_mod
from tether.platform import window as window_mod


class FakeWin:
    def __init__(self, hwnd, title, rect, pid):
        self.hwnd = hwnd
        self.title = title
        self.rect = rect  # (left, top, right, bottom)
        self.pid = pid


@pytest.fixture
def fake_windows(monkeypatch):
    """Wires EnumWindows/GetWindowText/GetWindowRect/GetWindowThreadProcessId
    against a list the test controls, and path_for_pid against a simple
    pid->path dict - the exact same primitives find_window_by_keyword
    actually calls, nothing about its own logic mocked away."""
    registry = {"wins": [], "paths": {}}

    def enum_windows(callback, extra):
        for w in registry["wins"]:
            callback(w.hwnd, extra)

    def is_visible(hwnd):
        return True

    def get_text(hwnd):
        return next(w.title for w in registry["wins"] if w.hwnd == hwnd)

    def get_rect(hwnd):
        return next(w.rect for w in registry["wins"] if w.hwnd == hwnd)

    def get_thread_pid(hwnd):
        w = next(w for w in registry["wins"] if w.hwnd == hwnd)
        return (0, w.pid)

    def path_for_pid(pid):
        return registry["paths"].get(pid)

    monkeypatch.setattr(win32gui, "EnumWindows", enum_windows)
    monkeypatch.setattr(win32gui, "IsWindowVisible", is_visible)
    monkeypatch.setattr(win32gui, "GetWindowText", get_text)
    monkeypatch.setattr(win32gui, "GetWindowRect", get_rect)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", get_thread_pid)
    monkeypatch.setattr(process_mod, "path_for_pid", path_for_pid)
    return registry


def _area_rect(w, h):
    return (0, 0, w, h)


def test_plain_title_match_picks_largest_area_no_path_filter(fake_windows):
    fake_windows["wins"] = [
        FakeWin(1, "Claude", _area_rect(400, 300), pid=100),
        FakeWin(2, "Claude - talk to Claude - Google Chrome", _area_rect(1920, 1080), pid=200),
    ]
    # No path filter at all - reproduces the real bug: the bigger browser
    # window wins purely on title+area.
    assert window_mod.find_window_by_keyword("Claude") == 2


def test_path_filter_rejects_the_browser_tab_even_though_it_is_bigger(fake_windows):
    fake_windows["wins"] = [
        FakeWin(1, "Claude", _area_rect(400, 300), pid=100),
        FakeWin(2, "Claude - talk to Claude - Google Chrome", _area_rect(1920, 1080), pid=200),
    ]
    fake_windows["paths"] = {
        100: r"C:\Program Files\WindowsApps\Claude.Desktop_1.0\Claude.exe",
        200: r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    }
    assert window_mod.find_window_by_keyword("Claude", path_contains="WindowsApps") == 1


def test_path_filter_still_picks_largest_among_its_own_matches(fake_windows):
    fake_windows["wins"] = [
        FakeWin(1, "Claude small", _area_rect(400, 300), pid=100),
        FakeWin(2, "Claude big", _area_rect(1200, 900), pid=101),
        FakeWin(3, "Claude - Chrome", _area_rect(1920, 1080), pid=200),
    ]
    fake_windows["paths"] = {
        100: r"C:\WindowsApps\Claude.exe",
        101: r"C:\WindowsApps\Claude.exe",
        200: r"C:\Chrome\chrome.exe",
    }
    assert window_mod.find_window_by_keyword("Claude", path_contains="WindowsApps") == 2


def test_path_filter_matching_nothing_falls_back_to_unfiltered_result(fake_windows):
    """A wrong/stale path_contains value (app installed somewhere the
    configured filter doesn't expect) must not turn a previously-working
    title match into a false "window not found" - it should just behave
    like no filter was given."""
    fake_windows["wins"] = [FakeWin(1, "Cursor", _area_rect(800, 600), pid=100)]
    fake_windows["paths"] = {100: r"C:\Users\me\AppData\Local\Programs\cursor\Cursor.exe"}
    assert window_mod.find_window_by_keyword("Cursor", path_contains="this-does-not-appear-anywhere") == 1


def test_process_whose_path_cannot_be_read_is_excluded_not_crashed_on(fake_windows):
    fake_windows["wins"] = [
        FakeWin(1, "Claude", _area_rect(400, 300), pid=100),
        FakeWin(2, "Claude other", _area_rect(1920, 1080), pid=999),
    ]
    fake_windows["paths"] = {100: r"C:\WindowsApps\Claude.exe"}  # pid 999 has no entry -> None
    assert window_mod.find_window_by_keyword("Claude", path_contains="WindowsApps") == 1


def test_no_title_matches_returns_none(fake_windows):
    fake_windows["wins"] = [FakeWin(1, "Notepad", _area_rect(400, 300), pid=100)]
    assert window_mod.find_window_by_keyword("Claude") is None
    assert window_mod.find_window_by_keyword("Claude", path_contains="WindowsApps") is None


def test_invisible_windows_are_never_matched(fake_windows):
    fake_windows["wins"] = [FakeWin(1, "Claude", _area_rect(400, 300), pid=100)]
    original_visible = win32gui.IsWindowVisible
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(win32gui, "IsWindowVisible", lambda hwnd: False)
        assert window_mod.find_window_by_keyword("Claude") is None
