"""
The @restricted decorator is the only thing stopping a stranger who finds
the bot from running shell commands on the machine. Worth testing directly.
"""
import asyncio
from dataclasses import dataclass

import pytest

from tether.transport.handlers import restricted

ALLOWED_CHAT_ID = 12345
STRANGER_CHAT_ID = 99999


@dataclass
class FakeChat:
    id: int


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, chat_id):
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage()


class FakeSecrets:
    chat_id = ALLOWED_CHAT_ID
    bot_password = None


class FakeSettings:
    language = "en"


class FakeConfig:
    secrets = FakeSecrets()
    settings = FakeSettings()


class FakeState:
    config = FakeConfig()
    unlocked = False


class FakeContext:
    def __init__(self):
        self.bot_data = {"state": FakeState()}


def _run(handler, chat_id):
    update = FakeUpdate(chat_id)
    asyncio.run(handler(update, FakeContext()))
    return update


def _run_with_text(handler, chat_id, text, password, unlocked, monkeypatch):
    """Uses monkeypatch (not direct mutation) for bot_password - FakeSecrets
    is a single shared class-level instance across every test in this file
    (same as chat_id above), and a raw mutation would leak into whichever
    test runs next."""
    monkeypatch.setattr(FakeSecrets, "bot_password", password)
    update = FakeUpdate(chat_id)
    update.message.text = text
    context = FakeContext()
    context.bot_data["state"].unlocked = unlocked
    asyncio.run(handler(update, context))
    return update


def test_allowed_chat_id_reaches_handler():
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run(handler, ALLOWED_CHAT_ID)
    assert called == [True]


def test_stranger_chat_id_is_blocked():
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    update = _run(handler, STRANGER_CHAT_ID)
    assert called == [], "handler ran for an unauthorized chat id"


def test_stranger_gets_no_reply_at_all():
    """Silence is deliberate. Replying would confirm the bot is live and let
    anyone burn the account's rate limit by spamming it."""
    @restricted
    async def handler(update, context):
        pass

    update = _run(handler, STRANGER_CHAT_ID)
    assert update.message.replies == [], "bot revealed itself to an unauthorized chat"


@pytest.mark.parametrize("chat_id", [0, -1, STRANGER_CHAT_ID, ALLOWED_CHAT_ID + 1])
def test_various_wrong_ids_all_blocked(chat_id):
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run(handler, chat_id)
    assert called == []


def test_handler_return_value_passed_through_for_allowed():
    @restricted
    async def handler(update, context):
        return "result"

    update = FakeUpdate(ALLOWED_CHAT_ID)
    assert asyncio.run(handler(update, FakeContext())) == "result"


# --- BOT_PASSWORD lock gate ---------------------------------------------

def test_no_password_set_never_locks(monkeypatch):
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run_with_text(handler, ALLOWED_CHAT_ID, "/anything", password=None, unlocked=False, monkeypatch=monkeypatch)
    assert called == [True]


def test_password_set_and_locked_blocks_the_handler(monkeypatch):
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    update = _run_with_text(handler, ALLOWED_CHAT_ID, "/status", password="hunter2", unlocked=False, monkeypatch=monkeypatch)
    assert called == [], "handler ran despite the bot being locked"
    assert update.message.replies, "locked chat should be told, not silently dropped"


def test_password_set_and_unlocked_reaches_the_handler(monkeypatch):
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run_with_text(handler, ALLOWED_CHAT_ID, "/status", password="hunter2", unlocked=True, monkeypatch=monkeypatch)
    assert called == [True]


@pytest.mark.parametrize("text", ["/start", "/unlock hunter2", "/help"])
def test_exempt_commands_reach_the_handler_while_locked(monkeypatch, text):
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run_with_text(handler, ALLOWED_CHAT_ID, text, password="hunter2", unlocked=False, monkeypatch=monkeypatch)
    assert called == [True], f"{text!r} should reach its handler even while locked"


def test_stranger_still_blocked_even_with_no_password(monkeypatch):
    """The chat-id gate is independent of the password gate - a stranger
    must never reach a handler regardless of BOT_PASSWORD."""
    called = []

    @restricted
    async def handler(update, context):
        called.append(True)

    _run_with_text(handler, STRANGER_CHAT_ID, "/status", password=None, unlocked=False, monkeypatch=monkeypatch)
    assert called == []
