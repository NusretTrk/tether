"""
settings_menu() used to build its Confirm/Mini App button labels by
calling a templated i18n key with no params and relying on the
.format() KeyError fallback (returns the raw, unformatted template) plus
a string .split() to fake a label - functionally harmless (the fallback
happened to produce the right text) but noisy (a real warning logged on
every /settings open) and fragile (depended on exactly where the
placeholder sits in the sentence). Regression guard: opening the
settings menu must not log an i18n mismatch warning.
"""
import logging

from tether.i18n import make_translator
from tether.transport import menus


def test_settings_menu_does_not_trigger_an_i18n_mismatch_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="tether.i18n"):
        menus.settings_menu(make_translator("en"))
    assert not any("template/params mismatch" in r.message for r in caplog.records)


def test_settings_menu_button_labels_are_clean_not_raw_templates():
    _t = make_translator("en")
    markup = menus.settings_menu(_t)
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Confirm" in l and "{state}" not in l for l in labels)
    assert any("Mini App" in l and "{state}" not in l for l in labels)
