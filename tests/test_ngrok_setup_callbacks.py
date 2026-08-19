"""
The confirm/save step (callbacks.py's "ngroksetup" category) is the one
place a captured value actually gets written to disk - exercised here
end to end through handle_callback, the same real dispatcher every
inline button goes through, not the ngrok_setup module in isolation.
"""
import asyncio
from dataclasses import dataclass, field

import tether.config as config_mod
from tether.transport import callbacks

CHAT_ID = 55


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answered = False
        self.edits = []
        self.message = type("M", (), {"message_id": 9})()

    async def answer(self, *a, **kw):
        self.answered = True

    async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
        self.edits.append(text)


class FakeCallbackUpdate:
    def __init__(self, data):
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery(data)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)


@dataclass
class FakeSettings:
    language: str = "en"
    mini_app_ngrok_domain: str = ""
    saved: list = field(default_factory=list)

    def save(self):
        self.saved.append(self.mini_app_ngrok_domain)


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
    staged_ngrok_token: str | None = None
    staged_ngrok_domain: str | None = None
    pending_ngrok_token_since: float | None = None
    pending_ngrok_domain_since: float | None = None
    event_loop: object = None


class FakeContext:
    def __init__(self, state=None):
        self.args = []
        self.bot = FakeBot()
        self.bot_data = {"state": state or FakeState()}


def test_confirming_a_staged_token_writes_it_and_updates_live_secrets(monkeypatch):
    written = {}

    def fake_set_env_var(key, value):
        written[key] = value
        return True

    monkeypatch.setattr(config_mod, "set_env_var", fake_set_env_var)

    state = FakeState(staged_ngrok_token="brand-new-token")
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:confirm:token")

    asyncio.run(callbacks.handle_callback(update, context))

    assert written == {"NGROK_AUTHTOKEN": "brand-new-token"}
    assert state.config.secrets.ngrok_authtoken == "brand-new-token"  # live immediately, no restart
    assert state.staged_ngrok_token is None
    assert any("saved and active" in e for e in update.callback_query.edits)


def test_confirming_a_token_that_fails_to_verify_reports_failure_not_success(monkeypatch):
    monkeypatch.setattr(config_mod, "set_env_var", lambda key, value: False)

    state = FakeState(staged_ngrok_token="brand-new-token")
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:confirm:token")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.config.secrets.ngrok_authtoken is None  # never applied in memory either
    assert any("Couldn't verify" in e for e in update.callback_query.edits)


def test_confirming_with_nothing_staged_is_treated_as_cancelled(monkeypatch):
    monkeypatch.setattr(config_mod, "set_env_var", lambda *a: (_ for _ in ()).throw(AssertionError("must not write")))

    state = FakeState(staged_ngrok_token=None)
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:confirm:token")

    asyncio.run(callbacks.handle_callback(update, context))
    assert any("Cancelled" in e for e in update.callback_query.edits)


def test_confirm_cancel_discards_staged_token_without_writing(monkeypatch):
    monkeypatch.setattr(config_mod, "set_env_var", lambda *a: (_ for _ in ()).throw(AssertionError("must not write")))

    state = FakeState(staged_ngrok_token="should-not-be-saved")
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:confirm_cancel:token")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.staged_ngrok_token is None


def test_confirming_a_staged_domain_saves_it_to_settings():
    state = FakeState(staged_ngrok_domain="myname.ngrok-free.app")
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:confirm:domain")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.config.settings.mini_app_ngrok_domain == "myname.ngrok-free.app"
    assert state.config.settings.saved == ["myname.ngrok-free.app"]
    assert state.staged_ngrok_domain is None
    assert any("myname.ngrok-free.app" in e for e in update.callback_query.edits)


def test_ngroksetup_menu_shows_current_status():
    state = FakeState()
    state.config.secrets.ngrok_authtoken = "already-set"
    state.config.settings.mini_app_ngrok_domain = "already.ngrok-free.app"
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:menu")

    asyncio.run(callbacks.handle_callback(update, context))
    assert any("static domain" in e for e in update.callback_query.edits)


def test_ngroksetup_token_button_starts_capture():
    state = FakeState()
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:token")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.pending_ngrok_token_since is not None
    assert len(context.bot.sent) == 1


def test_ngroksetup_domain_button_starts_capture():
    state = FakeState()
    context = FakeContext(state)
    update = FakeCallbackUpdate("ngroksetup:domain")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.pending_ngrok_domain_since is not None
    assert len(context.bot.sent) == 1


def test_turning_mini_app_on_requires_both_domain_and_token(monkeypatch):
    """Regression guard: the on/off toggle used to only check the domain -
    turning the Mini App on with a domain set but no token would have
    tried to start a tunnel destined to fail with no way to authenticate."""
    state = FakeState()
    state.config.settings.mini_app_ngrok_domain = "set.ngrok-free.app"
    state.config.secrets.ngrok_authtoken = None  # token still missing
    context = FakeContext(state)
    update = FakeCallbackUpdate("miniapp:set:on")

    called = []
    monkeypatch.setattr(
        "tether.miniapp.lifecycle.apply_mini_app_state",
        lambda *a: called.append(a),
    )

    asyncio.run(callbacks.handle_callback(update, context))

    assert called == []  # never even attempted to start
    assert any("Configure ngrok" in e for e in update.callback_query.edits)
