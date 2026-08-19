"""
Without an ignore list, the activity watcher reports the session tether is
itself running inside of as "finished"/"started" every time the controlling
agent completes or starts a reply - pure noise, verified live (this is what
the user saw as a stream of unexplained "Telegram PC control bot..."
notifications).
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
    assert watcher.poll() == ([], [])

    target.sessions = [FakeSession("Telegram PC control bot with window capture", False)]
    assert watcher.poll() == ([], []), "ignored session was reported as finished"


def test_non_ignored_session_still_reported():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["Telegram PC control"])

    target.sessions = [FakeSession("Some other project", True)]
    watcher.poll()
    target.sessions = [FakeSession("Some other project", False)]
    assert watcher.poll() == ([], ["Some other project"])


def test_ignore_match_is_case_insensitive():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["telegram pc control"])

    target.sessions = [FakeSession("TELEGRAM PC CONTROL bot", True)]
    watcher.poll()
    target.sessions = [FakeSession("TELEGRAM PC CONTROL bot", False)]
    assert watcher.poll() == ([], [])


def test_empty_ignore_list_reports_everything():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=[])

    target.sessions = [FakeSession("anything", True)]
    watcher.poll()
    target.sessions = [FakeSession("anything", False)]
    assert watcher.poll() == ([], ["anything"])


def test_default_ignore_list_covers_tethers_own_session_name():
    """The exact session name observed live in this project."""
    from tether.config import Settings
    defaults = Settings().activity_ignore_substrings
    real_name = "Telegram PC control bot with window capture".lower()
    assert any(p.lower() in real_name for p in defaults)


# --- started transitions -------------------------------------------------

def test_session_already_running_on_first_poll_is_not_reported_as_started():
    """Otherwise every session already running when tether launches would
    get reported as "just started"."""
    target = FakeTarget()
    watcher = ActivityWatcher(target)
    target.sessions = [FakeSession("Some project", True)]
    assert watcher.poll() == ([], [])


def test_idle_to_running_is_reported_as_started():
    target = FakeTarget()
    watcher = ActivityWatcher(target)

    target.sessions = [FakeSession("Some project", False)]
    watcher.poll()
    target.sessions = [FakeSession("Some project", True)]
    assert watcher.poll() == (["Some project"], [])


def test_ignored_session_never_reported_as_started():
    target = FakeTarget()
    watcher = ActivityWatcher(target, ignore_substrings=["Telegram PC control"])

    target.sessions = [FakeSession("Telegram PC control bot with window capture", False)]
    watcher.poll()
    target.sessions = [FakeSession("Telegram PC control bot with window capture", True)]
    assert watcher.poll() == ([], [])


def test_started_and_finished_reported_together_in_one_poll():
    target = FakeTarget()
    watcher = ActivityWatcher(target)

    target.sessions = [FakeSession("A", True), FakeSession("B", False)]
    watcher.poll()
    target.sessions = [FakeSession("A", False), FakeSession("B", True)]
    started, finished = watcher.poll()
    assert started == ["B"]
    assert finished == ["A"]
