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


class FakeSettings:
    language = "en"


class FakeConfig:
    secrets = FakeSecrets()
    settings = FakeSettings()


class FakeState:
    config = FakeConfig()


class FakeContext:
    def __init__(self):
        self.bot_data = {"state": FakeState()}


def _run(handler, chat_id):
    update = FakeUpdate(chat_id)
    asyncio.run(handler(update, FakeContext()))
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
    assert len(update.message.replies) == 1  # told them no, did nothing else


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
