"""The Mini App menu's "Get browser link" / "Revoke browser link" buttons -
same issue_web_link/revoke_web_link helpers /miniapp link|revoke uses on
the text-command path (test_cmd_miniapp.py), exercised here through the
real inline-keyboard dispatcher instead."""
import asyncio
from dataclasses import dataclass, field

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


@dataclass
class FakeSettings:
    language: str = "en"
    mini_app_enabled: bool = True
    mini_app_ngrok_domain: str = "myname.ngrok-free.app"


@dataclass
class FakeSecrets:
    chat_id: int = CHAT_ID
    ngrok_authtoken: str | None = "real-token"
    bot_password: str | None = None


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    unlocked: bool = True
    web_token_hash: str | None = None


class FakeJobQueue:
    def __init__(self):
        self.scheduled = []

    def run_once(self, callback, when, data=None, name=None):
        self.scheduled.append((callback, when, data, name))


class FakeContext:
    def __init__(self, state=None):
        self.args = []
        self.bot = object()
        self.bot_data = {"state": state or FakeState()}
        self.job_queue = FakeJobQueue()


def test_weblink_button_issues_a_token_and_schedules_self_delete(monkeypatch, tmp_path):
    monkeypatch.setattr("tether.miniapp.webtoken.STATE_DIR", tmp_path)
    monkeypatch.setattr("tether.miniapp.webtoken.TOKEN_PATH", tmp_path / "web_token.json")

    state = FakeState()
    context = FakeContext(state)
    update = FakeCallbackUpdate("miniapp:weblink")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.web_token_hash is not None
    assert any("myname.ngrok-free.app/#t=" in e for e in update.callback_query.edits)
    assert len(context.job_queue.scheduled) == 1
    _, when, data, _ = context.job_queue.scheduled[0]
    assert when == 600
    assert data == 9  # the edited message's own id


def test_weblink_button_without_a_domain_reports_missing_config(monkeypatch, tmp_path):
    monkeypatch.setattr("tether.miniapp.webtoken.STATE_DIR", tmp_path)
    monkeypatch.setattr("tether.miniapp.webtoken.TOKEN_PATH", tmp_path / "web_token.json")

    state = FakeState()
    state.config.settings.mini_app_ngrok_domain = ""
    context = FakeContext(state)
    update = FakeCallbackUpdate("miniapp:weblink")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.web_token_hash is None
    assert context.job_queue.scheduled == []
    assert any("Configure ngrok" in e for e in update.callback_query.edits)


def test_webrevoke_button_clears_the_token(monkeypatch, tmp_path):
    monkeypatch.setattr("tether.miniapp.webtoken.STATE_DIR", tmp_path)
    monkeypatch.setattr("tether.miniapp.webtoken.TOKEN_PATH", tmp_path / "web_token.json")

    state = FakeState(web_token_hash="some-hash")
    context = FakeContext(state)
    update = FakeCallbackUpdate("miniapp:webrevoke")

    asyncio.run(callbacks.handle_callback(update, context))

    assert state.web_token_hash is None
