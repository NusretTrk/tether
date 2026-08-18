"""
AVD moved off the physical keyboard (replaced by a direct Keypad button)
and into the /keys inline keypad instead, alongside Claude — both
screenshots reachable from the same place now.
"""
from tether.transport.menus import main_reply_keyboard, keypad_menu


def _flatten_reply_labels(markup):
    return [button.text for row in markup.keyboard for button in row]


def _callback_data(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def test_physical_keyboard_has_keypad_not_avd():
    labels = _flatten_reply_labels(main_reply_keyboard(lambda k, **kw: k))
    assert "btn_keypad" in labels
    assert "btn_screen_avd" not in labels
    assert "btn_screen_claude" in labels  # Claude screenshot stays direct


def test_keypad_menu_offers_both_screenshots():
    data = _callback_data(keypad_menu(lambda k, **kw: k))
    assert "screen:claude" in data
    assert "screen:avd" in data
