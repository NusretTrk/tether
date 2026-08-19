"""
/miniapp is the quick-control path the user asked for explicitly: turn
the Mini App on/off without navigating through /settings menus, and be
sure "off" actually stops the tunnel from being reachable rather than
just hiding the button.
"""
import asyncio
from dataclasses import dataclass, field

from tether.transport import handlers

CHAT_ID = 77


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append((txt, kwargs.get("reply_markup")))


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()


@dataclass
class FakeSettings:
    language: str = "en"
    mini_app_enabled: bool = False
    mini_app_ngrok_domain: str = ""
    saved: list = field(default_factory=list)

    def save(self):
        self.saved.append(self.mini_app_enabled)


@dataclass
class FakeSecrets:
    chat_id: int = CHAT_ID
    ngrok_authtoken: str | None = None


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    miniapp_server: object = None
    event_loop: object = None


class FakeContext:
    def __init__(self, args):
        self.args = args
        self.bot = object()
        self.bot_data = {"state": FakeState()}


def test_no_args_shows_status_without_changing_anything():
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_miniapp(update, context))

    assert len(update.message.replies) == 1
    assert context.bot_data["state"].config.settings.saved == []


def test_on_requires_domain_and_token_configured(monkeypatch):
    called = []
    monkeypatch.setattr("tether.miniapp.lifecycle.apply_mini_app_state", lambda *a: called.append(a))

    update, context = FakeUpdate(), FakeContext(["on"])
    asyncio.run(handlers.cmd_miniapp(update, context))

    assert called == []
    assert context.bot_data["state"].config.settings.mini_app_enabled is False
    text, _ = update.message.replies[0]
    assert "Configure ngrok" in text


def test_on_succeeds_once_domain_and_token_are_set(monkeypatch):
    called = []
    monkeypatch.setattr("tether.miniapp.lifecycle.apply_mini_app_state", lambda *a: called.append(a))

    update, context = FakeUpdate(), FakeContext(["on"])
    state = context.bot_data["state"]
    state.config.settings.mini_app_ngrok_domain = "myname.ngrok-free.app"
    state.config.secrets.ngrok_authtoken = "real-token"

    asyncio.run(handlers.cmd_miniapp(update, context))

    assert state.config.settings.mini_app_enabled is True
    assert len(called) == 1


def test_off_always_succeeds_and_actually_reapplies_lifecycle(monkeypatch):
    """Turning off must go through apply_mini_app_state, not just flip
    the setting - that's what actually kills the server/tunnel rather
    than leaving them running with the button merely hidden."""
    called = []
    monkeypatch.setattr("tether.miniapp.lifecycle.apply_mini_app_state", lambda *a: called.append(a))

    update, context = FakeUpdate(), FakeContext(["off"])
    state = context.bot_data["state"]
    state.config.settings.mini_app_enabled = True

    asyncio.run(handlers.cmd_miniapp(update, context))

    assert state.config.settings.mini_app_enabled is False
    assert len(called) == 1


def test_status_reflects_actually_running_state_not_just_the_setting():
    update, context = FakeUpdate(), FakeContext([])
    state = context.bot_data["state"]
    state.config.settings.mini_app_enabled = True
    state.miniapp_server = None  # enabled in settings, but not actually up

    asyncio.run(handlers.cmd_miniapp(update, context))

    text, _ = update.message.replies[0]
    assert "off" in text.lower()  # reports the real running state, not the flag
