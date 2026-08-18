"""
Without an ignore list, the activity watcher reports the session tether is
itself running inside of as "finished" every time the controlling agent
completes a reply - pure noise, verified live (this is what the user saw
as a stream of unexplained "Telegram PC control bot..." notifications).
"""
from dataclasses import dataclass

from tether.monitors.activity import ActivityWatcher


@dataclass
class FakeSession:
    name: str
    running: bool


class FakeTarget:
    def __init__(self):
        self.sessions: list[FakeSession] = []

    def list_sessions(self):
        return self.sessions


def test_ignored_session_never_reported_even_when_it_finishes():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["Telegram PC control"])

    target.sessions = [FakeSession("Telegram PC control bot with window capture", True)]
    assert watcher.poll() == []

    target.sessions = [FakeSession("Telegram PC control bot with window capture", False)]
    assert watcher.poll() == [], "ignored session was reported as finished"


def test_non_ignored_session_still_reported():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["Telegram PC control"])

    target.sessions = [FakeSession("Some other project", True)]
    watcher.poll()
    target.sessions = [FakeSession("Some other project", False)]
    assert watcher.poll() == ["Some other project"]


def test_ignore_match_is_case_insensitive():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["telegram pc control"])

    target.sessions = [FakeSession("TELEGRAM PC CONTROL bot", True)]
    watcher.poll()
    target.sessions = [FakeSession("TELEGRAM PC CONTROL bot", False)]
    assert watcher.poll() == []


def test_empty_ignore_list_reports_everything():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=[])

    target.sessions = [FakeSession("anything", True)]
    watcher.poll()
    target.sessions = [FakeSession("anything", False)]
    assert watcher.poll() == ["anything"]


def test_default_ignore_list_covers_tethers_own_session_name():
    """The exact session name observed live in this project."""
    from tether.config import Settings
    defaults = Settings().activity_ignore_substrings
    real_name = "Telegram PC control bot with window capture".lower()
    assert any(p.lower() in real_name for p in defaults)
