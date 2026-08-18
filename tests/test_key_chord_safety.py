"""
is_valid_key_spec is the only thing standing between a keypad profile
(user-defined, or in principle attacker-influenced via callback_data) and
arbitrary keystrokes on the desktop. Chords widen what's sendable for real
per-app shortcuts (Cursor's accept/reject, Ctrl+S) — this file is about
making sure that widening didn't also open the door to anything dangerous.
"""
from tether.targets.claude_desktop import ClaudeDesktopTarget


def test_single_allowed_keys_still_valid():
    for key in ClaudeDesktopTarget.ALLOWED_KEYS:
        assert ClaudeDesktopTarget.is_valid_key_spec(key)


def test_useful_chords_are_allowed():
    for chord in ["ctrl+c", "ctrl+v", "ctrl+s", "ctrl+z", "shift+tab", "ctrl+a", "ctrl+f1"]:
        assert ClaudeDesktopTarget.is_valid_key_spec(chord), f"{chord!r} should be allowed"


def test_alt_is_never_a_safe_modifier():
    """alt+anything can leave the target app entirely (alt+tab switches
    focus, alt+space opens the window menu, alt+enter toggles fullscreen in
    many apps) — excluded as a modifier outright, not per dangerous key."""
    for base in ClaudeDesktopTarget.SAFE_CHORD_BASE_KEYS:
        assert not ClaudeDesktopTarget.is_valid_key_spec(f"alt+{base}"), f"alt+{base} should be rejected"


def test_dangerous_combinations_rejected():
    dangerous = [
        "win", "winleft", "winright",       # opens Start menu / OS shortcuts
        "alt+f4",                            # closes the window
        "ctrl+alt+delete",                   # OS-reserved anyway, but must not even try
        "alt+tab",                           # switches focus away from the target entirely
        "ctrl+shift+esc",                    # task manager
        "printscreen",
    ]
    for spec in dangerous:
        assert not ClaudeDesktopTarget.is_valid_key_spec(spec), f"{spec!r} should be rejected"


def test_garbage_and_injection_shaped_strings_rejected():
    for spec in ["", "   ", "rm -rf /", "a; shutdown", "1;2", "../../etc/passwd",
                 "+", "++", "ctrl+", "+c", "ctrl+notarealkey", "notarealmod+c"]:
        assert not ClaudeDesktopTarget.is_valid_key_spec(spec), f"{spec!r} should be rejected"


def test_case_and_whitespace_normalised_before_validation():
    assert ClaudeDesktopTarget.is_valid_key_spec("  CTRL+S  ")
    assert ClaudeDesktopTarget.is_valid_key_spec("Enter")


def test_only_known_modifiers_accepted():
    assert not ClaudeDesktopTarget.is_valid_key_spec("cmd+c")
    assert not ClaudeDesktopTarget.is_valid_key_spec("super+c")


def test_chord_requires_exactly_one_base_key():
    assert not ClaudeDesktopTarget.is_valid_key_spec("ctrl+shift")  # no base key
    assert ClaudeDesktopTarget.is_valid_key_spec("ctrl+shift+s")     # two mods, one base — fine
