"""
Two politeness fixes that are really correctness fixes.

Focus: anything that types has to steal foreground focus first. Doing that
while someone is mid-sentence sends their keystrokes somewhere unintended.

Clipboard: pasting destroys whatever the user had copied. They find out
when their next Ctrl+V produces a message from their phone.
"""
import pytest

from tether.platform.capabilities import CAPABILITIES
from tether.platform.presence import is_user_active

pytestmark = pytest.mark.skipif(not CAPABILITIES.window_control, reason="Windows input/clipboard APIs")


def test_threshold_of_zero_disables_the_check_entirely():
    """0 must mean "never defer", not "defer always" — a reversed check
    here would make the bot refuse to type at all."""
    assert is_user_active(0) is False
    assert is_user_active(-1) is False


def test_idle_seconds_is_a_sane_positive_number():
    from tether.platform.presence import idle_seconds
    idle = idle_seconds()
    assert idle is not None
    assert idle >= 0
    assert idle < 60 * 60 * 24  # not a tick-count wraparound artefact


def test_huge_threshold_reports_active():
    """Any real session has input within the last day."""
    assert is_user_active(60 * 60 * 24) is True


def test_clipboard_text_is_restored_after_the_block():
    import pyperclip
    from tether.platform.window import preserve_clipboard

    pyperclip.copy("user's own content")
    with preserve_clipboard(True):
        pyperclip.copy("what the bot pasted")
        assert pyperclip.paste() == "what the bot pasted"
    assert pyperclip.paste() == "user's own content"


def test_preserve_can_be_disabled():
    import pyperclip
    from tether.platform.window import preserve_clipboard

    pyperclip.copy("original")
    with preserve_clipboard(False):
        pyperclip.copy("replacement")
    assert pyperclip.paste() == "replacement"


def test_restore_failure_does_not_mask_an_exception_from_the_block():
    from tether.platform.window import preserve_clipboard

    with pytest.raises(ValueError, match="inner"):
        with preserve_clipboard(True):
            raise ValueError("inner")


def test_empty_clipboard_does_not_crash_preserve():
    import pyperclip
    from tether.platform.window import preserve_clipboard

    pyperclip.copy("")
    with preserve_clipboard(True):
        pyperclip.copy("something")
    # no assertion on content — the point is it didn't raise
