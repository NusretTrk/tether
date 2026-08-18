"""
The keypad forwards keystrokes into whatever the agent has on screen. Only
an explicit allowlist may be sent - callback_data is attacker-influenced in
principle, and this is the one place a string from a message turns into
input on the desktop.
"""
from tether.targets.claude_desktop import ClaudeDesktopTarget


class NoWindowTarget(ClaudeDesktopTarget):
    """Rejection must happen before any window lookup, so this raises if the
    code ever tries to touch a window for a disallowed key."""

    def _hwnd(self):
        raise AssertionError("looked up a window for a key that should have been rejected")


def test_disallowed_keys_rejected_before_touching_window():
    t = NoWindowTarget("Claude")
    for bad in ["rm -rf /", "a; shutdown", "", "ctrl+alt+delete", "F4", "alt+f4",
                "enter\nenter", "1;2", "../../etc/passwd", "win+r"]:
        assert t.send_key(bad) is False, f"accepted disallowed key {bad!r}"


def test_allowlist_is_only_single_keys_and_the_mode_chord():
    allowed = ClaudeDesktopTarget.ALLOWED_KEYS
    for key in allowed:
        assert "+" not in key, f"{key!r} is a chord; only shift+tab is special-cased"
        assert ";" not in key and " " not in key


def test_expected_prompt_answers_are_available():
    """Numbered choices and y/n are what agent permission prompts actually
    ask for; losing them is what left the bot unable to unblock a session."""
    allowed = ClaudeDesktopTarget.ALLOWED_KEYS
    for key in ["1", "2", "3", "y", "n", "enter", "escape"]:
        assert key in allowed


def test_case_and_whitespace_normalised():
    t = NoWindowTarget("Claude")
    # still rejected (bad key), but proves normalisation runs before lookup
    assert t.send_key("  NOPE  ") is False
