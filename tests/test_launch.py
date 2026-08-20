"""
/launch with no args starts Claude Desktop (unchanged). /launch <name> is
the user's own "just type a command and the program opens" ask - reuses
keypad_profiles (the same config /target and /keys already read) rather
than a new parallel "apps I can open" list, and refuses cleanly rather
than guessing when a profile has no launch_command set.
"""
import asyncio
from dataclasses import dataclass, field

from tether.transport import handlers

CHAT_ID = 88


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append(txt)


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()


class FakeClaudeTarget:
    def __init__(self, running=False, launch_ok=True, window_appears=True):
        self.running = running
        self.launch_ok = launch_ok
        self.window_appears = window_appears
        self.launch_calls = 0

    def is_app_running(self):
        return self.running

    def launch_app(self):
        self.launch_calls += 1
        return self.launch_ok

    def wait_for_window(self, timeout):
        return self.window_appears


@dataclass
class FakeSettings:
    language: str = "en"
    keypad_profiles: dict = field(default_factory=dict)


@dataclass
class FakeSecrets:
    chat_id: int = CHAT_ID


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    target: FakeClaudeTarget = field(default_factory=FakeClaudeTarget)
    config: FakeConfig = field(default_factory=FakeConfig)


class FakeContext:
    def __init__(self, args, state=None):
        self.args = args
        self.bot_data = {"state": state or FakeState()}


def test_no_args_launches_claude_desktop_unchanged():
    target = FakeClaudeTarget(running=False)
    update, context = FakeUpdate(), FakeContext([], FakeState(target=target))

    asyncio.run(handlers.cmd_launch(update, context))

    assert target.launch_calls == 1
    assert "started" in update.message.replies[0].lower()


def test_no_args_reports_already_running_without_relaunching():
    target = FakeClaudeTarget(running=True)
    update, context = FakeUpdate(), FakeContext([], FakeState(target=target))

    asyncio.run(handlers.cmd_launch(update, context))

    assert target.launch_calls == 0
    assert "already running" in update.message.replies[0].lower()


def test_named_profile_without_launch_command_refuses_cleanly(monkeypatch):
    state = FakeState()
    state.config.settings.keypad_profiles = {"antigravity": {"window_keyword": "Antigravity"}}
    update, context = FakeUpdate(), FakeContext(["antigravity"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert "launch_command" in update.message.replies[0]
    assert "antigravity" in update.message.replies[0]


def test_named_profile_with_unknown_name_refuses_cleanly():
    state = FakeState()  # no profiles configured at all
    update, context = FakeUpdate(), FakeContext(["nonexistent"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert "nonexistent" in update.message.replies[0]


def test_named_profile_refuses_to_launch_a_second_copy(monkeypatch):
    monkeypatch.setattr("tether.platform.window.find_window_by_keyword", lambda kw, path=None: 123)
    launched = []
    monkeypatch.setattr("tether.platform.process.launch", lambda cmd: launched.append(cmd) or True)

    state = FakeState()
    state.config.settings.keypad_profiles = {
        "antigravity": {"window_keyword": "Antigravity", "launch_command": "C:\\Antigravity.exe"},
    }
    update, context = FakeUpdate(), FakeContext(["antigravity"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert launched == []
    assert "already running" in update.message.replies[0].lower()
    assert "antigravity" in update.message.replies[0].lower()


def test_named_profile_launches_and_confirms_window_appeared(monkeypatch):
    monkeypatch.setattr("tether.platform.window.find_window_by_keyword", lambda kw, path=None: None)
    launched = []
    monkeypatch.setattr("tether.platform.process.launch", lambda cmd: launched.append(cmd) or True)
    monkeypatch.setattr("tether.platform.window.wait_for_window_by_keyword", lambda kw, path, timeout: True)

    state = FakeState()
    state.config.settings.keypad_profiles = {
        "antigravity": {
            "window_keyword": "Antigravity", "window_path_filter": "Programs",
            "launch_command": "C:\\Antigravity.exe",
        },
    }
    update, context = FakeUpdate(), FakeContext(["antigravity"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert launched == ["C:\\Antigravity.exe"]
    assert "antigravity" in update.message.replies[0].lower()
    assert "started" in update.message.replies[0].lower()


def test_named_profile_reports_launch_failure_without_crashing(monkeypatch):
    monkeypatch.setattr("tether.platform.window.find_window_by_keyword", lambda kw, path=None: None)
    monkeypatch.setattr("tether.platform.process.launch", lambda cmd: False)

    state = FakeState()
    state.config.settings.keypad_profiles = {
        "antigravity": {"window_keyword": "Antigravity", "launch_command": "C:\\Antigravity.exe"},
    }
    update, context = FakeUpdate(), FakeContext(["antigravity"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert "couldn't launch" in update.message.replies[0].lower()


def test_named_profile_with_no_window_keyword_skips_confirmation(monkeypatch):
    launched = []
    monkeypatch.setattr("tether.platform.process.launch", lambda cmd: launched.append(cmd) or True)

    state = FakeState()
    state.config.settings.keypad_profiles = {"scratch": {"launch_command": "notepad.exe"}}
    update, context = FakeUpdate(), FakeContext(["scratch"], state)

    asyncio.run(handlers.cmd_launch(update, context))

    assert launched == ["notepad.exe"]
    assert "no window appeared" in update.message.replies[0].lower()
