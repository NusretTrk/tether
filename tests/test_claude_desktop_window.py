"""
ClaudeDesktopTarget._hwnd() must actually use app_path_filter for
window-finding, not just process-killing (list_app_processes/stop_app
already had this protection - Claude Desktop and the separate Claude
Code CLI share the exact same claude.exe name). Without it, a browser
tab with "Claude" in its title can outrank the real app purely on
screen area and silently become the target for every click/paste/OCR
call - confirmed live as the actual cause of "can't type into Claude
when a browser tab is open".
"""
from tether.targets import claude_desktop as cd


def test_hwnd_passes_app_path_filter_to_window_lookup(monkeypatch):
    captured = {}

    def fake_find(kw, path_contains=None):
        captured["kw"] = kw
        captured["path_contains"] = path_contains
        return 123

    monkeypatch.setattr(cd, "find_window_by_keyword", fake_find)
    target = cd.ClaudeDesktopTarget("Claude", app_path_filter="WindowsApps")

    assert target._hwnd() == 123
    assert captured == {"kw": "Claude", "path_contains": "WindowsApps"}


def test_hwnd_uses_the_default_path_filter_when_none_given(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cd, "find_window_by_keyword",
        lambda kw, path_contains=None: captured.setdefault("path_contains", path_contains) or 123,
    )
    cd.ClaudeDesktopTarget("Claude")._hwnd()
    assert captured["path_contains"] == cd.ClaudeDesktopTarget.DEFAULT_APP_PATH_FILTER
