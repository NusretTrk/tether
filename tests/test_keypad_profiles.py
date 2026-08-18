"""
Named keypad profiles let a user target a different app (Cursor, a
terminal, Antigravity) with its own button set and window, entirely
through config.yaml — no code changes needed per app.
"""
from tether.transport.menus import profile_keypad_menu, profile_list_menu


def _callback_data(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_profile_keypad_renders_two_buttons_per_row():
    keys = {"Accept": "tab", "Reject": "escape", "Save": "ctrl+s"}
    markup = profile_keypad_menu(lambda k, **kw: k, "cursor", keys)
    # 3 keys -> 2 rows of buttons (2 + 1) plus the back row
    button_rows = markup.inline_keyboard[:-1]
    assert len(button_rows[0]) == 2
    assert len(button_rows[1]) == 1


def test_profile_keypad_callback_data_encodes_profile_and_key():
    markup = profile_keypad_menu(lambda k, **kw: k, "cursor", {"Accept": "tab"})
    data = _callback_data(markup)
    assert "pkey:cursor:tab" in data


def test_profile_list_always_offers_default_claude_first():
    markup = profile_list_menu(lambda k, **kw: k, ["cursor", "terminal"])
    data = _callback_data(markup)
    assert data[0] == "menu:keypad"
    assert "pkeymenu:cursor" in data
    assert "pkeymenu:terminal" in data


def test_empty_profile_keys_does_not_crash():
    profile_keypad_menu(lambda k, **kw: k, "empty", {})


def test_chord_key_in_profile_survives_into_callback_data():
    """A profile defining Ctrl+S must produce exactly that in callback_data,
    not something mangled by the colon-based callback_data scheme."""
    markup = profile_keypad_menu(lambda k, **kw: k, "cursor", {"Save": "ctrl+s"})
    data = _callback_data(markup)
    assert "pkey:cursor:ctrl+s" in data
