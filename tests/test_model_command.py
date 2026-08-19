"""
/model has to behave two different ways depending on what /target is
currently pointed at: the original fixed-list Claude Desktop behavior is
untouched, and a /target-routed app goes through the new dynamic
OCR-based list_models/set_model path on GenericTarget instead. These
mock active_target() itself (already tested in test_target_resolve.py)
to check cmd_model routes to the right one.
"""
import asyncio
from dataclasses import dataclass, field

from tether.transport import handlers

CHAT_ID = 55


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


class FakeStatus:
    model = "Sonnet"
    effort = "Medium"


class FakeClaudeTarget:
    def read_status(self):
        return FakeStatus()

    def set_model(self, name):
        return "Sonnet" if name.lower() == "sonnet" else None


class FakeSettings:
    language = "en"


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    target: FakeClaudeTarget = field(default_factory=FakeClaudeTarget)
    config: FakeConfig = field(default_factory=FakeConfig)


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.bot_data = {"state": FakeState()}


# --- Claude Desktop path (active_target returns state.target) ------------

def test_claude_desktop_status_when_no_target_selected(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: state.target)
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_model(update, context))
    assert "Sonnet" in update.message.replies[0]


def test_claude_desktop_set_model_unchanged(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: state.target)
    update, context = FakeUpdate(), FakeContext(["sonnet"])
    asyncio.run(handlers.cmd_model(update, context))
    assert "Sonnet" in update.message.replies[0]


def test_claude_desktop_unknown_model_unchanged(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: state.target)
    update, context = FakeUpdate(), FakeContext(["not-a-real-model"])
    asyncio.run(handlers.cmd_model(update, context))
    assert "not-a-real-model" in update.message.replies[0]


# --- /target-routed generic app path --------------------------------------

class FakeGenericTarget:
    model_click = (0.9, 0.4)

    def list_models(self):
        return ["Gemini 3.5 Flash", "Gemini 3.1 Pro"]

    def set_model(self, name):
        return "Gemini 3.1 Pro" if "3.1" in name else None


def test_generic_target_no_args_lists_models(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: FakeGenericTarget())
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_model(update, context))
    assert "Gemini 3.5 Flash" in update.message.replies[0]
    assert "Gemini 3.1 Pro" in update.message.replies[0]


def test_generic_target_set_model_success(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: FakeGenericTarget())
    update, context = FakeUpdate(), FakeContext(["3.1"])
    asyncio.run(handlers.cmd_model(update, context))
    assert "Gemini 3.1 Pro" in update.message.replies[0]


def test_generic_target_set_model_no_match(monkeypatch):
    monkeypatch.setattr(handlers, "active_target", lambda state: FakeGenericTarget())
    update, context = FakeUpdate(), FakeContext(["nonexistent-model"])
    asyncio.run(handlers.cmd_model(update, context))
    assert "nonexistent-model" in update.message.replies[0]


def test_generic_target_without_model_click_reports_not_configured(monkeypatch):
    class NoModelClickTarget:
        model_click = None

    monkeypatch.setattr(handlers, "active_target", lambda state: NoModelClickTarget())
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_model(update, context))
    assert update.message.replies
    assert "model_click" in update.message.replies[0] or "not" in update.message.replies[0].lower()


def test_generic_target_empty_model_list_reports_failure(monkeypatch):
    class EmptyListTarget:
        model_click = (0.9, 0.4)

        def list_models(self):
            return []

    monkeypatch.setattr(handlers, "active_target", lambda state: EmptyListTarget())
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_model(update, context))
    assert update.message.replies
