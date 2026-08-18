"""Session/dialog parsing logic tests, using synthetic named-control lists
shaped like what was observed live against Claude Desktop's sidebar — no
live UIA/window dependency, so this runs on any machine."""
from tether.platform.uia import detect_dialogs, parse_sessions

REAL_SIDEBAR_SAMPLE = [
    ("ButtonControl", "Minimize"),
    ("ButtonControl", "Maximize"),
    ("ButtonControl", "Restore"),
    ("ButtonControl", "Close"),
    ("ButtonControl", "Menu"),
    ("ButtonControl", "Collapse sidebar"),
    ("ButtonControl", "Search"),
    ("ButtonControl", "New"),
    ("ButtonControl", "Claude Tele Control"),
    ("ButtonControl", "New session in Claude Tele Control"),
    ("ButtonControl", "Filter"),
    ("ButtonControl", "Running Telegram PC control bot with window capture"),
    ("TextControl", "Telegram PC control bot with window capture"),
    ("ButtonControl", "More options for Telegram PC control bot with window capture"),
    ("ButtonControl", "Idle HalallO architecture audit and execution plan"),
    ("TextControl", "HalallO architecture audit and execution plan"),
    ("ButtonControl", "More options for HalallO architecture audit and execution plan"),
]


def test_parses_running_and_idle_sessions():
    sessions = parse_sessions(REAL_SIDEBAR_SAMPLE)
    names = {n: r for n, r in sessions}
    assert names["Telegram PC control bot with window capture"] is True
    assert names["HalallO architecture audit and execution plan"] is False


def test_excludes_chrome_and_sub_buttons():
    sessions = parse_sessions(REAL_SIDEBAR_SAMPLE)
    names = [n for n, _ in sessions]
    assert "Minimize" not in names
    assert not any(n.startswith("More options for") for n in names)
    assert not any(n.startswith("New session in") for n in names)


def test_empty_input_yields_empty_list():
    assert parse_sessions([]) == []


def test_dialog_detected_from_trigger_keyword():
    controls = [
        ("TextControl", "For your security, sign in again to keep using Claude."),
        ("ButtonControl", "Sign in again"),
        ("ButtonControl", "Minimize"),
    ]
    dialogs = detect_dialogs(controls)
    assert len(dialogs) == 1
    name, buttons = dialogs[0]
    assert "sign in" in name.lower()
    assert "Sign in again" in buttons
    assert "Minimize" not in buttons


def test_no_dialog_when_no_trigger_keywords():
    controls = [
        ("TextControl", "Telegram PC control bot with window capture"),
        ("ButtonControl", "Idle Telegram PC control bot with window capture"),
    ]
    assert detect_dialogs(controls) == []
