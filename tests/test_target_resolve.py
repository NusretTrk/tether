"""
active_target() decides where a plain text/photo message actually goes -
Claude Desktop by default, or a GenericTarget built from a named
keypad_profiles entry after /target. Wrong here means a message either
silently goes to the wrong app, or a typo'd /target argument crashes
instead of falling back.
"""
from dataclasses import dataclass, field

from tether.targets.generic import GenericTarget
from tether.transport.target_resolve import active_target


class FakeSettings:
    keypad_profiles = {
        "cursor": {"window_keyword": "Cursor", "keys": {}},
        "broken": {"keys": {}},  # no window_keyword
        "antigravity": {"window_keyword": "Antigravity", "input_click": {"x": 0.92, "y": 0.42}},
        "filtered": {"window_keyword": "Cursor", "window_path_filter": "cursor\\Cursor.exe"},
    }
    preserve_user_clipboard = True


class FakeConfig:
    settings = FakeSettings()


CLAUDE_TARGET = object()  # sentinel - identity check, not a real Target


@dataclass
class FakeState:
    target: object = CLAUDE_TARGET
    config: FakeConfig = field(default_factory=FakeConfig)
    active_target_profile: str | None = None


def test_no_profile_selected_returns_claude_target():
    state = FakeState()
    assert active_target(state) is CLAUDE_TARGET


def test_valid_profile_returns_generic_target_with_its_window_keyword():
    state = FakeState(active_target_profile="cursor")
    result = active_target(state)
    assert isinstance(result, GenericTarget)
    assert result.window_keyword == "Cursor"


def test_unknown_profile_name_falls_back_to_claude_target():
    state = FakeState(active_target_profile="does_not_exist")
    assert active_target(state) is CLAUDE_TARGET


def test_profile_without_window_keyword_falls_back_to_claude_target():
    state = FakeState(active_target_profile="broken")
    assert active_target(state) is CLAUDE_TARGET


def test_generic_target_inherits_clipboard_preservation_setting(monkeypatch):
    monkeypatch.setattr(FakeSettings, "preserve_user_clipboard", False)
    state = FakeState(active_target_profile="cursor")
    result = active_target(state)
    assert result.preserve_user_clipboard is False


def test_profile_without_input_click_leaves_it_unset():
    state = FakeState(active_target_profile="cursor")
    assert active_target(state).input_click is None


def test_profile_with_input_click_passes_it_through():
    state = FakeState(active_target_profile="antigravity")
    result = active_target(state)
    assert result.input_click == (0.92, 0.42)


def test_profile_without_window_path_filter_leaves_it_unset():
    state = FakeState(active_target_profile="cursor")
    assert active_target(state).path_filter is None


def test_profile_with_window_path_filter_passes_it_through():
    """window_path_filter closes the same "a bigger browser tab titled
    'Cursor' outranks the real app" bug ClaudeDesktopTarget already
    guards against - must actually reach the constructed GenericTarget,
    not just exist in config.yaml unused."""
    state = FakeState(active_target_profile="filtered")
    result = active_target(state)
    assert result.path_filter == "cursor\\Cursor.exe"
