"""
A key in ALLOWED_KEYS with no button in the keypad UI is a dead feature -
it can be sent, but nobody can trigger it. That gap (4, 5, a, space,
backspace, left, right were all missing buttons) is what this locks in.
"""
import re

from tether.targets.claude_desktop import ClaudeDesktopTarget
from tether.transport.menus import keypad_menu


def _callback_keys(markup) -> set[str]:
    keys = set()
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data and button.callback_data.startswith("key:"):
                keys.add(button.callback_data.split(":", 1)[1])
    return keys


def _identity(key: str, **kwargs) -> str:
    return key  # stand-in translator, only used as a callable here


def test_every_allowed_key_has_a_button():
    markup = keypad_menu(lambda k, **kw: k)
    present = _callback_keys(markup)
    missing = ClaudeDesktopTarget.ALLOWED_KEYS - present
    assert not missing, f"these keys can be sent but have no button: {missing}"


def test_shift_tab_chord_present():
    markup = keypad_menu(lambda k, **kw: k)
    assert "shift+tab" in _callback_keys(markup)


def test_custom_keys_appended_as_extra_buttons():
    markup = keypad_menu(lambda k, **kw: k, custom_keys={"My Macro": "f5"})
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "My Macro" in labels


def test_custom_key_callback_data_matches_configured_key():
    markup = keypad_menu(lambda k, **kw: k, custom_keys={"My Macro": "f5"})
    found = None
    for row in markup.inline_keyboard:
        for b in row:
            if b.text == "My Macro":
                found = b.callback_data
    assert found == "key:f5"


def test_no_custom_keys_does_not_crash():
    keypad_menu(lambda k, **kw: k, custom_keys=None)
    keypad_menu(lambda k, **kw: k, custom_keys={})
